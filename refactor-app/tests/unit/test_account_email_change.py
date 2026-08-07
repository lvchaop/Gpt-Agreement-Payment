from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from refactor_app.api.routes.resources import (
    AccountEmailChangeJobRequest,
    create_account_email_change_job,
)
from refactor_app.application.workflows.account_email_change import (
    ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
    AccountEmailChangeCsvError,
    AccountEmailChangeInput,
    AccountEmailChangeSourceError,
    AccountEmailChangeWorkflow,
    parse_account_email_change_csv,
    parse_account_email_change_source_jsonl,
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
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.openai_chatgpt.client import OpenAIChatGPTClientError


def _source_access_token(
    *,
    email: str,
    user_id: str,
    account_id: str,
    expires_at: datetime | None = None,
) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = {
        "client_id": "app-source-test",
        "exp": int((expires_at or (datetime.now(UTC) + timedelta(hours=1))).timestamp()),
        "https://api.openai.com/auth": {
            "user_id": user_id,
            "chatgpt_account_id": account_id,
        },
        "https://api.openai.com/profile": {"email": email},
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{body}.signature"


def _source_record(*, email: str, user_id: str, account_id: str) -> dict:
    return {
        "version": 1,
        "db_id": 123,
        "platform": "chatgpt",
        "email": email,
        "login_identity": email,
        "account_claims_email": email,
        "phone": "+12025550123",
        "access_token": _source_access_token(
            email=email,
            user_id=user_id,
            account_id=account_id,
        ),
        "client_id": "app-source-test",
        "chatgpt_user_id": user_id,
        "chatgpt_account_id": account_id,
        "session_token": "session-source",
        "cookie_header": "__Secure-next-auth.session-token=session-source",
        "mailbox_url": (
            "http://mail.example.test/api/open/email/latest?"
            f"api_key=test-key&pt=test-pt&email={email}"
        ),
        "created_at": int(datetime.now(UTC).timestamp()),
        "last_used": int(datetime.now(UTC).timestamp()),
        "status": "registered",
    }


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


def test_parse_account_email_change_source_jsonl_validates_token_identity() -> None:
    record = _source_record(
        email="Source.User@outlook.com",
        user_id="user-source-1",
        account_id="personal-source-1",
    )

    sources = parse_account_email_change_source_jsonl(json.dumps(record))

    assert len(sources) == 1
    assert sources[0].email == "Source.User@outlook.com"
    assert sources[0].openai_user_id == "user-source-1"
    assert sources[0].chatgpt_account_id == "personal-source-1"
    assert sources[0].access_token == record["access_token"]
    assert sources[0].mailbox_url == record["mailbox_url"]


def test_parse_account_email_change_source_jsonl_rejects_identity_mismatch() -> None:
    record = _source_record(
        email="source@example.test",
        user_id="user-source-1",
        account_id="personal-source-1",
    )
    record["chatgpt_user_id"] = "user-other"

    with pytest.raises(AccountEmailChangeSourceError, match="chatgpt_user_id"):
        parse_account_email_change_source_jsonl(json.dumps(record))


def test_parse_source_accepts_expired_bootstrap_token_for_fresh_session_login() -> None:
    record = _source_record(
        email="source@example.test",
        user_id="user-source-1",
        account_id="personal-source-1",
    )
    record["access_token"] = _source_access_token(
        email=record["email"],
        user_id=record["chatgpt_user_id"],
        account_id=record["chatgpt_account_id"],
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    sources = parse_account_email_change_source_jsonl(json.dumps(record))

    assert sources[0].email == record["email"]


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
            return {"success": True, "http_status": 200}

        def verify_change_email(self, **kwargs):
            assert kwargs["email"] == new_mail
            assert kwargs["code"] == "123456"
            return {"success": True, "http_status": 200}

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


def test_account_email_change_auto_claim_uses_account_proxy_and_web_session() -> None:
    settings = Settings()
    engine = make_engine(settings)
    if not {"user_accounts", "spaces"}.issubset(set(inspect(engine).get_table_names())):
        pytest.skip("current database schema is unavailable")
    session_factory = make_session_factory(engine)
    suffix = str(uuid4())
    account_id = f"test-auto-email-change-{suffix}"
    space_id = f"test-auto-email-change-space-{suffix}"
    old_mail = f"Source-{suffix}@example.test"
    rejected_mail = f"AlreadyLinked-{suffix}@outlook.com"
    new_mail = f"Claimed-{suffix}@outlook.com"
    openai_user_id = f"user-{suffix}"
    personal_account_id = f"personal-{suffix}"
    source_token = "source-access-token"
    cookie_header = "__Secure-next-auth.session-token=source-session"
    steps: list[str] = []
    now = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email=old_mail,
                openai_user_id=openai_user_id,
                access_token=source_token,
                session_token="source-session",
                cookie_header=cookie_header,
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=space_id,
                external_space_id=personal_account_id,
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

    class MailProvider:
        def __init__(self) -> None:
            self.claim_count = 0
            self.completed: list[tuple[str, str]] = []
            self.released = False

        def claim_random(self, **kwargs):
            steps.append("claim")
            assert kwargs == {
                "caller_id": "refactor-app-protocol-registration",
                "task_id": "work-source-1",
                "provider": "outlook",
                "project_key": "",
                "email_domain": "",
            }
            self.claim_count += 1
            email = rejected_mail if self.claim_count == 1 else new_mail
            return ClaimedMailAccount(
                account_id=f"mail-{self.claim_count}",
                email=email,
                claim_token=f"claim-{self.claim_count}",
                caller_id=kwargs["caller_id"],
                task_id=kwargs["task_id"],
            )

        def wait_for_otp_by_email(self, **kwargs):
            assert kwargs["email"] == new_mail
            assert kwargs["code_source"] == "all"
            return OtpMessage(code="123456", raw={})

        def claim_complete(self, claim, **kwargs):
            assert kwargs["result"] == "success"
            self.completed.append((claim.email, kwargs["detail"]))
            return {"success": True, "data": {"pool_status": "used"}}

        def claim_release(self, _claim, **_kwargs):
            self.released = True
            return {"success": True}

    class OpenAIProvider:
        def fetch_web_session_payload(self, **kwargs):
            steps.append("session")
            assert kwargs == {
                "cookie_header": cookie_header,
                "proxy_url": "http://account-proxy.example:8080",
            }
            return {"accessToken": source_token}

        def decode_access_token(self, access_token: str):
            assert access_token == source_token
            return SimpleNamespace(
                account_id=openai_user_id,
                token_chatgpt_account_id=personal_account_id,
            )

        def check_change_email_eligibility(self, **kwargs):
            steps.append("eligibility")
            assert kwargs["access_token"] == source_token
            assert kwargs["cookie_header"] == cookie_header
            assert kwargs["proxy_url"] == "http://account-proxy.example:8080"
            return {"eligible": True, "http_status": 200}

        def begin_change_email(self, **kwargs):
            steps.append("begin")
            assert kwargs["cookie_header"] == cookie_header
            assert kwargs["proxy_url"] == "http://account-proxy.example:8080"
            if kwargs["email"] == rejected_mail:
                raise OpenAIChatGPTClientError(
                    "chatgpt backend request failed: http_status=403 "
                    "body_snippet={'detail': 'Email already linked to another account'}"
                )
            assert kwargs["email"] == new_mail
            return {"success": True, "http_status": 200}

        def verify_change_email(self, **kwargs):
            steps.append("verify")
            assert kwargs["email"] == new_mail
            assert kwargs["code"] == "123456"
            assert kwargs["cookie_header"] == cookie_header
            assert kwargs["proxy_url"] == "http://account-proxy.example:8080"
            return {"success": True, "http_status": 200}

    mail_provider = MailProvider()

    def backfill_session(**kwargs) -> str:
        steps.append("backfill")
        assert kwargs["user_account_id"] == account_id
        return account_id

    try:
        output = AccountEmailChangeWorkflow(
            session_factory=session_factory,
            mail_provider=mail_provider,
            openai_provider=OpenAIProvider(),
            backfill_session=backfill_session,
            proxy_resolver=lambda *_args, **_kwargs: "http://account-proxy.example:8080",
        ).run(
            AccountEmailChangeInput(
                user_account_id=account_id,
                old_mail=old_mail,
                mode=ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
                source_mailbox_url=(
                    "http://mail.example.test/latest?"
                    f"api_key=secret&pt=secret&email={old_mail}"
                ),
            ),
            work_id="work-source-1",
        )

        assert output["new_mail"] == new_mail
        assert output["remote_changed"] is True
        assert output["mail_claim_completed"] is True
        assert output["rejected_mail_count"] == 1
        assert mail_provider.completed == [
            (rejected_mail, "openai_email_already_linked"),
            (new_mail, new_mail),
        ]
        assert mail_provider.released is False
        assert steps == [
            "backfill",
            "session",
            "eligibility",
            "claim",
            "begin",
            "claim",
            "begin",
            "verify",
        ]
        with session_factory() as session:
            account = session.get(UserAccountModel, account_id)
            space = session.get(SpaceModel, space_id)
            assert account is not None
            assert account.email == new_mail
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


def test_create_account_email_change_job_imports_source_without_storing_raw_file_in_job() -> None:
    settings = Settings()
    engine = make_engine(settings)
    required_tables = {"jobs", "job_runs", "work_items", "user_accounts", "spaces"}
    if not required_tables.issubset(set(inspect(engine).get_table_names())):
        pytest.skip("current database schema is unavailable")
    suffix = str(uuid4())
    email = f"Source-{suffix}@outlook.com"
    user_id = f"user-{suffix}"
    personal_account_id = f"personal-{suffix}"
    record = _source_record(
        email=email,
        user_id=user_id,
        account_id=personal_account_id,
    )

    with engine.connect() as connection:
        outer_transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            result = create_account_email_change_job(
                AccountEmailChangeJobRequest(
                    mode=ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
                    source_jsonl_text=json.dumps(record),
                    work_count=3,
                    otp_timeout_s=90,
                    created_by="test",
                ),
                session,
            )

            assert result["job_status"] == "running"
            assert result["work_count"] == 3
            assert result["selected_count"] == 1
            job = session.get(JobModel, result["job_id"])
            assert job is not None
            assert job.input_json["mode"] == ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM
            assert "source_jsonl_text" not in job.input_json
            assert "access_token" not in job.input_json
            work = session.query(WorkItemModel).filter_by(job_id=job.id).one()
            assert "access_token" not in work.input_json
            assert work.input_json["source_mailbox_url"] == record["mailbox_url"]
            account = session.get(UserAccountModel, work.input_json["user_account_id"])
            assert account is not None
            assert account.email == email
            assert account.openai_user_id == user_id
            assert account.access_token == record["access_token"]
            personal_space = session.scalars(
                select(SpaceModel).where(
                    SpaceModel.owner_user_account_id == account.id,
                    SpaceModel.space_type == "personal",
                )
            ).one()
            assert personal_space.external_space_id == personal_account_id
            assert personal_space.name == email

            retry_result = create_account_email_change_job(
                AccountEmailChangeJobRequest(
                    mode=ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
                    source_jsonl_text=json.dumps(record),
                    work_count=3,
                    otp_timeout_s=90,
                    created_by="test-retry",
                ),
                session,
            )

            assert retry_result["selected_count"] == 1
            assert retry_result["reused_account_count"] == 1
            retry_work = session.query(WorkItemModel).filter_by(
                job_id=retry_result["job_id"]
            ).one()
            assert retry_work.input_json["user_account_id"] == account.id
            assert (
                session.query(UserAccountModel)
                .filter(UserAccountModel.email.ilike(email))
                .count()
                == 1
            )
            assert (
                session.query(SpaceModel)
                .filter(SpaceModel.external_space_id == personal_account_id)
                .count()
                == 1
            )
        finally:
            session.close()
            outer_transaction.rollback()
