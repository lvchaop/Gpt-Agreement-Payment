from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    assert "/spaces/payment-method-bind-selected-job" in paths
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


def test_delete_selected_user_accounts(monkeypatch: MonkeyPatch) -> None:
    _disable_web_login(monkeypatch)
    client = TestClient(create_app())
    account_ids = [f"test-bulk-delete-{uuid4()}" for _ in range(2)]
    missing_id = f"test-bulk-delete-missing-{uuid4()}"
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
            "deleted_proxy_bindings": 0,
        }
        with session_factory() as session:
            assert session.get(UserAccountModel, account_ids[0]) is None
            assert session.get(UserAccountModel, account_ids[1]) is None
    finally:
        with session_factory() as session:
            session.execute(delete(UserAccountModel).where(UserAccountModel.id.in_(account_ids)))
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
                        "city": "New York",
                        "state": "NY",
                        "postal_code": "10001",
                        "country": "US",
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
            json={"created_by": "test"},
        )
        assert job_response.status_code == 200
        job_id = job_response.json()["job_id"]
        assert job_response.json()["job_status"] == "queued"

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
    monkeypatch.setattr(
        resource_routes,
        "payment_method_inventory_summary",
        lambda _session: {
            "active_name_count": 1,
            "active_address_count": 1,
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
            works = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).all()
        assert len(works) == 1
        assert works[0].input_json["space_id"] == space_ids["eligible"]

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
    )
    job_ids = {suffix: f"{prefix}-job-{suffix}" for suffix in space_suffixes}
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))

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
