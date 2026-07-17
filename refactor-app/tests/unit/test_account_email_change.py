from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session

from refactor_app.api.routes.resources import (
    AccountEmailChangeJobRequest,
    create_account_email_change_job,
)
from refactor_app.application.workflows.account_email_change import (
    AccountEmailChangeCsvError,
    AccountEmailChangeInput,
    AccountEmailChangeWorkflow,
    parse_account_email_change_csv,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.plugins.contracts import OtpMessage


def test_parse_account_email_change_csv_preserves_row_pairing_and_case() -> None:
    pairs = parse_account_email_change_csv(
        "\ufeffold_mail,new_mail\nOldOne@outlook.com,NewOne@outlook.com\n"
        "OldTwo@outlook.com,NewTwo@outlook.com\n"
    )

    assert [(pair.row_number, pair.old_mail, pair.new_mail) for pair in pairs] == [
        (2, "OldOne@outlook.com", "NewOne@outlook.com"),
        (3, "OldTwo@outlook.com", "NewTwo@outlook.com"),
    ]


@pytest.mark.parametrize(
    "csv_text,error",
    [
        ("old_mail\na@example.test\n", "missing required columns"),
        (
            "old_mail,new_mail\na@example.test,b@example.test\n"
            "A@example.test,c@example.test\n",
            "duplicate old_mail",
        ),
        (
            "old_mail,new_mail\na@example.test,b@example.test\n"
            "c@example.test,A@example.test\n",
            "sets overlap",
        ),
    ],
)
def test_parse_account_email_change_csv_rejects_invalid_mapping(
    csv_text: str,
    error: str,
) -> None:
    with pytest.raises(AccountEmailChangeCsvError, match=error):
        parse_account_email_change_csv(csv_text)


def test_account_email_change_updates_same_account_and_personal_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    engine = make_engine(settings)
    if not {"user_accounts", "spaces"}.issubset(set(inspect(engine).get_table_names())):
        pytest.skip("current database schema is unavailable")
    session_factory = make_session_factory(engine)
    suffix = str(uuid4())
    account_id = f"test-email-change-{suffix}"
    space_id = f"test-email-change-space-{suffix}"
    old_mail = f"Old-{suffix}@example.test"
    new_mail = f"New-{suffix}@example.test"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email=old_mail,
                account_status="registering",
                session_status="unknown",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=space_id,
                external_space_id=f"personal-{suffix}",
                owner_user_account_id=account_id,
                name=old_mail,
                space_type="personal",
                auth_mode="codex_oauth",
                credential_type="personal_account",
                space_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    def backfill_session(**_kwargs) -> str:
        with session_factory() as session:
            account = session.get(UserAccountModel, account_id)
            assert account is not None
            account.cookie_header = (
                "__Secure-next-auth.session-token=session-1; oai-did=device-1"
            )
            account.session_token = "session-1"
            account.openai_user_id = "user-1"
            account.session_status = "active"
            account.updated_at = datetime.now(UTC)
            session.commit()
        return account_id

    class MailProvider:
        def wait_for_otp_by_email(self, **kwargs):
            assert kwargs["email"] == new_mail
            assert kwargs["timeout_s"] == 90
            assert kwargs["issued_after"] > 0
            assert kwargs["code_source"] == "all"
            return OtpMessage(code="123456", raw={})

    class OpenAIProvider:
        def __init__(self) -> None:
            self.session_calls = 0

        def fetch_web_session_payload(self, **_kwargs):
            self.session_calls += 1
            email = old_mail if self.session_calls == 1 else new_mail
            return {"accessToken": f"token-{self.session_calls}", "user": {"email": email}}

        def decode_access_token(self, _access_token: str):
            return SimpleNamespace(account_id="user-1")

        def check_change_email_eligibility(self, **_kwargs):
            return {"eligible": True, "http_status": 200}

        def begin_change_email(self, **kwargs):
            assert kwargs["email"] == new_mail
            return {"sent": True, "http_status": 200}

        def verify_change_email(self, **kwargs):
            assert kwargs["email"] == new_mail
            assert kwargs["code"] == "123456"
            return {"changed": True, "http_status": 200}

    try:
        output = AccountEmailChangeWorkflow(
            session_factory=session_factory,
            mail_provider=MailProvider(),
            openai_provider=OpenAIProvider(),
            backfill_session=backfill_session,
            proxy_resolver=lambda *_args, **_kwargs: "http://proxy.example:8080",
        ).run(
            AccountEmailChangeInput(
                user_account_id=account_id,
                old_mail=old_mail,
                new_mail=new_mail,
                otp_timeout_s=90,
            )
        )

        assert output["user_account_id"] == account_id
        assert output["old_mail"] == old_mail
        assert output["new_mail"] == new_mail
        assert output["post_session_status"] == "succeeded"
        assert output["post_session_email"] == new_mail
        with session_factory() as session:
            account = session.get(UserAccountModel, account_id)
            space = session.get(SpaceModel, space_id)
            assert account is not None
            assert account.id == account_id
            assert account.email == new_mail
            assert account.account_status == "active"
            assert account.openai_user_id == "user-1"
            assert space is not None
            assert space.name == new_mail
    finally:
        with session_factory() as session:
            session.execute(delete(SpaceModel).where(SpaceModel.id == space_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
            session.commit()


def test_create_account_email_change_job_creates_one_account_and_work_per_csv_row() -> None:
    settings = Settings()
    engine = make_engine(settings)
    required_tables = {"jobs", "job_runs", "work_items", "user_accounts"}
    if not required_tables.issubset(set(inspect(engine).get_table_names())):
        pytest.skip("current database schema is unavailable")
    suffix = str(uuid4())
    csv_text = (
        "old_mail,new_mail\n"
        f"OldOne-{suffix}@example.test,NewOne-{suffix}@example.test\n"
        f"OldTwo-{suffix}@example.test,NewTwo-{suffix}@example.test\n"
    )

    with engine.connect() as connection:
        outer_transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            result = create_account_email_change_job(
                AccountEmailChangeJobRequest(
                    csv_text=csv_text,
                    work_count=2,
                    otp_timeout_s=90,
                    created_by="test",
                ),
                session,
            )

            assert result["job_status"] == "running"
            assert result["work_count"] == 2
            assert result["selected_count"] == 2
            assert result["queued"] == 2
            job = session.get(JobModel, result["job_id"])
            assert job is not None
            assert job.type == "account.change_email.bulk"
            assert job.input_json["work_count"] == 2
            works = session.query(WorkItemModel).filter_by(job_id=job.id).all()
            assert [work.work_type for work in works] == [
                "account.change_email.one",
                "account.change_email.one",
            ]
            work_pairs = [
                (work.input_json["old_mail"], work.input_json["new_mail"])
                for work in works
            ]
            assert work_pairs == [
                (
                    f"OldOne-{suffix}@example.test",
                    f"NewOne-{suffix}@example.test",
                ),
                (
                    f"OldTwo-{suffix}@example.test",
                    f"NewTwo-{suffix}@example.test",
                ),
            ]
            account_ids = [work.input_json["user_account_id"] for work in works]
            accounts = (
                session.query(UserAccountModel)
                .filter(UserAccountModel.id.in_(account_ids))
                .all()
            )
            assert {account.email for account in accounts} == {
                f"OldOne-{suffix}@example.test",
                f"OldTwo-{suffix}@example.test",
            }
            assert {account.account_status for account in accounts} == {"registering"}
        finally:
            session.close()
            outer_transaction.rollback()
