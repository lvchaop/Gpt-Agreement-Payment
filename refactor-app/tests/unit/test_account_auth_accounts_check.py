import base64
import json

from refactor_app.application.workflows.account_auth import (
    BackfillSessionWorkflow,
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


def test_account_user_id_extracts_member_user_id_without_workspace_suffix() -> None:
    assert (
        _openai_user_id_from_account_user_id("user-member-1__business-space-1") == "user-member-1"
    )
    assert _openai_user_id_from_account_user_id("not-a-user__business-space-1") == ""


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
