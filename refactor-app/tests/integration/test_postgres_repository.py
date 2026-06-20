from __future__ import annotations

from datetime import UTC, datetime

from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import UserAccountModel
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork


def test_user_account_repository_round_trip() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    account_id = "test-user-account-repository-round-trip"
    now = datetime.now(UTC)

    with UnitOfWork(session_factory) as uow:
        assert uow.user_accounts is not None
        existing = uow.user_accounts.get(account_id)
        if existing is not None:
            uow.session.delete(existing)

    with UnitOfWork(session_factory) as uow:
        assert uow.user_accounts is not None
        uow.user_accounts.add(
            UserAccountModel(
                id=account_id,
                email="repo-test@example.com",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )

    with UnitOfWork(session_factory) as uow:
        assert uow.user_accounts is not None
        saved = uow.user_accounts.get(account_id)

        assert saved is not None
        assert saved.email == "repo-test@example.com"
        uow.session.delete(saved)


def test_unit_of_work_rolls_back_on_exception() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    account_id = "test-user-account-rollback"
    now = datetime.now(UTC)

    try:
        with UnitOfWork(session_factory) as uow:
            assert uow.user_accounts is not None
            uow.user_accounts.add(
                UserAccountModel(
                    id=account_id,
                    email="rollback-test@example.com",
                    account_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with UnitOfWork(session_factory) as uow:
        assert uow.user_accounts is not None
        assert uow.user_accounts.get(account_id) is None
