from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, func, select

from refactor_app.api.routes.resources import (
    _select_new_space_credential_ids,
    _space_push_record_dict,
    space_options,
)
from refactor_app.application.workflows.space_manual_export import (
    MANUAL_EXPORT_ENDPOINT,
    _render_rows,
    export_unpushed_sub2api_jsonl,
    redownload_sub2api_jsonl,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceModel,
    SpacePushAttemptModel,
    SpacePushBindingModel,
    UserAccountModel,
)


def test_personal_export_line_reuses_current_sub2api_credentials_shape() -> None:
    now = datetime.now(UTC)
    user = SimpleNamespace(id="user-1", email="personal@example.test")
    space = SimpleNamespace(
        id="space-1",
        external_space_id="personal-space-1",
        credential_type="personal_account",
        plan_type="plus",
    )
    credential = SimpleNamespace(
        id="credential-1",
        access_token="access-1",
        id_token="id-1",
        refresh_token="refresh-1",
        account_id="chatgpt-user-1",
        token_chatgpt_account_id="personal-space-1",
        codex_client_id="client-1",
        expires_at=now,
    )

    line = _render_rows(
        rows=[(credential, space, user)],
        session=SimpleNamespace(),  # type: ignore[arg-type]
        exported_at=now,
    )[0]

    assert line["type"] == "codex"
    assert line["access_token"] == "access-1"
    assert line["refresh_token"] == "refresh-1"
    assert line["chatgpt_account_id"] == "user-1_space-1"
    assert line["last_refresh"] == now.isoformat()


def test_manual_export_removes_credentials_from_pool_and_allows_redownload() -> None:
    suffix = uuid4().hex
    user_id = f"test-export-user-{suffix}"
    space_id = f"test-export-space-{suffix}"
    credential_id = f"test-export-credential-{suffix}"
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))

    try:
        with session_factory() as session:
            session.add(
                UserAccountModel(
                    id=user_id,
                    email=f"export-{suffix}@example.test",
                    openai_user_id=f"user-{suffix}",
                    account_status="active",
                    session_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                SpaceModel(
                    id=space_id,
                    external_space_id=f"workspace-{suffix}",
                    owner_user_account_id=user_id,
                    name=f"Export {suffix}",
                    space_type="business",
                    auth_mode="backend_access_token",
                    credential_type="team_5h_weekly",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                SpaceCredentialModel(
                    id=credential_id,
                    space_id=space_id,
                    user_account_id=user_id,
                    space_membership_id=None,
                    credential_status="active",
                    access_token=f"at-{suffix}",
                    account_id=f"user-{suffix}",
                    token_chatgpt_account_id=f"workspace-{suffix}",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

        with session_factory() as session:
            matching_options = space_options(
                session=session,
                q=suffix,
                credential_type="team_5h_weekly",
            )
            nonmatching_options = space_options(
                session=session,
                q=suffix,
                credential_type="team_monthly",
            )
            assert [item["value"] for item in matching_options["items"]] == [space_id]
            assert nonmatching_options["items"] == []

            first = export_unpushed_sub2api_jsonl(
                session=session,
                credential_type="team_5h_weekly",
                space_id=space_id,
            )
            session.commit()

        first_lines = first.content.decode("utf-8").splitlines()
        assert first.exported_count == 1
        assert len(first_lines) == 1
        first_payload = json.loads(first_lines[0])
        first_credentials = first_payload["accounts"][0]["credentials"]
        assert first_credentials["access_token"] == f"at-{suffix}"
        assert first_credentials["chatgpt_account_id"] == f"{user_id}_{space_id}"
        assert first_payload["accounts"][0]["name"] == f"codex-export-{suffix}@example.test"

        with session_factory() as session:
            binding = session.get(SpacePushBindingModel, credential_id)
            assert binding is not None
            assert binding.push_status == "pushed"
            assert binding.downstream_channel_id is None
            assert binding.downstream_external_id == first.export_batch_id
            assert binding.pushed_count == 1
            record = _space_push_record_dict(session=session, binding=binding)
            assert record["distribution_mode"] == "manual_export"
            assert record["downstream_channel_name"] == "文件导出"
            assert record["export_batch_id"] == first.export_batch_id

            attempt = session.scalars(
                select(SpacePushAttemptModel).where(
                    SpacePushAttemptModel.space_credential_id == credential_id
                )
            ).one()
            assert attempt.request_endpoint == MANUAL_EXPORT_ENDPOINT
            assert attempt.attempt_status == "pushed"
            assert f"at-{suffix}" not in json.dumps(attempt.request_body_json)

            pool_ids = _select_new_space_credential_ids(
                session=session,
                credential_type="team_5h_weekly",
                excluded_ids=set(),
                limit=100,
            )
            assert credential_id not in pool_ids

            attempt_count_before = int(
                session.scalar(
                    select(func.count())
                    .select_from(SpacePushAttemptModel)
                    .where(SpacePushAttemptModel.space_credential_id == credential_id)
                )
                or 0
            )
            repeated = redownload_sub2api_jsonl(
                session=session,
                export_batch_id=first.export_batch_id,
            )
            session.commit()

        assert repeated.exported_count == 1
        repeated_payload = json.loads(repeated.content.decode("utf-8").strip())
        assert repeated_payload["accounts"][0]["credentials"]["access_token"] == f"at-{suffix}"
        assert repeated_payload["exported_at"] == first_payload["exported_at"]
        assert (
            repeated_payload["accounts"][0]["extra"]["imported_at"]
            == first_payload["accounts"][0]["extra"]["imported_at"]
        )
        assert (
            repeated_payload["accounts"][0]["extra"]["codex_usage_updated_at"]
            == first_payload["accounts"][0]["extra"]["codex_usage_updated_at"]
        )

        with session_factory() as session:
            binding = session.get(SpacePushBindingModel, credential_id)
            assert binding is not None
            assert binding.push_status == "pushed"
            assert binding.pushed_count == 1
            attempt_count_after = int(
                session.scalar(
                    select(func.count())
                    .select_from(SpacePushAttemptModel)
                    .where(SpacePushAttemptModel.space_credential_id == credential_id)
                )
                or 0
            )
            assert attempt_count_after == attempt_count_before
    finally:
        with session_factory() as session:
            session.execute(
                delete(SpacePushAttemptModel).where(
                    SpacePushAttemptModel.space_credential_id == credential_id
                )
            )
            session.execute(
                delete(SpacePushBindingModel).where(
                    SpacePushBindingModel.space_credential_id == credential_id
                )
            )
            session.execute(
                delete(SpaceCredentialModel).where(SpaceCredentialModel.id == credential_id)
            )
            session.execute(delete(SpaceModel).where(SpaceModel.id == space_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == user_id))
            session.commit()
