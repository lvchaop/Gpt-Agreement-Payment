from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from refactor_app.api.routes import resources
from refactor_app.application.workflows.space_session_otp import (
    select_space_session_otp_prepare_candidates,
    space_session_otp_summary,
)
from refactor_app.application.workflows.space_session_otp_remote import (
    SessionOtpExecutorClient,
    run_remote_space_session_otp_submit,
    select_remote_session_otp_candidates,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine
from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    JobModel,
    JobRunModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)


def test_selector_only_returns_active_members_with_otp_collected_snapshot() -> None:
    engine = make_engine(Settings())
    suffix = str(uuid4())
    now = datetime.now(UTC)
    space_id = f"test-remote-otp-space-{suffix}"
    selected_account_id = f"test-remote-otp-selected-{suffix}"
    empty_otp_account_id = f"test-remote-otp-empty-{suffix}"
    pending_account_id = f"test-remote-otp-pending-{suffix}"

    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            session.add(
                SpaceModel(
                    id=space_id,
                    provider="openai_chatgpt",
                    external_space_id=f"external-{suffix}",
                    name="Remote OTP selector test",
                    space_type="business",
                    auth_mode="backend_access_token",
                    credential_type="team_monthly",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            accounts: list[tuple[str, str, str, str]] = []
            for account_id, email, snapshot_status, otp_code in (
                (
                    selected_account_id,
                    f"selected-{suffix}@example.test",
                    "otp_collected",
                    "123456",
                ),
                (
                    empty_otp_account_id,
                    f"empty-{suffix}@example.test",
                    "otp_collected",
                    "",
                ),
                (pending_account_id, f"pending-{suffix}@example.test", "otp_pending", ""),
            ):
                accounts.append((account_id, email, snapshot_status, otp_code))
                session.add(
                    UserAccountModel(
                        id=account_id,
                        email=email,
                        account_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()

            for account_id, email, snapshot_status, otp_code in accounts:
                membership_id = f"membership-{account_id}"
                session.add(
                    SpaceMembershipModel(
                        id=membership_id,
                        space_id=space_id,
                        user_account_id=account_id,
                        membership_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.add(
                    AccountSessionOtpSnapshotModel(
                        id=f"snapshot-{account_id}",
                        user_account_id=account_id,
                        source_membership_id="different-membership-is-audit-only",
                        snapshot_status=snapshot_status,
                        snapshot_json={
                            "phase": snapshot_status,
                            "email": email,
                            "otp_code": otp_code,
                            "proxy": "http://proxy.example:8080",
                        },
                        otp_code_len=len(otp_code),
                        prepared_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()

            selection = select_remote_session_otp_candidates(
                session=session,
                space_id=space_id,
            )
            summary = space_session_otp_summary(session=session, space_id=space_id)

            assert selection.eligible_count == 1
            assert selection.remaining_count == 0
            assert [candidate.user_account_id for candidate in selection.candidates] == [
                selected_account_id
            ]
            assert summary["remote_submit_snapshot_count"] == 1
            assert summary["remote_submit_eligible_count"] == 1
        finally:
            session.close()
            if transaction.is_active:
                transaction.rollback()
            engine.dispose()


def test_multi_space_selection_deduplicates_accounts_before_prepare_and_submit() -> None:
    engine = make_engine(Settings())
    suffix = str(uuid4())
    now = datetime.now(UTC)
    first_space_id = f"test-multi-otp-space-a-{suffix}"
    second_space_id = f"test-multi-otp-space-b-{suffix}"
    shared_account_id = f"test-multi-otp-shared-{suffix}"
    unique_account_id = f"test-multi-otp-unique-{suffix}"

    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            for space_id, name in (
                (first_space_id, "Multi OTP A"),
                (second_space_id, "Multi OTP B"),
            ):
                session.add(
                    SpaceModel(
                        id=space_id,
                        provider="openai_chatgpt",
                        external_space_id=f"external-{space_id}",
                        name=name,
                        space_type="business",
                        auth_mode="backend_access_token",
                        credential_type="team_monthly",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            for account_id, email in (
                (shared_account_id, f"shared-{suffix}@example.test"),
                (unique_account_id, f"unique-{suffix}@example.test"),
            ):
                session.add(
                    UserAccountModel(
                        id=account_id,
                        email=email,
                        account_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()

            for membership_id, space_id, account_id in (
                (f"membership-b-shared-{suffix}", second_space_id, shared_account_id),
                (f"membership-a-shared-{suffix}", first_space_id, shared_account_id),
                (f"membership-a-unique-{suffix}", first_space_id, unique_account_id),
            ):
                session.add(
                    SpaceMembershipModel(
                        id=membership_id,
                        space_id=space_id,
                        user_account_id=account_id,
                        membership_status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
            for account_id in (shared_account_id, unique_account_id):
                session.add(
                    AccountSessionOtpSnapshotModel(
                        id=f"snapshot-{account_id}",
                        user_account_id=account_id,
                        source_membership_id="audit-only",
                        snapshot_status="otp_collected",
                        snapshot_json={
                            "otp_code": "123456",
                            "proxy": "http://proxy.example:8080",
                        },
                        otp_code_len=6,
                        prepared_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()

            selected_space_ids = [second_space_id, first_space_id]
            prepare_candidates = select_space_session_otp_prepare_candidates(
                session=session,
                space_ids=selected_space_ids,
            )
            remote_selection = select_remote_session_otp_candidates(
                session=session,
                space_ids=selected_space_ids,
            )
            summary = space_session_otp_summary(
                session=session,
                space_ids=selected_space_ids,
            )

            assert [item.user_account_id for item in prepare_candidates] == [
                shared_account_id,
                unique_account_id,
            ]
            assert prepare_candidates[0].space_id == second_space_id
            assert prepare_candidates[0].space_membership_id == f"membership-b-shared-{suffix}"
            assert remote_selection.eligible_count == 2
            assert [item.user_account_id for item in remote_selection.candidates] == [
                shared_account_id,
                unique_account_id,
            ]
            assert summary["space_ids"] == selected_space_ids
            assert summary["prepare_candidate_count"] == 2
            assert summary["remote_submit_snapshot_count"] == 2
        finally:
            session.close()
            if transaction.is_active:
                transaction.rollback()
            engine.dispose()


def test_bridge_selects_submits_polls_and_writes_back_existing_snapshot() -> None:
    engine = make_engine(Settings())
    suffix = str(uuid4())
    now = datetime.now(UTC)
    space_id = f"test-remote-otp-e2e-space-{suffix}"
    account_id = f"test-remote-otp-e2e-account-{suffix}"
    membership_id = f"test-remote-otp-e2e-membership-{suffix}"
    snapshot_id = f"test-remote-otp-e2e-snapshot-{suffix}"

    with engine.connect() as connection:
        transaction = connection.begin()

        def session_factory() -> Session:
            return Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

        with session_factory() as session:
            session.add(
                SpaceModel(
                    id=space_id,
                    provider="openai_chatgpt",
                    external_space_id=f"external-e2e-{suffix}",
                    name="Remote OTP bridge test",
                    space_type="business",
                    auth_mode="backend_access_token",
                    credential_type="team_monthly",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                UserAccountModel(
                    id=account_id,
                    email=f"e2e-{suffix}@example.test",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        with session_factory() as session:
            session.add(
                SpaceMembershipModel(
                    id=membership_id,
                    space_id=space_id,
                    user_account_id=account_id,
                    membership_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                AccountSessionOtpSnapshotModel(
                    id=snapshot_id,
                    user_account_id=account_id,
                    source_membership_id=membership_id,
                    snapshot_status="otp_collected",
                    snapshot_json={
                        "phase": "otp_collected",
                        "email": f"e2e-{suffix}@example.test",
                        "otp_code": "654321",
                        "proxy": "http://proxy.example:8080",
                    },
                    otp_code_len=6,
                    prepared_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

        submitted_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                submitted_payloads.append(json.loads(request.content))
                return httpx.Response(202, json={"batch_id": "batch-e2e", "status": "queued"})
            return httpx.Response(
                200,
                json={
                    "batch_id": "batch-e2e",
                    "status": "succeeded",
                    "results": [
                        {
                            "item_id": snapshot_id,
                            "status": "succeeded",
                            "snapshot_patch": {
                                "phase": "otp_validated",
                                "otp_code": "",
                                "continue_url": "https://auth.openai.com/authorize/continue",
                            },
                        }
                    ],
                },
            )

        client = SessionOtpExecutorClient(
            base_url="http://executor.example",
            api_key="test-key",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        try:
            result = run_remote_space_session_otp_submit(
                session_factory=session_factory,
                space_id=space_id,
                client=client,
                poll_interval_s=0.001,
                poll_timeout_s=1,
            )

            assert result["status"] == "succeeded"
            assert result["succeeded_count"] == 1
            assert submitted_payloads[0]["items"][0]["item_id"] == snapshot_id
            with session_factory() as session:
                snapshot = session.get(AccountSessionOtpSnapshotModel, snapshot_id)
                assert snapshot is not None
                assert snapshot.snapshot_status == "otp_validated"
                assert snapshot.otp_code_len == 0
                assert snapshot.snapshot_json["continue_url"].endswith("/authorize/continue")
                assert snapshot.submitted_at is not None
        finally:
            client.close()
            if transaction.is_active:
                transaction.rollback()
            engine.dispose()


def test_active_otp_job_lookup_repairs_terminal_parent_status() -> None:
    engine = make_engine(Settings())
    suffix = str(uuid4())
    now = datetime.now(UTC)
    space_id = f"test-remote-otp-job-space-{suffix}"
    job_id = f"test-remote-otp-job-{suffix}"
    run_id = f"test-remote-otp-run-{suffix}"

    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            session.add(
                JobModel(
                    id=job_id,
                    type="account.session_otp.remote_submit.bulk",
                    job_status="running",
                    input_json={"space_id": space_id},
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            session.add(
                JobRunModel(
                    id=run_id,
                    job_id=job_id,
                    run_status="running",
                    attempt=1,
                    started_at=now,
                    output_json={},
                )
            )
            for index, status in enumerate(("succeeded", "failed")):
                session.add(
                    WorkItemModel(
                        id=f"test-remote-otp-work-{index}-{suffix}",
                        job_id=job_id,
                        work_type="account.session_otp.remote_submit",
                        work_status=status,
                        input_json={"space_id": space_id},
                        output_json={},
                        finished_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()

            active = resources._space_session_otp_active_job_dict(
                session=session,
                space_id=space_id,
            )

            assert active == {}
            assert session.get(JobModel, job_id).job_status == "failed"
            assert session.get(JobRunModel, run_id).run_status == "failed"
        finally:
            session.close()
            if transaction.is_active:
                transaction.rollback()
            engine.dispose()
