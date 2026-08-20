from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from refactor_app.api.routes import resources
from refactor_app.application.jobs import handlers
from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.workflows import account_auth
from refactor_app.application.workflows.account_auth import (
    BackfillRtWorkflow,
    CodexAuthorizationFallbackRequired,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobModel,
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import CodexBrowserRtResult


def _access_token(*, workspace_id: str, user_id: str) -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return ".".join(
        (
            encode({"alg": "none", "typ": "JWT"}),
            encode(
                {
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": workspace_id,
                        "chatgpt_user_id": user_id,
                    }
                }
            ),
            "",
        )
    )


def _insert_business_target(*, select_channel: bool = False) -> tuple[object, dict[str, str]]:
    suffix = uuid4().hex
    ids = {
        "user": f"test-business-codex-user-{suffix}",
        "space": f"test-business-codex-space-{suffix}",
        "external_space": f"test-business-codex-external-{suffix}",
        "membership": f"test-business-codex-membership-{suffix}",
        "openai_user": f"user-{suffix}",
    }
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=ids["user"],
                email=f"{suffix}@example.test",
                openai_user_id=ids["openai_user"],
                session_token=f"session-{suffix}",
                cookie_header=f"cookie={suffix}",
                codex_select_channel_required=select_channel,
                codex_select_channel_detected_at=now if select_channel else None,
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=ids["space"],
                external_space_id=ids["external_space"],
                owner_user_account_id="",
                name=f"Business {suffix}",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_monthly",
                space_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            SpaceMembershipModel(
                id=ids["membership"],
                space_id=ids["space"],
                user_account_id=ids["user"],
                membership_status="active",
                session_account_detected=True,
                remote_user_id=ids["openai_user"],
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    return session_factory, ids


def _cleanup(session_factory, ids: dict[str, str], job_id: str = "") -> None:
    with session_factory() as session:
        if job_id:
            session.execute(delete(JobModel).where(JobModel.id == job_id))
        session.execute(delete(SpaceModel).where(SpaceModel.id == ids["space"]))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == ids["user"]))
        session.commit()


def _mock_loaded_account(ids: dict[str, str]):
    account = SimpleNamespace(
        email=f"{ids['user']}@example.test",
        openai_user_id=ids["openai_user"],
    )
    auth = SimpleNamespace(
        cookie_header="cookie=test",
        auth_cookie_header="",
        session_token="",
        password="",
    )
    return account, auth, "http://proxy.example.test:8080", "US"


def test_business_codex_oauth_writes_credential_auth_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, ids = _insert_business_target()
    result = CodexBrowserRtResult(
        ok=True,
        access_token=_access_token(
            workspace_id=ids["external_space"],
            user_id=ids["openai_user"],
        ),
        id_token="id-token",
        refresh_token="refresh-token",
        token_type="Bearer",
        scope="openid offline_access",
    )
    monkeypatch.setattr(
        BackfillRtWorkflow,
        "_load_input",
        lambda self, user_account_id, run_id="": _mock_loaded_account(ids),
    )
    monkeypatch.setattr(
        account_auth,
        "acquire_codex_rt_with_existing_browser_session",
        lambda **kwargs: result,
    )

    try:
        assert (
            BackfillRtWorkflow(session_factory=session_factory, mail_provider=object()).run(
                user_account_id=ids["user"],
                business_space_id=ids["space"],
                fallback_to_web_access_token_on_phone_gate=True,
            )
            == ids["user"]
        )
        with session_factory() as session:
            credential = session.scalars(
                select(SpaceCredentialModel).where(
                    SpaceCredentialModel.space_id == ids["space"],
                    SpaceCredentialModel.user_account_id == ids["user"],
                )
            ).one()
            assert credential.auth_mode == "codex_oauth"
            assert credential.space_membership_id == ids["membership"]
            assert credential.token_chatgpt_account_id == ids["external_space"]
            assert credential.refresh_token == "refresh-token"
    finally:
        _cleanup(session_factory, ids)


def test_business_codex_browser_fallback_receives_account_totp_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, ids = _insert_business_target()
    resolved_ids: list[str] = []
    submitted_codes: list[str] = []
    account = SimpleNamespace(
        email=f"{ids['user']}@example.test",
        openai_user_id=ids["openai_user"],
    )
    auth = SimpleNamespace(
        cookie_header="cookie=test",
        auth_cookie_header="",
        session_token="",
        password="configured-password",
        mfa_status="configured",
        twofauth_account_id="twofauth-account-42",
    )
    monkeypatch.setattr(
        BackfillRtWorkflow,
        "_load_input",
        lambda self, user_account_id, run_id="": (
            account,
            auth,
            "http://proxy.example.test:8080",
            "US",
        ),
    )
    monkeypatch.setattr(
        account_auth,
        "acquire_codex_rt_with_existing_browser_session",
        lambda **_kwargs: CodexBrowserRtResult(
            ok=False,
            failure_code="session_cookie_not_accepted",
            failure_message="login required",
        ),
    )

    def browser_login(**kwargs):
        submitted_codes.append(kwargs["totp_code_provider"]())
        return CodexBrowserRtResult(
            ok=True,
            access_token=_access_token(
                workspace_id=ids["external_space"],
                user_id=ids["openai_user"],
            ),
            id_token="id-token",
            refresh_token="refresh-token",
            token_type="Bearer",
            scope="openid offline_access",
        )

    monkeypatch.setattr(account_auth, "acquire_codex_rt_with_browser_login", browser_login)

    def resolve(account_id: str) -> str:
        resolved_ids.append(account_id)
        return "654321"

    try:
        assert (
            BackfillRtWorkflow(
                session_factory=session_factory,
                mail_provider=object(),
                totp_code_resolver=resolve,
            ).run(
                user_account_id=ids["user"],
                business_space_id=ids["space"],
                fallback_to_web_access_token_on_phone_gate=True,
            )
            == ids["user"]
        )
        assert resolved_ids == ["twofauth-account-42"]
        assert submitted_codes == ["654321"]
    finally:
        _cleanup(session_factory, ids)


def test_business_phone_gate_requests_at_fallback_without_second_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, ids = _insert_business_target()
    monkeypatch.setattr(
        BackfillRtWorkflow,
        "_load_input",
        lambda self, user_account_id, run_id="": _mock_loaded_account(ids),
    )
    monkeypatch.setattr(
        account_auth,
        "acquire_codex_rt_with_existing_browser_session",
        lambda **kwargs: CodexBrowserRtResult(
            ok=False,
            failure_code="add_phone_blocked",
            failure_message="add phone required",
            final_url="https://auth.openai.com/add-phone",
        ),
    )

    def fail_if_browser_login_runs(**kwargs):
        raise AssertionError("phone gate must downgrade before browser login fallback")

    monkeypatch.setattr(
        account_auth,
        "acquire_codex_rt_with_browser_login",
        fail_if_browser_login_runs,
    )

    try:
        with pytest.raises(CodexAuthorizationFallbackRequired) as raised:
            BackfillRtWorkflow(session_factory=session_factory, mail_provider=object()).run(
                user_account_id=ids["user"],
                business_space_id=ids["space"],
                fallback_to_web_access_token_on_phone_gate=True,
            )
        assert raised.value.failure_code == "add_phone_blocked"
        with session_factory() as session:
            assert session.scalar(
                select(SpaceCredentialModel.id).where(
                    SpaceCredentialModel.space_id == ids["space"]
                )
            ) is None
    finally:
        _cleanup(session_factory, ids)


def test_marked_select_channel_enqueues_one_rate_limited_at_fallback_work() -> None:
    session_factory, ids = _insert_business_target(select_channel=True)
    job_id = ""
    try:
        with session_factory() as session:
            job = JobQueue(session).enqueue(
                job_type="automation.space_authorize",
                input_json={"space_id": ids["space"], "work_count": 3},
                created_by="test",
            )
            session.flush()
            source_work = WorkQueue(session).enqueue(
                job_id=job.id,
                work_type="space.business_codex.authorize.account",
                input_json={
                    "space_membership_id": ids["membership"],
                    "space_id": ids["space"],
                    "user_account_id": ids["user"],
                    "external_space_id": ids["external_space"],
                    "credential_name": f"codex-{ids['user']}",
                    "cookie_header": "cookie=test",
                },
            )
            job_id = job.id
            source_work_id = source_work.id
            session.commit()

        output = handlers._run_space_business_codex_authorization_work(
            session_factory=session_factory,
            settings=Settings(),
            input_json={
                "_work_id": source_work_id,
                "space_membership_id": ids["membership"],
                "space_id": ids["space"],
                "user_account_id": ids["user"],
                "external_space_id": ids["external_space"],
                "credential_name": f"codex-{ids['user']}",
                "cookie_header": "cookie=test",
            },
        )
        assert output["_work_outcome"] == "skipped"
        assert output["skip_reason"] == (
            "phone_otp_select_channel_web_access_token_fallback"
        )

        with session_factory() as session:
            fallback = session.scalars(
                select(WorkItemModel).where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.business_access_token.create.account",
                )
            ).one()
            assert fallback.execution_key == f"space-business-at:{ids['external_space']}"
            assert fallback.input_json["startup_sleep_s"] == 10.0
            assert fallback.input_json["oauth_fallback_reason"] == "phone_otp_select_channel"
    finally:
        _cleanup(session_factory, ids, job_id=job_id)


def test_scheduled_business_authorization_selects_only_requested_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory, ids = _insert_business_target()
    job_id = ""
    monkeypatch.setattr(resources, "_active_work_job_for_type", lambda **kwargs: None)
    try:
        with session_factory() as session:
            result = resources._create_space_authorization_work_job(
                session=session,
                space_id=ids["space"],
                work_count=4,
                created_by="test",
                credential_name_prefix="codex",
            )
            job_id = str(result["job_id"])

        assert result["selected_count"] == 1
        assert result["work_count"] == 4
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            work = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).one()
            assert job is not None
            assert job.type == "automation.space_authorize"
            assert job.input_json["space_id"] == ids["space"]
            assert work.work_type == "space.business_codex.authorize.account"
            assert work.execution_key == ""
            assert work.input_json["space_membership_id"] == ids["membership"]
    finally:
        _cleanup(session_factory, ids, job_id=job_id)


def test_active_authorization_job_is_scoped_to_selected_space() -> None:
    session_factory, ids = _insert_business_target()
    other_job_id = ""
    same_job_id = ""
    try:
        with session_factory() as session:
            other_job = JobQueue(session).enqueue(
                job_type="automation.space_authorize",
                input_json={"space_id": f"other-{uuid4().hex}", "work_count": 1},
                created_by="test",
            )
            WorkQueue(session).enqueue(
                job_id=other_job.id,
                work_type="space.business_codex.authorize.account",
                input_json={},
            )
            other_job_id = other_job.id
            session.commit()

        with session_factory() as session:
            assert (
                resources._active_work_job_for_type(
                    session=session,
                    job_type="automation.space_authorize",
                    space_id=ids["space"],
                    external_space_id=ids["external_space"],
                )
                is None
            )

            same_job = JobQueue(session).enqueue(
                job_type="automation.space_authorize",
                input_json={"space_id": ids["space"], "work_count": 1},
                created_by="test",
            )
            WorkQueue(session).enqueue(
                job_id=same_job.id,
                work_type="space.business_codex.authorize.account",
                input_json={},
            )
            same_job_id = same_job.id
            session.commit()

        with session_factory() as session:
            active = resources._active_work_job_for_type(
                session=session,
                job_type="automation.space_authorize",
                space_id=ids["space"],
                external_space_id=ids["external_space"],
            )
            assert active is not None
            assert active.id == same_job_id
    finally:
        with session_factory() as session:
            if other_job_id:
                session.execute(delete(JobModel).where(JobModel.id == other_job_id))
            if same_job_id:
                session.execute(delete(JobModel).where(JobModel.id == same_job_id))
            session.commit()
        _cleanup(session_factory, ids)
