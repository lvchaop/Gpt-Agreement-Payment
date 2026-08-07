import base64
import json
from types import SimpleNamespace

import pytest

from refactor_app.application.workflows import account_auth
from refactor_app.application.workflows.account_auth import (
    PLUS_ONE_MONTH_FREE_PROMOTION_ID,
    AccountAuthWorkflowError,
    BackfillSessionWorkflow,
    _extract_account_promotion_id,
    _extract_accounts_check_identities,
    _extract_personal_accounts_check_identity,
    _extract_personal_chatgpt_account_id,
    _openai_user_id_from_account_user_id,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import session_account_fields


def _workspace_token(account_id: str) -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return ".".join(
        (
            encode({"alg": "none", "typ": "JWT"}),
            encode(
                {
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": account_id,
                        "chatgpt_user_id": "user-1",
                    }
                }
            ),
            "",
        )
    )


def _accounts_check_payload() -> dict:
    personal = {
        "account": {
            "account_id": "personal-space-1",
            "account_owner_id": "user-owner-1",
            "account_user_id": "user-owner-1__personal-space-1",
            "structure": "personal",
        }
    }
    return {
        "accounts": {
            "business-space-1": {
                "account": {
                    "account_id": "business-space-1",
                    "account_owner_id": "user-owner-1",
                    "account_user_id": "user-owner-1__business-space-1",
                    "structure": "workspace",
                }
            },
            "personal-space-1": personal,
            "default": personal,
        },
        "account_ordering": ["business-space-1", "personal-space-1"],
    }


def test_session_account_fields_extracts_personal_plan_type() -> None:
    assert session_account_fields(
        {
            "account": {
                "id": "personal-space-1",
                "structure": "personal",
                "planType": "pro",
            }
        }
    ) == ("personal-space-1", "personal", "pro")


def test_accounts_check_extracts_stable_and_scoped_user_ids() -> None:
    identities = _extract_accounts_check_identities(_accounts_check_payload())

    assert identities["business-space-1"].account_owner_id == "user-owner-1"
    assert identities["business-space-1"].account_user_id == "user-owner-1__business-space-1"


def test_accounts_check_selects_personal_identity_as_account_identity() -> None:
    payload = _accounts_check_payload()

    identity = _extract_personal_accounts_check_identity(payload)

    assert identity is not None
    assert identity.account_id == "personal-space-1"
    assert identity.account_owner_id == "user-owner-1"
    assert _extract_personal_chatgpt_account_id(payload) == "personal-space-1"


def test_accounts_check_extracts_plus_promotion_for_target_personal_space() -> None:
    payload = _accounts_check_payload()
    payload["accounts"]["personal-space-1"]["eligible_promo_campaigns"] = {
        "plus": {"id": PLUS_ONE_MONTH_FREE_PROMOTION_ID}
    }

    assert (
        _extract_account_promotion_id(payload, account_id="personal-space-1")
        == PLUS_ONE_MONTH_FREE_PROMOTION_ID
    )

    payload["accounts"]["personal-space-1"].pop("eligible_promo_campaigns")
    payload["accounts"]["business-space-1"]["eligible_promo_campaigns"] = {
        "plus": {"id": PLUS_ONE_MONTH_FREE_PROMOTION_ID}
    }
    assert _extract_account_promotion_id(payload, account_id="personal-space-1") == ""


def test_accounts_check_v4_headers_match_positive_promotion_har(monkeypatch) -> None:
    captured: dict = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {})

    monkeypatch.setattr(account_auth.curl_requests, "Session", lambda **_kwargs: Client())

    account_auth._fetch_accounts_check_v4(
        access_token="access-token",
        cookie_header="session=value",
        proxy_url="http://proxy.example:8080",
    )

    headers = captured["headers"]
    assert headers["oai-client-build-number"] == "9052945"
    assert (
        headers["oai-client-version"]
        == "prod-e1d6f2820dd20c3bab36cc42e8668035bf87f7bc"
    )
    assert headers["referer"] == "https://chatgpt.com/"
    assert headers["x-openai-target-path"] == "/backend-api/accounts/check/v4-2023-04-27"


def test_personal_promotion_probe_uses_existing_token_and_jp_proxy(monkeypatch) -> None:
    captured: dict = {}
    account = SimpleNamespace(
        access_token="personal-access-token",
        session_token="session-token",
        cookie_header="oai-did=device-1",
        device_id="device-1",
    )
    space = SimpleNamespace(
        external_space_id="personal-space-1",
        has_promotion=False,
        promotion_id="",
        updated_at=None,
    )

    class ScalarResult:
        def first(self):
            return space

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _model, key):
            assert key == "account-1"
            return account

        def scalars(self, _stmt):
            return ScalarResult()

        def commit(self):
            return None

    def fetch(**kwargs):
        captured.update(kwargs)
        payload = _accounts_check_payload()
        payload["accounts"]["personal-space-1"]["eligible_promo_campaigns"] = {
            "plus": {"id": PLUS_ONE_MONTH_FREE_PROMOTION_ID}
        }
        return payload

    monkeypatch.setattr(account_auth, "_fetch_accounts_check_v4", fetch)
    result = BackfillSessionWorkflow(
        session_factory=FakeSession,
        mail_provider=object(),
    ).probe_personal_space_promotion(
        user_account_id="account-1",
        proxy_url="http://jp-proxy.example:8080",
    )

    assert captured["proxy_url"] == "http://jp-proxy.example:8080"
    assert captured["chatgpt_account_id"] == "personal-space-1"
    assert captured["access_token"] == "personal-access-token"
    assert "__Secure-next-auth.session-token=session-token" in captured["cookie_header"]
    assert result["proxy_country"] == "JP"
    assert result["has_promotion"] is True
    assert space.has_promotion is True
    assert space.promotion_id == PLUS_ONE_MONTH_FREE_PROMOTION_ID


def test_account_user_id_extracts_member_user_id_without_workspace_suffix() -> None:
    assert (
        _openai_user_id_from_account_user_id("user-member-1__business-space-1") == "user-member-1"
    )
    assert _openai_user_id_from_account_user_id("not-a-user__business-space-1") == ""


def test_refresh_detected_spaces_uses_current_session_and_only_marks_detection() -> None:
    captured: dict = {}
    access_token = _workspace_token("personal-space-1")

    class Workflow(BackfillSessionWorkflow):
        def __init__(self) -> None:
            pass

        def _load_input(self, user_account_id: str, run_id: str = ""):
            assert user_account_id == "account-1"
            assert run_id == "run-1"
            account = SimpleNamespace(id="account-1")
            auth = SimpleNamespace(
                access_token=access_token,
                cookie_header="session-cookie=value",
                device_id="device-1",
            )
            return account, auth, "http://proxy.example:8080"

        def _mark_detected_space_memberships(self, **kwargs) -> dict:
            captured.update(kwargs)
            return _accounts_check_payload()

        def detect_account_spaces_from_session(self, **_kwargs) -> dict:
            raise AssertionError("refresh must not enter full session detection")

    result = Workflow().refresh_detected_spaces_from_current_session(
        user_account_id="account-1",
        run_id="run-1",
    )

    assert captured == {
        "user_account_id": "account-1",
        "access_token": access_token,
        "cookie_header": "session-cookie=value",
        "proxy_url": "http://proxy.example:8080",
        "chatgpt_account_id": "personal-space-1",
        "oai_device_id": "device-1",
        "run_id": "run-1",
        "parent_step_id": "",
        "raise_on_error": True,
        "detection_flag_only": True,
    }
    assert result["user_account_id"] == "account-1"
    assert result["accounts_check_succeeded"] is True
    assert result["visible_account_ids"] == ["business-space-1", "personal-space-1"]


def test_required_accounts_check_propagates_v4_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        account_auth,
        "_fetch_accounts_check_v4",
        lambda **_kwargs: (_ for _ in ()).throw(
            AccountAuthWorkflowError("accounts_check_failed:http_status=403")
        ),
    )

    class Workflow(BackfillSessionWorkflow):
        def __init__(self) -> None:
            pass

        def _start_step(self, *_args, **_kwargs) -> str:
            return "step-1"

        def _write_event(self, *_args, **_kwargs) -> None:
            return None

        def _finish_step(self, *_args, **_kwargs) -> None:
            return None

    workflow = Workflow()
    with pytest.raises(AccountAuthWorkflowError, match="accounts_check_failed"):
        workflow._mark_detected_space_memberships(
            user_account_id="account-1",
            access_token="access-token",
            cookie_header="session-cookie=value",
            proxy_url="http://proxy.example:8080",
            run_id="run-1",
            parent_step_id="",
            raise_on_error=True,
        )


def test_detect_account_spaces_exchanges_business_bootstrap_for_personal_token() -> None:
    bootstrap_token = _workspace_token("business-space-1")
    personal_token = _workspace_token("personal-space-1")
    exchange_calls: list[dict] = []
    written_tokens: list[dict] = []
    personal_spaces: list[dict] = []

    class ChatGPTClient:
        def exchange_workspace_session_payload(self, **kwargs) -> dict:
            exchange_calls.append(kwargs)
            return {
                "accessToken": personal_token,
                "account": {
                    "id": "personal-space-1",
                    "structure": "personal",
                    "planType": "plus",
                },
            }

    class Workflow(BackfillSessionWorkflow):
        def __init__(self) -> None:
            self._chatgpt_client = ChatGPTClient()

        def _mark_detected_space_memberships(self, **kwargs) -> dict:
            assert kwargs["chatgpt_account_id"] == "business-space-1"
            return _accounts_check_payload()

        def _has_personal_chatgpt_account_id(self, _user_account_id: str) -> bool:
            return True

        def _personal_space_external_id(self, _user_account_id: str) -> str:
            return "personal-space-1"

        def _write_personal_session_access_token(self, **kwargs) -> None:
            written_tokens.append(kwargs)

        def _ensure_personal_space_from_session(self, **kwargs) -> None:
            personal_spaces.append(kwargs)

        def _write_event(self, *_args, **_kwargs) -> None:
            return None

    result = Workflow().detect_account_spaces_from_session(
        user_account_id="account-1",
        access_token=bootstrap_token,
        cookie_header="__Secure-next-auth.session-token=session-1",
        proxy_url="http://proxy.example",
        session_chatgpt_account_id="business-space-1",
        session_chatgpt_account_structure="workspace",
        require_personal_access_token=True,
    )

    assert result["personal_session_access_token_status"] == "active"
    assert result["personal_plan_type"] == "plus"
    assert exchange_calls == [
        {
            "chatgpt_account_id": "personal-space-1",
            "cookie_header": "__Secure-next-auth.session-token=session-1",
            "proxy_url": "http://proxy.example",
        }
    ]
    assert written_tokens == [
        {
            "user_account_id": "account-1",
            "personal_chatgpt_account_id": "personal-space-1",
            "access_token": personal_token,
        }
    ]
    assert personal_spaces == [
        {
            "user_account_id": "account-1",
            "personal_chatgpt_account_id": "personal-space-1",
            "plan_type": "plus",
        }
    ]
