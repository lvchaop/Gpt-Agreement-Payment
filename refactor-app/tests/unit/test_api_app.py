from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import delete, select

from refactor_app.api.app import create_app
from refactor_app.api.routes import resources as resource_routes
from refactor_app.application.jobs import handlers
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobModel,
    PaymentAddressPoolModel,
    PaymentCardPoolModel,
    PaymentNamePoolModel,
    SpaceMembershipModel,
    SpaceModel,
    TeamAdminSessionModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.plugins.payment_card import payment_card_fingerprint


def _disable_web_login(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_WEB_LOGIN_PASSWORD", "")


def test_create_app_registers_p8_routes(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    app = create_app()

    paths = set(app.openapi()["paths"])

    assert app.title == "refactor-app"
    assert "/health" in paths
    assert "/jobs" in paths
    assert "/user-accounts" in paths
    assert "/user-accounts/{user_account_id}/access-token" in paths
    assert "/user-accounts/delete-selected" in paths
    assert "/account-email-change/jobs" in paths
    assert "/spaces" in paths
    assert "/payment-method-pools/summary" in paths
    assert "/payment-method-pools/import" in paths
    assert "/spaces/{space_id}/payment-method-bind-job" in paths
    assert "/spaces/{space_id}/paypal-link-job" in paths
    assert "/spaces/paypal-link-selected-job" in paths
    assert "/spaces/payment-method-bind-selected-job" in paths
    assert "/spaces/promotion-check-selected-job" in paths
    assert "/spaces/promotion-offers" in paths
    assert "/spaces/subscription-refresh-selected-job" in paths
    assert "/memberships/personal-codex-authorize-job" in paths
    assert "/space-credentials" in paths
    assert "/space-credentials/business-access-token-job" in paths
    assert "/space-credentials/push-job" in paths
    assert "/spaces/recycle-sweep-job" in paths
    assert "/team-workspaces" not in paths
    assert "/codex-credentials" not in paths
    assert "/workspace-join-batches" not in paths
    assert "/downstream-push-records" not in paths
    assert "/proxies" in paths
    assert "/mail/allocate-job" in paths
    assert "/mail/poll-otp-job" in paths
    assert "/mail/mark-used-job" in paths
    assert "/mail/mark-failed-job" in paths
    assert "/mail/release-job" in paths
    assert "/ops" in paths


def test_ops_ui_serves_minimal_operations_page(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert '<div id="app"></div>' in response.text
    assert "/ops/assets/" in response.text


def test_create_job_api_enqueues_job(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/jobs",
        json={"type": "test.api.enqueue", "input_json": {"value": "ok"}, "created_by": "test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_status"] == "queued"

    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        job = session.get(JobModel, body["job_id"])
        assert job is not None
        assert job.type == "test.api.enqueue"
        session.execute(delete(JobModel).where(JobModel.id == body["job_id"]))
        session.commit()


def test_protocol_registration_api_normalizes_and_defaults_proxy_country(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    job_ids: list[str] = []

    try:
        configured = client.post(
            "/account-protocol-registration/jobs",
            json={
                "mode": "email_protocol_no_phone",
                "proxy_country": "jp",
                "authorize_codex_after_security": True,
            },
        )
        defaulted = client.post(
            "/account-protocol-registration/jobs",
            json={"mode": "email_protocol_no_phone"},
        )
        invalid = client.post(
            "/account-protocol-registration/jobs",
            json={"mode": "email_protocol_no_phone", "proxy_country": "USA"},
        )

        assert configured.status_code == 200
        assert defaulted.status_code == 200
        assert invalid.status_code == 422
        job_ids = [configured.json()["job_id"], defaulted.json()["job_id"]]

        session_factory = make_session_factory(make_engine(Settings()))
        with session_factory() as session:
            configured_job = session.get(JobModel, job_ids[0])
            defaulted_job = session.get(JobModel, job_ids[1])
            assert configured_job is not None
            assert defaulted_job is not None
            assert configured_job.input_json["proxy_country"] == "JP"
            assert defaulted_job.input_json["proxy_country"] == "US"
            assert configured_job.input_json["authorize_codex_after_security"] is True
            assert defaulted_job.input_json["authorize_codex_after_security"] is False
    finally:
        if job_ids:
            session_factory = make_session_factory(make_engine(Settings()))
            with session_factory() as session:
                session.execute(delete(JobModel).where(JobModel.id.in_(job_ids)))
                session.commit()


def test_protocol_registration_api_accepts_state_or_asn_route_selector(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    job_ids: list[str] = []

    try:
        state_response = client.post(
            "/account-protocol-registration/jobs",
            json={
                "mode": "email_protocol_no_phone",
                "proxy_country": "us",
                "proxy_state": "California",
            },
        )
        asn_response = client.post(
            "/account-protocol-registration/jobs",
            json={
                "mode": "email_protocol_no_phone",
                "proxy_country": "us",
                "proxy_asn": "AS33363",
            },
        )
        both_response = client.post(
            "/account-protocol-registration/jobs",
            json={
                "mode": "email_protocol_no_phone",
                "proxy_state": "California",
                "proxy_asn": "33363",
            },
        )

        assert state_response.status_code == 200
        assert asn_response.status_code == 200
        assert both_response.status_code == 422
        job_ids = [state_response.json()["job_id"], asn_response.json()["job_id"]]

        session_factory = make_session_factory(make_engine(Settings()))
        with session_factory() as session:
            state_job = session.get(JobModel, job_ids[0])
            asn_job = session.get(JobModel, job_ids[1])
            assert state_job is not None
            assert asn_job is not None
            assert state_job.input_json["proxy_country"] == "US"
            assert state_job.input_json["proxy_state"] == "California"
            assert state_job.input_json["proxy_asn"] == ""
            assert asn_job.input_json["proxy_country"] == "US"
            assert asn_job.input_json["proxy_state"] == ""
            assert asn_job.input_json["proxy_asn"] == "AS33363"
    finally:
        if job_ids:
            session_factory = make_session_factory(make_engine(Settings()))
            with session_factory() as session:
                session.execute(delete(JobModel).where(JobModel.id.in_(job_ids)))
                session.commit()


def test_protocol_registration_api_persists_browser_backend_without_license_key(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    monkeypatch.setenv("CLOAKBROWSER_LICENSE_KEY", "cb_fixture_secret")
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "email_browser_no_phone",
            "browser_backend": "cloakbrowser",
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    session_factory = make_session_factory(make_engine(Settings()))
    try:
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            assert job is not None
            assert job.input_json["browser_backend"] == "cloakbrowser"
            assert "cloakbrowser_license_key" not in job.input_json
            assert "cb_fixture_secret" not in str(job.input_json)
    finally:
        with session_factory() as session:
            session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.commit()


def test_protocol_registration_api_accepts_phone_browser_mode(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "phone_browser_bind_email",
            "mail_provider": "hero_yandex",
            "browser_backend": "camoufox",
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    session_factory = make_session_factory(make_engine(Settings()))
    try:
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            assert job is not None
            assert job.input_json["mode"] == "phone_browser_bind_email"
            assert job.input_json["mail_provider"] == "hero_yandex"
    finally:
        with session_factory() as session:
            session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.commit()


def test_backfill_session_job_persists_selected_proxy_country(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    suffix = uuid4().hex
    account_id = f"test-backfill-country-{suffix}"
    job_id = ""
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email=f"backfill-country-{suffix}@yandex.lt",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        response = client.post(
            "/user-accounts/backfill-session-job",
            json={"user_account_ids": [account_id], "proxy_country": "de"},
        )

        assert response.status_code == 200
        payload = response.json()
        job_id = payload["job_id"]
        assert payload["proxy_country"] == "DE"
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            work = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).one()
            assert job is not None
            assert job.input_json["proxy_country"] == "DE"
            assert work.input_json["proxy_country"] == "DE"
    finally:
        with session_factory() as session:
            if job_id:
                session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
            session.commit()


def test_backfill_session_request_defaults_proxy_country_to_us() -> None:
    request = resource_routes.BackfillSessionRtRequest(user_account_ids=["account-1"])

    assert request.proxy_country == "US"


def test_backfill_session_work_handler_passes_explicit_proxy_country(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}

    class Workflow:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def run(self, **kwargs):
            captured["run"] = kwargs
            return kwargs["user_account_id"]

    monkeypatch.setattr(handlers, "BackfillSessionWorkflow", Workflow)
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    runner = handlers.JobRunner(lambda: None)
    handlers.register_core_handlers(
        runner,
        session_factory=lambda: None,
        settings=Settings(_env_file=None),
    )

    result = runner._work_handlers["account.backfill_session"](
        None,
        {"user_account_id": "account-1", "proxy_country": "de", "_run_id": "run-1"},
    )

    assert result == {"user_account_id": "account-1"}
    assert captured["init"]["proxy_country"] == "DE"
    assert captured["init"]["prefer_configured_proxy_country"] is True
    assert captured["run"] == {"user_account_id": "account-1", "run_id": "run-1"}


def test_protocol_registration_api_accepts_hero_gmail_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "email_browser_no_phone",
            "mail_provider": "hero_gmail",
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    session_factory = make_session_factory(make_engine(Settings()))
    try:
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            assert job is not None
            assert job.input_json["mail_provider"] == "hero_gmail"
            assert job.input_json["email_domain"] == "gmail.com"
    finally:
        with session_factory() as session:
            session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.commit()


def test_protocol_registration_api_rejects_non_gmail_hero_domain(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "email_browser_no_phone",
            "mail_provider": "hero_gmail",
            "email_domain": "hotmail.com",
        },
    )
    assert response.status_code == 422


def test_protocol_registration_api_accepts_multiple_hero_yandex_domains(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "email_browser_no_phone",
            "mail_provider": "hero_yandex",
            "email_domain": " yandex.ru, yandex.com.tr;ya.ru ",
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    session_factory = make_session_factory(make_engine(Settings()))
    try:
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            assert job is not None
            assert job.input_json["mail_provider"] == "hero_yandex"
            assert job.input_json["email_domain"] == "yandex.ru,yandex.com.tr,ya.ru"
    finally:
        with session_factory() as session:
            session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.commit()


def test_protocol_registration_api_rejects_non_yandex_hero_domain(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    response = client.post(
        "/account-protocol-registration/jobs",
        json={
            "mode": "email_browser_no_phone",
            "mail_provider": "hero_yandex",
            "email_domain": "yandex.ru,gmail.com",
        },
    )
    assert response.status_code == 422


def test_delete_selected_user_accounts(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_ids = [f"test-bulk-delete-{uuid4()}" for _ in range(2)]
    missing_id = f"test-bulk-delete-missing-{uuid4()}"
    personal_space_ids = [f"{account_id}-personal-space" for account_id in account_ids]
    business_space_id = f"{account_ids[0]}-business-space"
    now = datetime.now(UTC)

    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        session.add_all(
            UserAccountModel(
                id=account_id,
                email=f"{account_id}@example.com",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
            for account_id in account_ids
        )
        session.add_all(
            [
                SpaceModel(
                    id=space_id,
                    external_space_id=f"{space_id}-external",
                    owner_user_account_id=account_id,
                    name=space_id,
                    space_type="personal",
                    auth_mode="codex_oauth",
                    credential_type="personal_account",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
                for account_id, space_id in zip(account_ids, personal_space_ids, strict=True)
            ]
            + [
                SpaceModel(
                    id=business_space_id,
                    external_space_id=f"{business_space_id}-external",
                    owner_user_account_id=account_ids[0],
                    name=business_space_id,
                    space_type="business",
                    auth_mode="backend_access_token",
                    credential_type="team_5h_weekly",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            ]
        )
        session.commit()

    try:
        response = client.post(
            "/user-accounts/delete-selected",
            json={"user_account_ids": [account_ids[0], account_ids[0], account_ids[1], missing_id]},
        )

        assert response.status_code == 200
        assert response.json() == {
            "requested_count": 3,
            "deleted_count": 2,
            "missing_count": 1,
            "deleted_personal_spaces": 2,
            "deleted_proxy_bindings": 0,
        }
        with session_factory() as session:
            assert session.get(UserAccountModel, account_ids[0]) is None
            assert session.get(UserAccountModel, account_ids[1]) is None
            assert session.get(SpaceModel, personal_space_ids[0]) is None
            assert session.get(SpaceModel, personal_space_ids[1]) is None
            assert session.get(SpaceModel, business_space_id) is not None
    finally:
        with session_factory() as session:
            session.execute(
                delete(SpaceModel).where(
                    SpaceModel.id.in_([*personal_space_ids, business_space_id])
                )
            )
            session.execute(delete(UserAccountModel).where(UserAccountModel.id.in_(account_ids)))
            session.commit()


def test_delete_user_account_deletes_owned_personal_space(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_id = f"test-delete-account-{uuid4()}"
    personal_space_id = f"{account_id}-personal-space"
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))
    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email=f"{account_id}@example.com",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=personal_space_id,
                external_space_id=f"{personal_space_id}-external",
                owner_user_account_id=account_id,
                name=personal_space_id,
                space_type="personal",
                auth_mode="codex_oauth",
                credential_type="personal_account",
                space_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        response = client.delete(f"/user-accounts/{account_id}")

        assert response.status_code == 200
        assert response.json() == {
            "user_account_id": account_id,
            "deleted": True,
            "deleted_personal_spaces": 1,
            "deleted_proxy_bindings": 0,
        }
        with session_factory() as session:
            assert session.get(UserAccountModel, account_id) is None
            assert session.get(SpaceModel, personal_space_id) is None
    finally:
        with session_factory() as session:
            session.execute(delete(SpaceModel).where(SpaceModel.id == personal_space_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
            session.commit()


def test_get_user_account_access_token_reads_single_account(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_id = f"test-access-token-{uuid4()}"
    empty_account_id = f"test-access-token-empty-{uuid4()}"
    now = datetime.now(UTC)
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=account_id,
                    email=f"{account_id}@example.com",
                    access_token="personal-session-access-token",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=empty_account_id,
                    email=f"{empty_account_id}@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    try:
        response = client.get(f"/user-accounts/{account_id}/access-token")
        assert response.status_code == 200
        assert response.json() == {
            "user_account_id": account_id,
            "access_token": "personal-session-access-token",
        }

        list_response = client.get("/user-accounts", params={"q": account_id})
        item = list_response.json()["items"][0]
        assert item["has_access_token"] is True
        assert "access_token" not in item

        empty_response = client.get(f"/user-accounts/{empty_account_id}/access-token")
        assert empty_response.status_code == 409
        assert empty_response.json()["detail"] == "account access_token is empty"
    finally:
        with session_factory() as session:
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([account_id, empty_account_id])
                )
            )
            session.commit()


def test_payment_method_pool_import_and_personal_job_api(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    route_settings = Settings(_env_file=None)
    captcha_client_key = uuid4().hex
    route_settings.personal_plus_checkout_captcha_api_url = "https://captcha.test"
    route_settings.personal_plus_checkout_captcha_client_key = captcha_client_key
    monkeypatch.setattr(resource_routes, "get_settings", lambda: route_settings)
    client = TestClient(create_app())
    prefix = f"test-payment-method-{uuid4()}"
    account_id = f"{prefix}-account"
    space_id = f"{prefix}-space"
    card_number = _test_luhn_card(uuid4().int)
    full_name = f"Test User {uuid4().hex[:8]}"
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))
    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email=f"{prefix}@example.com",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=space_id,
                external_space_id=f"{prefix}-external",
                owner_user_account_id=account_id,
                name=prefix,
                space_type="personal",
                auth_mode="codex_oauth",
                credential_type="personal_account",
                has_promotion=True,
                promotion_id="plus-1-month-free",
                space_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    job_id = ""
    try:
        import_response = client.post(
            "/payment-method-pools/import",
            json={
                "names": [full_name],
                "addresses": [
                    {
                        "line1": f"{prefix} Main Street",
                        "city": "Berlin",
                        "state": "BE",
                        "postal_code": "10115",
                        "country": "DE",
                    }
                ],
                "cards": [
                    {
                        "card_number": card_number,
                        "cvc": "123",
                        "exp_month": 12,
                        "exp_year": 2035,
                    }
                ],
            },
        )
        assert import_response.status_code == 200
        import_payload = import_response.json()
        assert import_payload["inserted_count"] == 3
        assert import_payload["summary"]["active_address_country_counts"]["DE"] >= 1
        assert card_number not in import_response.text
        assert '"cvc":"123"' not in import_response.text

        spaces_response = client.get(
            "/spaces",
            params={"q": prefix, "payment_method_status": "missing"},
        )
        assert spaces_response.status_code == 200
        space_payload = spaces_response.json()["items"][0]
        assert space_payload["payment_method_status"] == "missing"
        assert space_payload["payment_method_attempt_count"] == 0

        job_response = client.post(
            f"/spaces/{space_id}/payment-method-bind-job",
            json={"created_by": "test", "proxy_country": "de"},
        )
        assert job_response.status_code == 200
        job_id = job_response.json()["job_id"]
        assert job_response.json()["job_status"] in {"queued", "running"}
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            work = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).one()
        assert job is not None
        assert job.input_json["proxy_country"] == "DE"
        assert work.input_json["proxy_country"] == "DE"
        assert job.input_json["checkout_ui_mode"] == "custom"
        assert work.input_json["checkout_ui_mode"] == "custom"
        assert job.input_json["captcha_api_url"] == "https://captcha.test"
        assert work.input_json["captcha_api_url"] == "https://captcha.test"
        assert hashlib.sha256(job.input_json["captcha_client_key"].encode()).digest() == (
            hashlib.sha256(captcha_client_key.encode()).digest()
        )
        assert hashlib.sha256(work.input_json["captcha_client_key"].encode()).digest() == (
            hashlib.sha256(captcha_client_key.encode()).digest()
        )
        assert "captcha_client_key" not in job_response.text

        duplicate_response = client.post(
            f"/spaces/{space_id}/payment-method-bind-job",
            json={"created_by": "test"},
        )
        assert duplicate_response.status_code == 200
        assert duplicate_response.json()["job_id"] == job_id
    finally:
        with session_factory() as session:
            if job_id:
                session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.execute(delete(SpaceModel).where(SpaceModel.id == space_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
            session.execute(
                delete(PaymentCardPoolModel).where(
                    PaymentCardPoolModel.card_fingerprint
                    == payment_card_fingerprint(card_number)
                )
            )
            session.execute(
                delete(PaymentAddressPoolModel).where(
                    PaymentAddressPoolModel.line1 == f"{prefix} Main Street"
                )
            )
            session.execute(
                delete(PaymentNamePoolModel).where(
                    PaymentNamePoolModel.normalized_name == full_name.casefold()
                )
            )
            session.commit()


def test_space_payment_method_boolean_filter_and_selected_bind_job(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    route_settings = Settings(_env_file=None)
    captcha_client_key = uuid4().hex
    route_settings.personal_plus_checkout_captcha_api_url = "https://captcha.test"
    route_settings.personal_plus_checkout_captcha_client_key = captcha_client_key
    monkeypatch.setattr(resource_routes, "get_settings", lambda: route_settings)
    monkeypatch.setattr(
        resource_routes,
        "payment_method_inventory_summary",
        lambda _session: {
            "active_name_count": 1,
            "active_address_count": 1,
            "active_address_country_counts": {"JP": 1},
            "available_card_count": 10,
        },
    )
    client = TestClient(create_app())
    prefix = f"test-payment-selected-{uuid4()}"
    active_account_id = f"{prefix}-active-account"
    inactive_account_id = f"{prefix}-inactive-account"
    now = datetime.now(UTC)
    space_ids = {
        "eligible": f"{prefix}-eligible",
        "bound": f"{prefix}-bound",
        "business": f"{prefix}-business",
        "inactive_owner": f"{prefix}-inactive-owner",
        "cooling": f"{prefix}-cooling",
    }

    def make_space(
        key: str,
        *,
        owner_user_account_id: str = active_account_id,
        space_type: str = "personal",
        has_payment_method: bool = False,
        payment_method_status: str = "missing",
        payment_method_attempt_count: int = 0,
        payment_method_cooldown_until: datetime | None = None,
    ) -> SpaceModel:
        return SpaceModel(
            id=space_ids[key],
            external_space_id=f"{prefix}-external-{key}",
            owner_user_account_id=owner_user_account_id,
            name=f"{prefix}-{key}",
            space_type=space_type,
            auth_mode="codex_oauth",
            credential_type=(
                "personal_account" if space_type == "personal" else "team_5h_weekly"
            ),
            has_promotion=space_type == "personal",
            promotion_id=("plus-1-month-free" if space_type == "personal" else ""),
            has_payment_method=has_payment_method,
            payment_method_status=payment_method_status,
            payment_method_attempt_count=payment_method_attempt_count,
            payment_method_cooldown_until=payment_method_cooldown_until,
            space_status="active",
            created_at=now,
            updated_at=now,
        )

    session_factory = make_session_factory(make_engine(Settings()))
    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=active_account_id,
                    email=f"{active_account_id}@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=inactive_account_id,
                    email=f"{inactive_account_id}@example.com",
                    account_status="invalid",
                    created_at=now,
                    updated_at=now,
                ),
                make_space("eligible"),
                make_space(
                    "bound",
                    has_payment_method=True,
                    payment_method_status="bound",
                ),
                make_space("business", space_type="business"),
                make_space("inactive_owner", owner_user_account_id=inactive_account_id),
                make_space(
                    "cooling",
                    payment_method_status="failed",
                    payment_method_attempt_count=3,
                    payment_method_cooldown_until=now + timedelta(hours=6),
                ),
            ]
        )
        session.commit()

    job_id = ""
    try:
        missing_country_response = client.post(
            "/spaces/payment-method-bind-selected-job",
            json={
                "space_ids": [space_ids["eligible"]],
                "proxy_country": "DE",
                "created_by": "test",
            },
        )
        assert missing_country_response.status_code == 409
        assert missing_country_response.json()["detail"] == {
            "message": "payment method inventory is empty",
            "pools": ["address"],
            "proxy_country": "DE",
        }

        bound_response = client.get(
            "/spaces",
            params={"q": prefix, "has_payment_method": "true"},
        )
        assert bound_response.status_code == 200
        assert [item["id"] for item in bound_response.json()["items"]] == [
            space_ids["bound"]
        ]

        unbound_response = client.get(
            "/spaces",
            params={"q": prefix, "has_payment_method": "false", "page_size": 20},
        )
        assert unbound_response.status_code == 200
        assert {item["id"] for item in unbound_response.json()["items"]} == {
            space_ids["eligible"],
            space_ids["business"],
            space_ids["inactive_owner"],
            space_ids["cooling"],
        }

        selected_response = client.post(
            "/spaces/payment-method-bind-selected-job",
            json={
                "space_ids": [
                    space_ids["eligible"],
                    space_ids["business"],
                    space_ids["bound"],
                    space_ids["inactive_owner"],
                    space_ids["cooling"],
                    f"{prefix}-missing",
                    space_ids["eligible"],
                ],
                "proxy_country": "jp",
                "created_by": "test",
            },
        )
        assert selected_response.status_code == 200
        payload = selected_response.json()
        job_id = payload["job_id"]
        assert payload["requested_count"] == 6
        assert payload["selected_count"] == 1
        assert payload["selection_skipped_count"] == 5
        assert payload["queued"] == 1
        assert {item["reason"] for item in payload["selection_skipped"]} == {
            "payment_method_personal_space_required",
            "payment_method_already_bound",
            "payment_method_owner_account_not_active",
            "payment_method_cooldown_active",
            "space_not_found",
        }

        with session_factory() as session:
            job = session.get(JobModel, job_id)
            works = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).all()
        assert job is not None
        assert len(works) == 1
        assert job.input_json["proxy_country"] == "JP"
        assert works[0].input_json["proxy_country"] == "JP"
        assert works[0].input_json["space_id"] == space_ids["eligible"]
        assert job.input_json["checkout_ui_mode"] == "custom"
        assert works[0].input_json["checkout_ui_mode"] == "custom"
        assert job.input_json["captcha_api_url"] == "https://captcha.test"
        assert works[0].input_json["captcha_api_url"] == "https://captcha.test"
        assert hashlib.sha256(job.input_json["captcha_client_key"].encode()).digest() == (
            hashlib.sha256(captcha_client_key.encode()).digest()
        )
        assert hashlib.sha256(works[0].input_json["captcha_client_key"].encode()).digest() == (
            hashlib.sha256(captcha_client_key.encode()).digest()
        )
        assert "captcha_client_key" not in selected_response.text

        duplicate_response = client.post(
            "/spaces/payment-method-bind-selected-job",
            json={"space_ids": [space_ids["eligible"]], "created_by": "test"},
        )
        assert duplicate_response.status_code == 200
        duplicate_payload = duplicate_response.json()
        assert duplicate_payload["job_id"] == ""
        assert duplicate_payload["selection_skipped"] == [
            {
                "space_id": space_ids["eligible"],
                "reason": "active_personal_payment_method_bind_job_exists",
            }
        ]
    finally:
        with session_factory() as session:
            if job_id:
                session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.execute(delete(SpaceModel).where(SpaceModel.id.in_(space_ids.values())))
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([active_account_id, inactive_account_id])
                )
            )
            session.commit()


def test_personal_promotion_check_selection_filters_invalid_spaces(
    monkeypatch: MonkeyPatch,
) -> None:
    prefix = f"test-promotion-selected-{uuid4()}"
    active_account_id = f"{prefix}-active-account"
    inactive_account_id = f"{prefix}-inactive-account"
    now = datetime.now(UTC)
    space_ids = {
        "eligible": f"{prefix}-eligible",
        "duplicate": f"{prefix}-duplicate",
        "business": f"{prefix}-business",
        "inactive_space": f"{prefix}-inactive-space",
        "missing_owner": f"{prefix}-missing-owner",
        "inactive_owner": f"{prefix}-inactive-owner",
    }

    def make_space(
        key: str,
        *,
        owner_user_account_id: str = active_account_id,
        space_type: str = "personal",
        space_status: str = "active",
    ) -> SpaceModel:
        return SpaceModel(
            id=space_ids[key],
            external_space_id=f"{prefix}-external-{key}",
            owner_user_account_id=owner_user_account_id,
            name=f"{prefix}-{key}",
            space_type=space_type,
            auth_mode="codex_oauth",
            credential_type=(
                "personal_account" if space_type == "personal" else "team_5h_weekly"
            ),
            space_status=space_status,
            created_at=now,
            updated_at=now,
        )

    session_factory = make_session_factory(make_engine(Settings()))
    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=active_account_id,
                    email=f"{active_account_id}@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=inactive_account_id,
                    email=f"{inactive_account_id}@example.com",
                    account_status="invalid",
                    created_at=now,
                    updated_at=now,
                ),
                make_space("eligible"),
                make_space("duplicate"),
                make_space("business", space_type="business"),
                make_space("inactive_space", space_status="disabled"),
                make_space("missing_owner", owner_user_account_id=""),
                make_space("inactive_owner", owner_user_account_id=inactive_account_id),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        resource_routes,
        "_active_personal_promotion_check_jobs_by_space_id",
        lambda **_kwargs: {space_ids["duplicate"]: object()},
    )
    try:
        with session_factory() as session:
            requested, selected, skipped = (
                resource_routes._select_personal_promotion_check_spaces(
                    session=session,
                    space_ids=[
                        space_ids["eligible"],
                        space_ids["duplicate"],
                        space_ids["business"],
                        space_ids["inactive_space"],
                        space_ids["missing_owner"],
                        space_ids["inactive_owner"],
                        f"{prefix}-missing",
                        space_ids["eligible"],
                    ],
                )
            )
        assert len(requested) == 7
        assert [space.id for space in selected] == [space_ids["eligible"]]
        assert {item["reason"] for item in skipped} == {
            "active_personal_promotion_check_job_exists",
            "promotion_check_personal_space_required",
            "promotion_check_space_not_active",
            "promotion_check_owner_account_missing",
            "promotion_check_owner_account_not_active",
            "space_not_found",
        }
    finally:
        with session_factory() as session:
            session.execute(delete(SpaceModel).where(SpaceModel.id.in_(space_ids.values())))
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([active_account_id, inactive_account_id])
                )
            )
            session.commit()


def test_personal_promotion_check_selected_job_normalizes_config_and_enqueues_work(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    captured: dict = {"works": []}
    selected = [SimpleNamespace(id="space-1"), SimpleNamespace(id="space-2")]

    monkeypatch.setattr(
        resource_routes,
        "_select_personal_promotion_check_spaces",
        lambda **_kwargs: (
            ["space-1", "space-2", "space-missing"],
            selected,
            [{"space_id": "space-missing", "reason": "space_not_found"}],
        ),
    )

    def start_work_job(**kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["works"].append(kwargs)

    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {
            "job_id": "job-1",
            "job_status": "running",
            "run_id": "run-1",
            "work_count": 7,
            "selected_count": 2,
            "queued": 2,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    response = TestClient(create_app()).post(
        "/spaces/promotion-check-selected-job",
        json={
            "space_ids": ["space-1", "space-2", "space-missing"],
            "proxy_country": "jp",
            "work_count": 7,
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["requested_count"] == 3
    assert payload["selected_count"] == 2
    assert payload["selection_skipped_count"] == 1
    assert captured["start"]["job_type"] == "space.personal_promotion_check.selected"
    assert captured["start"]["input_json"]["proxy_country"] == "JP"
    assert captured["start"]["input_json"]["work_count"] == 7
    assert [work["execution_key"] for work in captured["works"]] == [
        "personal-promotion-check:space-1",
        "personal-promotion-check:space-2",
    ]
    assert all(work["input_json"]["proxy_country"] == "JP" for work in captured["works"])


def test_personal_subscription_refresh_selected_job_enqueues_eligible_spaces(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    captured: dict = {"works": []}
    selected = [SimpleNamespace(id="space-1"), SimpleNamespace(id="space-2")]
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_subscription_refresh_spaces",
        lambda **_kwargs: (
            ["space-1", "space-2", "space-missing"],
            selected,
            [{"space_id": "space-missing", "reason": "space_not_found"}],
        ),
    )

    def start_work_job(**kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["works"].append(kwargs)

    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {
            "job_id": "job-1",
            "job_status": "running",
            "run_id": "run-1",
            "work_count": 2,
            "selected_count": 2,
            "queued": 2,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    response = TestClient(create_app()).post(
        "/spaces/subscription-refresh-selected-job",
        json={
            "space_ids": ["space-1", "space-2", "space-missing"],
            "work_count": 2,
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["requested_count"] == 3
    assert payload["selected_count"] == 2
    assert payload["selection_skipped_count"] == 1
    assert payload["selection_skipped"] == [
        {"space_id": "space-missing", "reason": "space_not_found"}
    ]
    assert captured["start"]["job_type"] == "space.personal_subscription_refresh.selected"
    assert captured["start"]["input_json"]["work_count"] == 2
    assert [work["execution_key"] for work in captured["works"]] == [
        "personal-subscription-refresh:space-1",
        "personal-subscription-refresh:space-2",
    ]
    assert all(
        work["work_type"] == "space.personal_subscription_refresh.space"
        for work in captured["works"]
    )


def test_personal_plus_checkout_single_job_accepts_space_without_local_promotion(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}
    space = SimpleNamespace(
        id="space-1",
        owner_user_account_id="user-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        has_promotion=False,
        promotion_id="",
    )
    account = SimpleNamespace(account_status="active")

    class Session:
        committed = False

        @staticmethod
        def get(model, row_id):
            if model is SpaceModel and row_id == "space-1":
                return space
            if model is UserAccountModel and row_id == "user-1":
                return account
            raise AssertionError((model, row_id))

        def commit(self):
            self.committed = True

    def start_work_job(**kwargs):
        captured["job"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["work"] = kwargs

    monkeypatch.setattr(
        resource_routes,
        "get_settings",
        lambda: SimpleNamespace(
            personal_plus_checkout_captcha_api_url="",
            personal_plus_checkout_captcha_client_key="",
        ),
    )
    monkeypatch.setattr(
        resource_routes,
        "_active_work_job_for_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {"job_id": "job-1", "job_status": "running"},
    )
    session = Session()

    result = resource_routes.create_personal_plus_checkout_job(
        "space-1",
        resource_routes.PersonalPlusCheckoutJobRequest(),
        session,
    )

    assert result["job_id"] == "job-1"
    assert session.committed is True
    assert captured["job"]["input_json"]["promo_campaign_id"] == "plus-1-month-free"
    assert captured["work"]["input_json"]["promo_campaign_id"] == "plus-1-month-free"


def test_personal_paypal_agreement_single_job_accepts_space_without_local_promotion(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}
    space = SimpleNamespace(
        id="space-1",
        owner_user_account_id="user-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        has_promotion=False,
        promotion_id="",
    )
    account = SimpleNamespace(account_status="active", access_token="access-token")

    class Session:
        committed = False

        @staticmethod
        def get(model, row_id):
            if model is SpaceModel and row_id == "space-1":
                return space
            if model is UserAccountModel and row_id == "user-1":
                return account
            raise AssertionError((model, row_id))

        def commit(self):
            self.committed = True

    def start_work_job(**kwargs):
        captured["job"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["work"] = kwargs

    monkeypatch.setattr(
        resource_routes,
        "_active_work_job_for_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {"job_id": "job-1", "job_status": "running"},
    )
    session = Session()

    result = resource_routes.create_personal_paypal_link_job(
        "space-1",
        resource_routes.PersonalPayPalLinkJobRequest(
            execute_agreement=True,
            agreement_country="US",
            agreement_proxy_country="US",
        ),
        session,
    )

    assert result["job_id"] == "job-1"
    assert session.committed is True
    assert captured["job"]["input_json"]["apply_promotion"] is True
    assert captured["job"]["input_json"]["promo_campaign_id"] == "plus-1-month-free"
    assert captured["job"]["input_json"]["execute_agreement"] is True
    assert captured["work"]["input_json"]["promo_campaign_id"] == "plus-1-month-free"


def test_personal_paypal_link_selected_job_enqueues_each_selected_space(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    captured: dict = {"works": []}
    selected = [SimpleNamespace(id="space-1"), SimpleNamespace(id="space-2")]
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_paypal_link_spaces",
        lambda **_kwargs: (
            ["space-1", "space-2", "space-missing"],
            selected,
            [{"space_id": "space-missing", "reason": "space_not_found"}],
        ),
    )

    def start_work_job(**kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["works"].append(kwargs)

    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {
            "job_id": "job-1",
            "job_status": "running",
            "run_id": "run-1",
            "work_count": 2,
            "selected_count": 2,
            "queued": 2,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    response = TestClient(create_app()).post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1", "space-2", "space-missing"],
            "proxy_country": "jp",
            "checkout_proxy_country": "br",
            "update_proxy_country": "br",
            "billing_country": "jp",
            "currency": "usd",
            "apply_promotion": True,
            "promo_campaign_id": "plus-1-month-free",
            "checkout_ui_mode": "hosted",
            "execute_agreement": True,
            "agreement_country": "jp",
            "agreement_proxy_country": "us",
            "agreement_buyer_mode": "original",
            "agreement_sms_country": "43",
            "agreement_max_card_attempts": 9,
            "agreement_finalize_checkout": False,
            "work_count": 1,
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["requested_count"] == 3
    assert payload["selected_count"] == 2
    assert payload["selection_skipped_count"] == 1
    assert captured["start"]["job_type"] == "space.personal_paypal_link.tick"
    assert captured["start"]["input_json"]["proxy_country"] == "BR"
    assert captured["start"]["input_json"]["checkout_proxy_country"] == "BR"
    assert captured["start"]["input_json"]["update_proxy_country"] == "BR"
    assert captured["start"]["input_json"]["billing_country"] == "JP"
    assert captured["start"]["input_json"]["currency"] == "USD"
    assert captured["start"]["input_json"]["checkout_attempt_mode"] == "new"
    assert captured["start"]["input_json"]["execute_agreement"] is True
    assert captured["start"]["input_json"]["agreement_country"] == "JP"
    assert captured["start"]["input_json"]["agreement_proxy_country"] == "US"
    assert captured["start"]["input_json"]["agreement_buyer_mode"] == "original"
    assert captured["start"]["input_json"]["agreement_sms_country"] == "43"
    assert captured["start"]["input_json"]["agreement_max_card_attempts"] == 9
    assert captured["start"]["input_json"]["agreement_finalize_checkout"] is False
    assert captured["start"]["input_json"]["work_count"] == 1
    assert [work["execution_key"] for work in captured["works"]] == [
        "personal-paypal-link:space-1",
        "personal-paypal-link:space-2",
    ]
    assert all(
        work["input_json"]["proxy_country"] == "BR" for work in captured["works"]
    )
    assert all(
        work["input_json"]["checkout_proxy_country"] == "BR"
        for work in captured["works"]
    )
    assert all(
        work["input_json"]["update_proxy_country"] == "BR"
        for work in captured["works"]
    )
    assert all(
        work["input_json"]["billing_country"] == "JP"
        for work in captured["works"]
    )
    assert all(work["input_json"]["currency"] == "USD" for work in captured["works"])
    assert all(
        work["input_json"]["checkout_attempt_mode"] == "new"
        for work in captured["works"]
    )
    agreement_fields = {
        "execute_agreement": True,
        "agreement_country": "JP",
        "agreement_proxy_country": "US",
        "agreement_buyer_mode": "original",
        "agreement_sms_country": "43",
        "agreement_max_card_attempts": 9,
        "agreement_finalize_checkout": False,
    }
    assert all(
        {
            field: work["input_json"][field]
            for field in agreement_fields
        }
        == agreement_fields
        for work in captured["works"]
    )


def test_personal_plus_checkout_selected_job_reuses_checkout_proxy_and_work_count(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    captured: dict = {"works": []}
    selected = [SimpleNamespace(id="space-1"), SimpleNamespace(id="space-2")]
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_plus_checkout_spaces",
        lambda **_kwargs: (
            ["space-1", "space-2", "space-missing"],
            selected,
            [{"space_id": "space-missing", "reason": "space_not_found"}],
        ),
    )

    def start_work_job(**kwargs):
        captured["start"] = kwargs
        return SimpleNamespace(id="job-1"), SimpleNamespace(id="run-1")

    class CapturingWorkQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            captured["works"].append(kwargs)

    monkeypatch.setattr(resource_routes, "_start_work_job", start_work_job)
    monkeypatch.setattr(resource_routes, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(
        resource_routes,
        "_work_job_summary_response",
        lambda **_kwargs: {
            "job_id": "job-1",
            "job_status": "running",
            "run_id": "run-1",
            "work_count": 30,
            "selected_count": 2,
            "queued": 2,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    response = TestClient(create_app()).post(
        "/spaces/plus-checkout-selected-job",
        json={
            "space_ids": ["space-1", "space-2", "space-missing"],
            "proxy_country": "de",
            "checkout_proxy_country": "de",
            "update_proxy_country": "de",
            "promo_campaign_id": "plus-1-month-free",
            "work_count": 30,
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["requested_count"] == 3
    assert payload["selected_count"] == 2
    assert payload["selection_skipped_count"] == 1
    assert captured["start"]["job_type"] == "space.personal_plus_checkout.tick"
    assert captured["start"]["input_json"]["work_count"] == 30
    assert captured["start"]["input_json"]["proxy_country"] == "DE"
    assert captured["start"]["input_json"]["checkout_proxy_country"] == "DE"
    assert captured["start"]["input_json"]["update_proxy_country"] == "DE"
    assert [work["execution_key"] for work in captured["works"]] == [
        "personal-plus-checkout:space-1",
        "personal-plus-checkout:space-2",
    ]
    assert all(work["input_json"]["proxy_country"] == "DE" for work in captured["works"])
    assert all(
        work["input_json"]["checkout_proxy_country"] == "DE"
        for work in captured["works"]
    )
    assert all(
        work["input_json"]["update_proxy_country"] == "DE"
        for work in captured["works"]
    )


def test_personal_plus_checkout_selection_accepts_space_without_local_promotion() -> None:
    space = SimpleNamespace(
        id="space-1",
        owner_user_account_id="user-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        has_promotion=False,
        promotion_id="",
        has_payment_method=False,
        payment_method_status="unbound",
    )
    account = SimpleNamespace(
        id="user-1",
        account_status="active",
        access_token="access-token",
        cookie_header="",
        auth_cookie_header="",
    )

    class ScalarRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class Session:
        calls = 0

        def scalars(self, _statement):
            type(self).calls += 1
            return ScalarRows(
                {
                    1: [space],
                    2: [account],
                    3: [],
                }[type(self).calls]
            )

    requested, selected, skipped = (
        resource_routes._select_personal_plus_checkout_spaces(
            session=Session(),
            space_ids=["space-1"],
        )
    )

    assert requested == ["space-1"]
    assert selected == [space]
    assert skipped == []


def test_personal_paypal_link_selection_accepts_space_without_local_promotion() -> None:
    space = SimpleNamespace(
        id="space-1",
        owner_user_account_id="user-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        has_promotion=False,
        promotion_id="",
    )
    account = SimpleNamespace(
        id="user-1",
        account_status="active",
        access_token="access-token",
    )

    class ScalarRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class Session:
        calls = 0

        def scalars(self, _statement):
            type(self).calls += 1
            return ScalarRows(
                {
                    1: [space],
                    2: [account],
                    3: [],
                }[type(self).calls]
            )

    requested, selected, skipped = (
        resource_routes._select_personal_paypal_link_spaces(
            session=Session(),
            space_ids=["space-1"],
            apply_promotion=True,
        )
    )

    assert requested == ["space-1"]
    assert selected == [space]
    assert skipped == []


def test_personal_plus_checkout_selected_job_rejects_proxy_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_plus_checkout_spaces",
        lambda **_kwargs: (["space-1"], [SimpleNamespace(id="space-1")], []),
    )

    response = TestClient(create_app()).post(
        "/spaces/plus-checkout-selected-job",
        json={
            "space_ids": ["space-1"],
            "checkout_proxy_country": "us",
            "update_proxy_country": "jp",
            "work_count": 1,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "update_proxy_country must match checkout_proxy_country"
    }


def test_personal_paypal_link_agreement_api_defaults_are_backward_compatible() -> None:
    request = resource_routes.PersonalPayPalLinkJobRequest()

    assert resource_routes._personal_paypal_agreement_config(request) == {
        "execute_agreement": False,
        "agreement_country": None,
        "agreement_proxy_country": None,
        "agreement_buyer_mode": "identity_elevation",
        "agreement_sms_country": "",
        "agreement_max_card_attempts": 5,
        "agreement_finalize_checkout": True,
    }


def test_personal_paypal_link_accepts_tr_billing_country() -> None:
    request = resource_routes.PersonalPayPalLinkJobRequest(
        proxy_country="US",
        billing_country="tr",
    )

    assert resource_routes._personal_paypal_link_country_config(request) == (
        "TR",
        "US",
        "US",
        "USD",
    )


def test_personal_gcash_link_keeps_ph_contract_and_configured_checkout_proxy() -> None:
    request = resource_routes.PersonalPayPalLinkJobRequest(
        payment_method_type="gcash",
        proxy_country="US",
        checkout_proxy_country="DE",
        update_proxy_country="DE",
        billing_country="DE",
        currency="EUR",
        checkout_ui_mode="hosted",
    )

    assert resource_routes._personal_paypal_link_country_config(request) == (
        "PH",
        "DE",
        "DE",
        "PHP",
    )


def test_personal_paypal_link_selected_job_rejects_invalid_agreement_config(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_paypal_link_spaces",
        lambda **_kwargs: (["space-1"], [SimpleNamespace(id="space-1")], []),
    )
    client = TestClient(create_app())

    invalid_country = client.post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1"],
            "execute_agreement": True,
            "agreement_country": "USA",
        },
    )
    missing_country = client.post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1"],
            "execute_agreement": True,
        },
    )
    invalid_sms_country = client.post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1"],
            "agreement_sms_country": "18A",
        },
    )
    gcash_agreement = client.post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1"],
            "payment_method_type": "gcash",
            "execute_agreement": True,
            "agreement_country": "US",
            "agreement_proxy_country": "US",
        },
    )

    assert invalid_country.status_code == 400
    assert invalid_country.json() == {
        "detail": "agreement_country must be a two-letter country code"
    }
    assert missing_country.status_code == 400
    assert missing_country.json() == {
        "detail": "agreement_country is required when execute_agreement is true"
    }
    assert invalid_sms_country.status_code == 400
    assert invalid_sms_country.json() == {
        "detail": "agreement_sms_country must contain digits only"
    }
    assert gcash_agreement.status_code == 400
    assert gcash_agreement.json() == {
        "detail": "PayPal agreement execution requires payment_method_type=paypal"
    }


def test_personal_paypal_link_selected_job_rejects_update_proxy_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    monkeypatch.setattr(
        resource_routes,
        "_select_personal_paypal_link_spaces",
        lambda **_kwargs: (
            ["space-1"],
            [SimpleNamespace(id="space-1")],
            [],
        ),
    )

    response = TestClient(create_app()).post(
        "/spaces/paypal-link-selected-job",
        json={
            "space_ids": ["space-1"],
            "billing_country": "de",
            "checkout_proxy_country": "br",
            "update_proxy_country": "th",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "update_proxy_country must match checkout_proxy_country"
    }


def test_personal_subscription_refresh_work_uses_stored_auth_and_writes_snapshot(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {"commit_count": 0}
    prior_session_refresh = datetime(2026, 1, 2, tzinfo=UTC)
    space = SimpleNamespace(
        id="space-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        owner_user_account_id="account-1",
        external_space_id="personal-account-1",
        plan_type="plus",
        seats_entitled=1,
        seat_limit=1,
        seats_in_use=1,
        raw_space_json={"before": True},
        last_subscription_sync_at=None,
        updated_at=None,
    )
    account = SimpleNamespace(
        id="account-1",
        email="selected@example.com",
        account_status="active",
        access_token="db-access-token",
        cookie_header="   ",
        auth_cookie_header="auth=fallback-cookie",
        last_session_refresh_at=prior_session_refresh,
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, key):
            if model is SpaceModel and key == "space-1":
                return space
            if model is UserAccountModel and key == "account-1":
                return account
            return None

        def commit(self):
            captured["commit_count"] += 1

    class FakeProvider:
        def fetch_subscription(self, **kwargs):
            captured["fetch"] = kwargs
            return {
                "plan_type": "free",
                "seats_entitled": 0,
                "seats_in_use": 0,
                "has_active_subscription": False,
            }

    def resolve_proxy(**kwargs):
        captured["proxy"] = kwargs
        return SimpleNamespace(
            proxy_url="http://us-proxy.example:8080",
            country_code="US",
            provider="cliproxy",
            sid_source="email_sha256",
            probe_attempts=1,
        )

    monkeypatch.setattr(handlers, "_openai_plugin", lambda _settings: FakeProvider())
    monkeypatch.setattr(handlers, "resolve_cliproxy_proxy", resolve_proxy)
    runner = handlers.JobRunner(FakeSession)
    handlers.register_core_handlers(
        runner,
        session_factory=FakeSession,
        settings=Settings(),
    )

    assert "space.personal_subscription_refresh.selected" in runner._handlers
    assert "space.personal_subscription_refresh.space" in runner._work_handlers
    result = runner._work_handlers["space.personal_subscription_refresh.space"](
        None,
        {"space_id": "space-1", "_run_id": "run-1"},
    )

    assert captured["proxy"] == {
        "email": "selected@example.com",
        "country_code": "US",
    }
    assert captured["fetch"] == {
        "access_token": "db-access-token",
        "account_id": "personal-account-1",
        "cookie_header": "auth=fallback-cookie",
        "proxy_url": "http://us-proxy.example:8080",
    }
    assert captured["commit_count"] == 1
    assert account.last_session_refresh_at == prior_session_refresh
    assert space.plan_type == "free"
    assert space.seats_entitled == 0
    assert space.seat_limit == 0
    assert space.seats_in_use == 0
    assert space.raw_space_json["has_active_subscription"] is False
    assert space.last_subscription_sync_at is not None
    assert space.updated_at == space.last_subscription_sync_at
    assert result["subscription_status"] == "refreshed"
    assert result["plan_type"] == "free"


def test_personal_subscription_refresh_work_treats_404_as_no_subscription(
    monkeypatch: MonkeyPatch,
) -> None:
    captured = {"commit_count": 0}
    space = SimpleNamespace(
        id="space-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        owner_user_account_id="account-1",
        external_space_id="personal-account-1",
        raw_space_json={"before": True},
        last_subscription_sync_at=None,
    )
    account = SimpleNamespace(
        id="account-1",
        email="selected@example.com",
        account_status="active",
        access_token="db-access-token",
        cookie_header="primary=cookie",
        auth_cookie_header="auth=fallback-cookie",
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, key):
            if model is SpaceModel and key == "space-1":
                return space
            if model is UserAccountModel and key == "account-1":
                return account
            return None

        def commit(self):
            captured["commit_count"] += 1

    class MissingSubscriptionProvider:
        def fetch_subscription(self, **_kwargs):
            raise handlers.OpenAIChatGPTClientError(
                "chatgpt backend request failed: http_status=404 body_snippet={}"
            )

    monkeypatch.setattr(
        handlers,
        "resolve_cliproxy_proxy",
        lambda **_kwargs: SimpleNamespace(proxy_url="http://us-proxy.example:8080"),
    )
    monkeypatch.setattr(
        handlers,
        "_openai_plugin",
        lambda _settings: MissingSubscriptionProvider(),
    )

    result = handlers._run_personal_subscription_refresh_work(
        session_factory=FakeSession,
        settings=Settings(),
        input_json={"space_id": "space-1"},
    )

    assert result["subscription_status"] == "no_subscription"
    assert result["http_status"] == 404
    assert captured["commit_count"] == 0
    assert space.raw_space_json == {"before": True}
    assert space.last_subscription_sync_at is None


def test_personal_promotion_check_work_uses_selected_space_and_jp_proxy(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}
    space = SimpleNamespace(
        id="space-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        owner_user_account_id="account-1",
    )
    account = SimpleNamespace(
        id="account-1",
        email="selected@example.com",
        account_status="active",
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, key):
            if model is SpaceModel and key == "space-1":
                return space
            if model is UserAccountModel and key == "account-1":
                return account
            return None

    def resolve_proxy(**kwargs):
        captured["proxy"] = kwargs
        return SimpleNamespace(
            proxy_url="http://jp-proxy.example:8080",
            country_code="JP",
            provider="cliproxy",
            sid_source="email_sha256",
            probe_attempts=1,
        )

    class FakeBackfillSessionWorkflow:
        def __init__(self, **kwargs):
            captured["workflow_init"] = kwargs

        def probe_personal_space_promotion(self, **kwargs):
            captured["probe"] = kwargs
            return {
                "status": "succeeded",
                "has_promotion": True,
                "promotion_id": "plus-1-month-free",
                "proxy_country": "JP",
            }

    monkeypatch.setattr(handlers, "resolve_cliproxy_proxy", resolve_proxy)
    monkeypatch.setattr(handlers, "BackfillSessionWorkflow", FakeBackfillSessionWorkflow)
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())

    result = handlers._run_personal_promotion_check_work(
        session_factory=FakeSession,
        settings=Settings(),
        input_json={"space_id": "space-1", "_run_id": "run-1"},
    )

    assert captured["proxy"] == {
        "email": "selected@example.com",
        "country_code": "JP",
    }
    assert captured["probe"] == {
        "user_account_id": "account-1",
        "proxy_url": "http://jp-proxy.example:8080",
        "proxy_country": "JP",
        "space_id": "space-1",
        "run_id": "run-1",
    }
    assert result["space_id"] == "space-1"
    assert result["proxy_provider"] == "cliproxy"
    assert result["proxy_sid_source"] == "email_sha256"
    assert result["proxy_probe_attempts"] == 1
    assert result["has_promotion"] is True


def test_personal_codex_heartbeat_work_can_use_cliproxy_us(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}
    account = SimpleNamespace(id="account-1", email="heartbeat@example.com")

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, key):
            if model is UserAccountModel and key == "account-1":
                return account
            return None

    class FakeHeartbeatWorkflow:
        def __init__(self, **kwargs):
            captured["workflow"] = kwargs

        def run(self, input_):
            captured["proxy_url"] = captured["workflow"]["proxy_resolver"]("account-1")
            captured["proxy_url_reused"] = captured["workflow"]["proxy_resolver"](
                "account-1"
            )
            return {"space_credential_id": input_.space_credential_id, "action": "ok"}

    def resolve_proxy(**kwargs):
        captured["proxy"] = kwargs
        return SimpleNamespace(proxy_url="http://us-cliproxy.example:443")

    monkeypatch.setattr(handlers, "resolve_cliproxy_proxy", resolve_proxy)
    monkeypatch.setattr(
        handlers,
        "PersonalCodexCredentialHeartbeatWorkflow",
        FakeHeartbeatWorkflow,
    )
    monkeypatch.setattr(handlers, "_openai_plugin", lambda _settings: object())

    result = handlers._run_personal_codex_credential_heartbeat_work(
        session_factory=FakeSession,
        settings=Settings(),
        input_json={
            "space_credential_id": "credential-1",
            "proxy_mode": "cliproxy",
            "proxy_country": "US",
        },
    )

    assert result == {"space_credential_id": "credential-1", "action": "ok"}
    assert captured["proxy"] == {
        "email": "heartbeat@example.com",
        "country_code": "US",
    }
    assert captured["proxy_url"] == "http://us-cliproxy.example:443"
    assert captured["proxy_url_reused"] == "http://us-cliproxy.example:443"


def test_personal_codex_authorization_work_uses_proxy_override(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict = {}
    target = SimpleNamespace(
        user_account_id="account-1",
        space_id="space-1",
        space_membership_id="membership-1",
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _stmt):
            return "credential-1"

    class FakeBackfillRtWorkflow:
        def __init__(self, **kwargs):
            captured["workflow"] = kwargs

        def run(self, **kwargs):
            captured["run"] = kwargs

    monkeypatch.setattr(
        handlers,
        "resolve_personal_codex_authorization_target",
        lambda **_kwargs: (target, ""),
    )
    monkeypatch.setattr(handlers, "BackfillRtWorkflow", FakeBackfillRtWorkflow)
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    monkeypatch.setattr(
        handlers,
        "_personal_codex_grizzly_phone_provider",
        lambda **_kwargs: None,
    )

    result = handlers._run_personal_codex_authorization_work(
        session_factory=FakeSession,
        settings=Settings(),
        input_json={
            "space_membership_id": "membership-1",
            "proxy_url_override": "http://us-cliproxy.example:443",
        },
    )

    assert result["space_credential_id"] == "credential-1"
    assert captured["run"]["proxy_url_override"] == "http://us-cliproxy.example:443"


def test_payment_method_pool_imports_each_pool_independently(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    prefix = f"test-payment-independent-{uuid4()}"
    full_name = f"{prefix} User"
    address_line1 = f"{prefix} Street"
    card_number = _test_luhn_card(uuid4().int)

    try:
        responses = [
            client.post(
                "/payment-method-pools/import",
                json={"names": [full_name]},
            ),
            client.post(
                "/payment-method-pools/import",
                json={
                    "addresses": [
                        f"{address_line1}, Middletown, Delaware 19709, United States"
                    ]
                },
            ),
            client.post(
                "/payment-method-pools/import",
                json={
                    "cards": [
                        f"Live | {card_number}|01|2030|123 | "
                        "[BIN: US - visa - debit] | Charge OK."
                    ]
                },
            ),
        ]

        assert [response.status_code for response in responses] == [200, 200, 200]
        assert [response.json()["inserted_count"] for response in responses] == [1, 1, 1]
        assert card_number not in responses[2].text
    finally:
        session_factory = make_session_factory(make_engine(Settings()))
        with session_factory() as session:
            session.execute(
                delete(PaymentNamePoolModel).where(
                    PaymentNamePoolModel.normalized_name == full_name.casefold()
                )
            )
            session.execute(
                delete(PaymentAddressPoolModel).where(
                    PaymentAddressPoolModel.line1 == address_line1
                )
            )
            session.execute(
                delete(PaymentCardPoolModel).where(
                    PaymentCardPoolModel.card_fingerprint
                    == payment_card_fingerprint(card_number)
                )
            )
            session.commit()


def test_payment_method_pool_crud_api_masks_card_secrets(
    monkeypatch: MonkeyPatch,
) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    prefix = f"test-payment-crud-{uuid4()}"
    card_number = _test_luhn_card(uuid4().int)
    name_id = ""
    address_id = ""
    card_id = ""
    session_factory = make_session_factory(make_engine(Settings()))
    try:
        name_response = client.post(
            "/payment-method-pools/names",
            json={"full_name": f"{prefix} Name"},
        )
        assert name_response.status_code == 200
        name_id = name_response.json()["id"]
        assert client.get("/payment-method-pools/names", params={"q": prefix}).json()["total"] == 1
        assert client.patch(
            f"/payment-method-pools/names/{name_id}",
            json={"name_status": "disabled"},
        ).json()["name_status"] == "disabled"

        address_response = client.post(
            "/payment-method-pools/addresses",
            json={
                "line1": f"{prefix} Street",
                "city": "New York",
                "postal_code": "10001",
                "country": "US",
            },
        )
        assert address_response.status_code == 200
        address_id = address_response.json()["id"]
        assert client.patch(
            f"/payment-method-pools/addresses/{address_id}",
            json={"city": "Boston"},
        ).json()["city"] == "Boston"

        card_response = client.post(
            "/payment-method-pools/cards",
            json={
                "card_number": card_number,
                "cvc": "123",
                "exp_month": 12,
                "exp_year": 2035,
            },
        )
        assert card_response.status_code == 200
        card_payload = card_response.json()
        card_id = card_payload["id"]
        assert "card_number" not in card_payload
        assert "cvc" not in card_payload
        assert card_payload["last4"] == card_number[-4:]
        list_payload = client.get("/payment-method-pools/cards").json()
        assert list_payload["items"][0]["card_number_masked"].endswith(card_number[-4:])
        assert card_number not in str(list_payload)
        assert client.patch(
            f"/payment-method-pools/cards/{card_id}",
            json={"card_status": "disabled"},
        ).json()["card_status"] == "disabled"
    finally:
        with session_factory() as session:
            if name_id:
                session.execute(
                    delete(PaymentNamePoolModel).where(PaymentNamePoolModel.id == name_id)
                )
            if address_id:
                session.execute(
                    delete(PaymentAddressPoolModel).where(
                        PaymentAddressPoolModel.id == address_id
                    )
                )
            if card_id:
                session.execute(
                    delete(PaymentCardPoolModel).where(PaymentCardPoolModel.id == card_id)
                )
            session.commit()


def test_personal_payment_method_tick_only_enqueues_eligible_spaces() -> None:
    prefix = f"test-payment-method-tick-{uuid4()}"
    active_account_id = f"{prefix}-active-account"
    inactive_account_id = f"{prefix}-inactive-account"
    eligible_space_id = f"{prefix}-eligible"
    space_suffixes = (
        "eligible",
        "business",
        "bound",
        "inactive-space",
        "inactive-owner",
        "attempt-limit",
        "binding",
    )
    job_ids = {suffix: f"{prefix}-job-{suffix}" for suffix in space_suffixes}
    now = datetime.now(UTC)
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))

    def make_space(
        suffix: str,
        *,
        owner_user_account_id: str = active_account_id,
        space_type: str = "personal",
        space_status: str = "active",
        has_payment_method: bool = False,
        payment_method_status: str = "missing",
        payment_method_attempt_count: int = 0,
    ) -> SpaceModel:
        return SpaceModel(
            id=f"{prefix}-{suffix}",
            external_space_id=f"{prefix}-external-{suffix}",
            owner_user_account_id=owner_user_account_id,
            name=suffix,
            space_type=space_type,
            auth_mode="codex_oauth",
            credential_type=(
                "personal_account" if space_type == "personal" else "team_5h_weekly"
            ),
            has_promotion=space_type == "personal",
            promotion_id=("plus-1-month-free" if space_type == "personal" else ""),
            space_status=space_status,
            has_payment_method=has_payment_method,
            payment_method_status=payment_method_status,
            payment_method_attempt_count=payment_method_attempt_count,
            created_at=now,
            updated_at=now,
        )

    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=active_account_id,
                    email=f"{active_account_id}@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=inactive_account_id,
                    email=f"{inactive_account_id}@example.com",
                    account_status="invalid",
                    created_at=now,
                    updated_at=now,
                ),
                make_space("eligible"),
                make_space("business", space_type="business"),
                make_space(
                    "bound",
                    has_payment_method=True,
                    payment_method_status="bound",
                ),
                make_space("inactive-space", space_status="disabled"),
                make_space("inactive-owner", owner_user_account_id=inactive_account_id),
                make_space(
                    "attempt-limit",
                    payment_method_status="failed",
                    payment_method_attempt_count=3,
                ),
                make_space(
                    "binding",
                    payment_method_status="binding",
                    payment_method_attempt_count=1,
                ),
                *[
                    JobModel(
                        id=job_id,
                        type="space.personal_payment_method_bind.tick",
                        job_status="running",
                        input_json={
                            "space_id": f"{prefix}-{suffix}",
                            "limit": 10,
                            "work_count": 3,
                        },
                        created_by="test",
                        created_at=now,
                        updated_at=now,
                    )
                    for suffix, job_id in job_ids.items()
                ],
            ]
        )
        session.commit()

    try:
        results = {
                suffix: handlers._run_personal_payment_method_bind_tick_job(
                    session_factory=session_factory,
                    settings=settings,
                    input_json={
                    "space_id": f"{prefix}-{suffix}",
                    "limit": 10,
                    "work_count": 3,
                    "_job_id": job_id,
                    "_run_id": f"{prefix}-run-{suffix}",
                },
            )
            for suffix, job_id in job_ids.items()
        }
        second = handlers._run_personal_payment_method_bind_tick_job(
            session_factory=session_factory,
            settings=settings,
            input_json={
                "space_id": eligible_space_id,
                "limit": 10,
                "work_count": 3,
                "_job_id": job_ids["eligible"],
                "_run_id": f"{prefix}-run-eligible",
            },
        )

        with session_factory() as session:
            works = (
                session.query(WorkItemModel)
                .filter(WorkItemModel.job_id.in_(list(job_ids.values())))
                .all()
            )

        assert results["eligible"]["selected_count"] == 1
        assert results["eligible"]["queued"] == 1
        assert results["eligible"]["work_count"] == 3
        assert all(
            results[suffix]["selected_count"] == 0
            for suffix in space_suffixes
            if suffix != "eligible"
        )
        assert second["selected_count"] == 1
        assert len(works) == 1
        assert works[0].work_type == "space.personal_payment_method_bind.space"
        assert works[0].execution_key == f"personal-payment-method:{eligible_space_id}"
        assert works[0].input_json["space_id"] == eligible_space_id
    finally:
        with session_factory() as session:
            session.execute(delete(JobModel).where(JobModel.id.in_(list(job_ids.values()))))
            session.execute(delete(SpaceModel).where(SpaceModel.id.like(f"{prefix}-%")))
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([active_account_id, inactive_account_id])
                )
            )
            session.commit()


def test_account_and_space_session_recency_filters(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    prefix = f"test-session-recency-{uuid4()}"
    account_ids = {
        "recent": f"{prefix}-account-recent",
        "stale": f"{prefix}-account-stale",
        "never": f"{prefix}-account-never",
    }
    space_ids = {
        "recent": f"{prefix}-space-recent",
        "stale": f"{prefix}-space-stale",
        "never": f"{prefix}-space-never",
        "business": f"{prefix}-space-business",
    }
    membership_ids = {
        "recent": f"{prefix}-membership-recent",
        "stale": f"{prefix}-membership-stale",
        "never": f"{prefix}-membership-never",
        "business": f"{prefix}-membership-business",
    }
    admin_session_id = f"{prefix}-admin-session"
    now = datetime.now(UTC)
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))

    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=account_ids["recent"],
                    email=f"{prefix}-recent@example.com",
                    account_status="active",
                    codex_select_channel_required=True,
                    codex_select_channel_detected_at=now - timedelta(hours=1),
                    last_session_refresh_at=now - timedelta(hours=4),
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=account_ids["stale"],
                    email=f"{prefix}-stale@example.com",
                    account_status="active",
                    last_session_refresh_at=now - timedelta(hours=10),
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=account_ids["never"],
                    email=f"{prefix}-never@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                TeamAdminSessionModel(
                    id=admin_session_id,
                    admin_email=f"{prefix}-admin@example.com",
                    raw_session_json={},
                    imported_at=now - timedelta(hours=5),
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        for key in ("recent", "stale", "never"):
            session.add(
                SpaceModel(
                    id=space_ids[key],
                    external_space_id=f"{prefix}-external-{key}",
                    owner_user_account_id=account_ids[key],
                    name=f"{prefix}-{key}",
                    space_type="personal",
                    auth_mode="codex_oauth",
                    credential_type="personal_account",
                    plan_type=(
                        "plus" if key == "recent" else "" if key == "never" else "free"
                    ),
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            SpaceModel(
                id=space_ids["business"],
                external_space_id=f"{prefix}-external-business",
                name=f"{prefix}-business",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_monthly",
                plan_type="team",
                space_status="active",
                source_admin_session_id=admin_session_id,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        for key in ("recent", "stale", "never"):
            session.add(
                SpaceMembershipModel(
                    id=membership_ids[key],
                    space_id=space_ids[key],
                    user_account_id=account_ids[key],
                    membership_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            SpaceMembershipModel(
                id=membership_ids["business"],
                space_id=space_ids["business"],
                user_account_id=account_ids["recent"],
                membership_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    try:
        account_response = client.get(
            "/user-accounts",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert account_response.status_code == 200
        account_items = {item["id"]: item for item in account_response.json()["items"]}
        assert set(account_items) == {
            account_ids["recent"]
        }
        assert account_items[account_ids["recent"]]["personal_plan_type"] == "plus"
        assert account_items[account_ids["recent"]]["codex_select_channel_required"] is True
        assert account_items[account_ids["recent"]]["codex_select_channel_detected_at"]

        account_batch_response = client.get(
            "/user-accounts",
            params={
                "email_list": (
                    f" {prefix}-stale@example.com\n"
                    f"{prefix}-NEVER@example.com\n"
                    f"{prefix}-stale@example.com "
                ),
                "page_size": 20,
            },
        )
        assert account_batch_response.status_code == 200
        assert {
            item["id"] for item in account_batch_response.json()["items"]
        } == {account_ids["stale"], account_ids["never"]}

        account_select_channel_response = client.get(
            "/user-accounts",
            params={
                "q": prefix,
                "codex_select_channel_required": "true",
                "page_size": 20,
            },
        )
        assert account_select_channel_response.status_code == 200
        assert {
            item["id"] for item in account_select_channel_response.json()["items"]
        } == {account_ids["recent"]}

        account_plan_response = client.get(
            "/user-accounts",
            params={"q": prefix, "personal_plan_type": "plus", "page_size": 20},
        )
        assert account_plan_response.status_code == 200
        assert {item["id"] for item in account_plan_response.json()["items"]} == {
            account_ids["recent"]
        }

        account_unknown_plan_response = client.get(
            "/user-accounts",
            params={"q": prefix, "personal_plan_type": "unknown", "page_size": 20},
        )
        assert account_unknown_plan_response.status_code == 200
        assert {
            item["id"] for item in account_unknown_plan_response.json()["items"]
        } == {account_ids["never"]}

        account_plan_sort_response = client.get(
            "/user-accounts",
            params={"q": prefix, "sort": "personal_plan_type", "page_size": 20},
        )
        assert account_plan_sort_response.status_code == 200
        account_plan_types = [
            item["personal_plan_type"]
            for item in account_plan_sort_response.json()["items"]
        ]
        assert account_plan_types == sorted(account_plan_types)

        account_never_response = client.get(
            "/user-accounts",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in account_never_response.json()["items"]} == {
            account_ids["never"]
        }

        space_response = client.get(
            "/spaces",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert space_response.status_code == 200
        space_items = {item["id"]: item for item in space_response.json()["items"]}
        assert set(space_items) == {space_ids["recent"], space_ids["business"]}
        assert space_items[space_ids["recent"]]["plan_type"] == "plus"
        assert space_items[space_ids["recent"]]["last_session_refresh_at"]
        assert space_items[space_ids["business"]]["last_session_refresh_at"]

        space_batch_response = client.get(
            "/spaces",
            params={
                "email_list": f"{prefix}-recent@example.com\n{prefix}-ADMIN@example.com",
                "page_size": 20,
            },
        )
        assert space_batch_response.status_code == 200
        assert {
            item["id"] for item in space_batch_response.json()["items"]
        } == {space_ids["recent"], space_ids["business"]}

        space_never_response = client.get(
            "/spaces",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in space_never_response.json()["items"]} == {
            space_ids["never"]
        }

        space_unknown_plan_response = client.get(
            "/spaces",
            params={"q": prefix, "plan_type": "unknown", "page_size": 20},
        )
        assert space_unknown_plan_response.status_code == 200
        assert {item["id"] for item in space_unknown_plan_response.json()["items"]} == {
            space_ids["never"]
        }

        membership_response = client.get(
            "/memberships",
            params={"q": prefix, "session_recency": "within_6h", "page_size": 20},
        )
        assert membership_response.status_code == 200
        membership_items = {
            item["id"]: item for item in membership_response.json()["items"]
        }
        assert set(membership_items) == {
            membership_ids["recent"],
            membership_ids["business"],
        }
        assert membership_items[membership_ids["recent"]]["space_plan_type"] == "plus"
        assert membership_items[membership_ids["recent"]]["last_session_refresh_at"]
        assert (
            membership_items[membership_ids["recent"]]["codex_select_channel_required"]
            is True
        )

        membership_select_channel_response = client.get(
            "/memberships",
            params={
                "q": prefix,
                "codex_select_channel_required": "true",
                "page_size": 20,
            },
        )
        assert membership_select_channel_response.status_code == 200
        assert {
            item["id"] for item in membership_select_channel_response.json()["items"]
        } == {
            membership_ids["recent"],
            membership_ids["business"],
        }

        membership_plan_response = client.get(
            "/memberships",
            params={"q": prefix, "plan_type": "plus", "page_size": 20},
        )
        assert {item["id"] for item in membership_plan_response.json()["items"]} == {
            membership_ids["recent"]
        }

        membership_unknown_plan_response = client.get(
            "/memberships",
            params={"q": prefix, "plan_type": "unknown", "page_size": 20},
        )
        assert membership_unknown_plan_response.status_code == 200
        assert {
            item["id"] for item in membership_unknown_plan_response.json()["items"]
        } == {membership_ids["never"]}

        membership_never_response = client.get(
            "/memberships",
            params={"q": prefix, "session_recency": "never", "page_size": 20},
        )
        assert {item["id"] for item in membership_never_response.json()["items"]} == {
            membership_ids["never"]
        }
    finally:
        with session_factory() as session:
            session.execute(delete(SpaceModel).where(SpaceModel.id.in_(space_ids.values())))
            session.execute(
                delete(TeamAdminSessionModel).where(TeamAdminSessionModel.id == admin_session_id)
            )
            session.execute(
                delete(UserAccountModel).where(UserAccountModel.id.in_(account_ids.values()))
            )
            session.commit()


def test_legacy_team_workspace_import_route_is_not_exposed(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/team-workspaces/import", json={})

    assert response.status_code == 404


def _test_luhn_card(seed: int) -> str:
    body = "4" + f"{seed % 10**14:014d}"
    for check_digit in range(10):
        candidate = f"{body}{check_digit}"
        total = 0
        parity = len(candidate) % 2
        for index, character in enumerate(candidate):
            digit = int(character)
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        if total % 10 == 0:
            return candidate
    raise AssertionError("failed to generate test card")
