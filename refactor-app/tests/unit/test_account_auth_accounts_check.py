import base64
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from refactor_app.application.workflows import account_auth
from refactor_app.application.workflows.account_auth import (
    PLUS_ONE_MONTH_FREE_PROMOTION_ID,
    AccountAuthWorkflowError,
    BackfillSessionWorkflow,
    _extract_account_promotion_campaigns,
    _extract_account_promotion_id,
    _extract_accounts_check_identities,
    _extract_personal_accounts_check_identity,
    _extract_personal_chatgpt_account_id,
    _openai_user_id_from_account_user_id,
    _persist_promotion_snapshot,
)
from refactor_app.infrastructure.db.models import (
    PromotionCheckRunModel,
    SpacePromotionOfferModel,
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


def test_accounts_check_extracts_every_campaign_for_only_the_target_space() -> None:
    payload = _accounts_check_payload()
    payload["accounts"]["personal-space-1"]["eligible_promo_campaigns"] = {
        "plus": {"id": PLUS_ONE_MONTH_FREE_PROMOTION_ID, "label": "Plus"},
        "team": {"promotionId": "team-trial", "label": "Team"},
    }
    payload["accounts"]["business-space-1"]["eligible_promo_campaigns"] = {
        "business": {"id": "business-only"}
    }

    offers = _extract_account_promotion_campaigns(payload, account_id="personal-space-1")

    assert [offer["promotion_id"] for offer in offers] == [
        PLUS_ONE_MONTH_FREE_PROMOTION_ID,
        "team-trial",
    ]
    assert offers[1]["campaign_key"] == "team"
    assert offers[1]["raw_offer_json"] == {"promotionId": "team-trial", "label": "Team"}


class _PromotionScalarResult:
    def __init__(self, rows: list[SpacePromotionOfferModel]) -> None:
        self._rows = rows

    def all(self) -> list[SpacePromotionOfferModel]:
        return list(self._rows)


class _PromotionSession:
    def __init__(self, existing: list[SpacePromotionOfferModel]) -> None:
        self.existing = existing
        self.added: list[object] = []

    def scalars(self, _stmt) -> _PromotionScalarResult:
        return _PromotionScalarResult(self.existing)

    def execute(self, _stmt):
        raise AssertionError("promotion persistence should use ORM scalar reads")

    def add(self, row: object) -> None:
        self.added.append(row)


def _promotion_offer(
    *,
    promotion_id: str,
    first_seen_at: datetime,
    last_seen_at: datetime | None = None,
) -> SpacePromotionOfferModel:
    return SpacePromotionOfferModel(
        id=f"offer-{promotion_id}",
        space_id="space-1",
        user_account_id="account-1",
        proxy_country="TR",
        promotion_id=promotion_id,
        promotion_name="old-name",
        status="eligible",
        normalized_json={"old": True},
        raw_campaign_json={"id": promotion_id, "old": True},
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at or first_seen_at,
        last_checked_at=last_seen_at or first_seen_at,
        source_check_id="promotion-check-old",
    )


def test_promotion_snapshot_upserts_current_offers_and_preserves_first_seen() -> None:
    first_seen = datetime(2026, 8, 1, tzinfo=UTC)
    previous_seen = first_seen + timedelta(days=1)
    checked_at = first_seen + timedelta(days=2)
    retained = _promotion_offer(
        promotion_id=PLUS_ONE_MONTH_FREE_PROMOTION_ID,
        first_seen_at=first_seen,
        last_seen_at=previous_seen,
    )
    disappeared = _promotion_offer(
        promotion_id="old-trial",
        first_seen_at=first_seen,
        last_seen_at=previous_seen,
    )
    session = _PromotionSession([retained, disappeared])
    response = {"accounts": {"personal-space-1": {}}}

    check_id = _persist_promotion_snapshot(
        session,
        space_id="space-1",
        user_account_id="account-1",
        proxy_country="TR",
        campaigns=[
            {
                "promotion_id": PLUS_ONE_MONTH_FREE_PROMOTION_ID,
                "campaign_key": "plus",
                "raw_offer_json": {
                    "id": PLUS_ONE_MONTH_FREE_PROMOTION_ID,
                    "label": "Plus",
                },
            },
            {
                "promotion_id": "new-trial",
                "campaign_key": "new",
                "raw_offer_json": {"id": "new-trial", "currency": "TRY"},
            },
        ],
        response_json=response,
        checked_at=checked_at,
    )

    assert check_id.startswith("promotion-check-")
    assert retained.first_seen_at == first_seen
    assert retained.last_seen_at == checked_at
    assert retained.last_checked_at == checked_at
    assert retained.status == "eligible"
    assert retained.source_check_id == check_id
    assert retained.raw_campaign_json["label"] == "Plus"
    assert disappeared.status == "stale"
    assert disappeared.last_seen_at == previous_seen
    assert disappeared.last_checked_at == checked_at
    assert disappeared.source_check_id == check_id

    created = next(
        row
        for row in session.added
        if isinstance(row, SpacePromotionOfferModel)
    )
    assert created.promotion_id == "new-trial"
    assert created.user_account_id == "account-1"
    assert created.proxy_country == "TR"
    assert created.status == "eligible"
    assert created.first_seen_at == checked_at
    assert created.source_check_id == check_id

    check = next(
        row for row in session.added if isinstance(row, PromotionCheckRunModel)
    )
    assert check.id == check_id
    assert check.space_id == "space-1"
    assert check.user_account_id == "account-1"
    assert check.proxy_country == "TR"
    assert check.status == "succeeded"
    assert check.campaigns_count == 2
    assert check.response_json == response


def test_empty_promotion_snapshot_marks_country_offers_stale() -> None:
    first_seen = datetime(2026, 8, 1, tzinfo=UTC)
    checked_at = first_seen + timedelta(days=1)
    previous = _promotion_offer(
        promotion_id=PLUS_ONE_MONTH_FREE_PROMOTION_ID,
        first_seen_at=first_seen,
    )
    session = _PromotionSession([previous])

    check_id = _persist_promotion_snapshot(
        session,
        space_id="space-1",
        user_account_id="account-1",
        proxy_country="TR",
        campaigns=[],
        response_json={"accounts": {}},
        checked_at=checked_at,
    )

    assert previous.status == "stale"
    assert previous.first_seen_at == first_seen
    assert previous.last_seen_at == first_seen
    assert previous.last_checked_at == checked_at
    assert previous.source_check_id == check_id
    check = next(
        row for row in session.added if isinstance(row, PromotionCheckRunModel)
    )
    assert check.status == "empty"
    assert check.campaigns_count == 0


def test_accounts_check_v4_headers_match_positive_promotion_har(monkeypatch) -> None:
    captured: dict = {}
    session_options: dict = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {})

    def create_client(**kwargs):
        session_options.update(kwargs)
        return Client()

    monkeypatch.setattr(account_auth.curl_requests, "Session", create_client)

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
    assert session_options["impersonate"] == account_auth.BROWSER_IMPERSONATE


def test_accounts_check_v4_prefers_captured_browser_identity(monkeypatch) -> None:
    captured: dict = {}
    session_options: dict = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {})

    def create_client(**kwargs):
        session_options.update(kwargs)
        return Client()

    monkeypatch.setattr(account_auth.curl_requests, "Session", create_client)

    account_auth._fetch_accounts_check_v4(
        access_token="access-token",
        cookie_header="session=value",
        proxy_url="http://proxy.example:8080",
        proxy_country="US",
        browser_user_agent="Mozilla/5.0 Fixture Firefox/152.0",
        browser_platform="Win32",
        browser_timezone="America/New_York",
        browser_timezone_offset=-240,
        browser_accept_language="en-US,en;q=0.5",
        browser_impersonate="firefox147",
    )

    assert captured["url"].endswith("?timezone_offset_min=-240")
    assert captured["headers"]["user-agent"] == "Mozilla/5.0 Fixture Firefox/152.0"
    assert captured["headers"]["accept-language"] == "en-US,en;q=0.5"
    assert captured["headers"]["oai-language"] == "en-US"
    assert "sec-ch-ua" not in captured["headers"]
    assert "sec-ch-ua-platform" not in captured["headers"]
    assert session_options["impersonate"] == "firefox"


def test_accounts_check_uses_rolling_chrome_alias_for_cloakbrowser() -> None:
    assert account_auth._supported_curl_impersonate("chrome150") == "chrome"


def test_accounts_check_v4_keeps_country_defaults_without_browser_identity(
    monkeypatch,
) -> None:
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
        proxy_country="JP",
    )

    assert captured["url"].endswith("?timezone_offset_min=540")
    assert captured["headers"]["accept-language"] == "ja-JP,ja;q=0.9,en;q=0.5"
    assert captured["headers"]["oai-language"] == "ja-JP"
    assert "user-agent" not in captured["headers"]


def test_personal_promotion_probe_uses_existing_token_and_configured_proxy(monkeypatch) -> None:
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
        proxy_url="http://tr-proxy.example:8080",
        proxy_country="TR",
    )

    assert captured["proxy_url"] == "http://tr-proxy.example:8080"
    assert captured["chatgpt_account_id"] == "personal-space-1"
    assert captured["access_token"] == "personal-access-token"
    assert "__Secure-next-auth.session-token=session-token" in captured["cookie_header"]
    assert result["proxy_country"] == "TR"
    assert result["has_promotion"] is True
    assert space.has_promotion is True
    assert space.promotion_id == PLUS_ONE_MONTH_FREE_PROMOTION_ID


def test_backfill_session_resolves_us_cliproxy_instead_of_bound_proxy() -> None:
    captured: list[dict] = []
    events: list[tuple[str, dict]] = []
    account = SimpleNamespace(id="account-1", email="backfill@example.test")
    workflow = BackfillSessionWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        proxy_resolver=lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                proxy_url="http://cliproxy.example:443",
                provider="cliproxy",
                country_code="US",
                egress_ip="203.0.113.10",
                sid_source="email_sha256",
                proxy_mode="cliproxy_sticky",
            )
        ),
    )
    workflow._load_account_auth_proxy = lambda _user_account_id: (account, account, None)
    workflow._write_event = lambda _run_id, event_type, _message, data, **_kwargs: events.append(
        (event_type, data)
    )

    loaded = workflow._load_input("account-1", run_id="run-1")

    assert loaded == (account, account, "http://cliproxy.example:443", "US")
    assert captured == [{"email": "backfill@example.test", "country_code": "US"}]
    assert events == [
        (
            "account_auth.proxy_ready",
            {
                "user_account_id": "account-1",
                "proxy_source": "cliproxy",
                "proxy_provider": "cliproxy",
                "proxy_country": "US",
                "proxy_country_source": "configured_default",
                "proxy_egress_ip": "203.0.113.10",
                "proxy_sid_source": "email_sha256",
                "proxy_mode": "cliproxy_sticky",
            },
        )
    ]

    workflow._force_new_proxy_sid = True
    workflow._load_input("account-1", run_id="run-2")
    assert captured[-1] == {
        "email": "backfill@example.test",
        "country_code": "US",
        "force_new_sid": True,
    }


@pytest.mark.parametrize(
    ("email", "country"),
    [
        ("account@yandex.lt", "LT"),
        ("account@yandex.com.tr", "TR"),
    ],
)
def test_backfill_session_uses_yandex_email_country(email: str, country: str) -> None:
    captured: list[dict] = []
    events: list[tuple[str, dict]] = []
    account = SimpleNamespace(id="account-1", email=email)
    workflow = BackfillSessionWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        proxy_resolver=lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                proxy_url="http://cliproxy.example:443",
                provider="cliproxy",
                country_code=country,
            )
        ),
    )
    workflow._load_account_auth_proxy = lambda _user_account_id: (account, account, None)
    workflow._write_event = lambda _run_id, event_type, _message, data, **_kwargs: events.append(
        (event_type, data)
    )

    loaded = workflow._load_input("account-1", run_id="run-1")

    assert loaded == (account, account, "http://cliproxy.example:443", country)
    assert captured == [{"email": email, "country_code": country}]
    assert events[0][1]["proxy_country"] == country
    assert events[0][1]["proxy_country_source"] == "email_domain"


def test_backfill_session_configured_country_overrides_yandex_email_country() -> None:
    captured: list[dict] = []
    events: list[tuple[str, dict]] = []
    account = SimpleNamespace(id="account-1", email="account@yandex.lt")
    workflow = BackfillSessionWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        proxy_country="de",
        prefer_configured_proxy_country=True,
        proxy_resolver=lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                proxy_url="http://cliproxy.example:443",
                provider="cliproxy",
                country_code="DE",
            )
        ),
    )
    workflow._load_account_auth_proxy = lambda _user_account_id: (account, account, None)
    workflow._write_event = lambda _run_id, event_type, _message, data, **_kwargs: events.append(
        (event_type, data)
    )

    loaded = workflow._load_input("account-1", run_id="run-1")

    assert loaded == (account, account, "http://cliproxy.example:443", "DE")
    assert captured == [{"email": "account@yandex.lt", "country_code": "DE"}]
    assert events[0][1]["proxy_country_source"] == "configured_override"


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
            return account, auth, "http://proxy.example:8080", "US"

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
        "proxy_country": "US",
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
