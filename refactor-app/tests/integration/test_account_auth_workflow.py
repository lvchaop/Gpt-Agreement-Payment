from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, inspect

from refactor_app.application.workflows.account_auth import BackfillSessionWorkflow
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import UserAccountModel


def test_backfill_session_marks_deleted_or_deactivated_account_invalid() -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-deleted-or-deactivated-account"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="deleted-account@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    workflow = BackfillSessionWorkflow(session_factory=session_factory, mail_provider=object())
    workflow._write_failure(
        user_account_id=account_id,
        error_code="RuntimeError",
        error_message=(
            'OTP 验证失败: 403 - {"error":{"message":"You do not have an account '
            "because it has been deleted or deactivated. If you believe this was an "
            'error, please contact us through our help center at help.openai.com."}}'
        ),
        now=now,
    )

    with session_factory() as session:
        account = session.get(UserAccountModel, account_id)
        assert account is not None
        assert account.account_status == "invalid"
        assert account.session_status == "dead"
        assert account.last_login_error_code == "RuntimeError"
        assert "deleted or deactivated" in account.last_login_error_message

        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_backfill_session_keeps_account_active_for_regular_failure() -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-regular-account-auth-failure"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="regular-failure@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    workflow = BackfillSessionWorkflow(session_factory=session_factory, mail_provider=object())
    workflow._write_failure(
        user_account_id=account_id,
        error_code="missing_password",
        error_message="password is required to backfill session/rt",
        now=now,
    )

    with session_factory() as session:
        account = session.get(UserAccountModel, account_id)
        assert account is not None
        assert account.account_status == "active"
        assert account.session_status == "error"
        assert account.last_login_error_code == "missing_password"

        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def _skip_if_schema_is_not_current(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("user_accounts")}
    if {"password", "session_status", "last_login_error_code"} - columns:
        pytest.skip("local Postgres schema has not applied Space migrations")
