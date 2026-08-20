from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, inspect

from refactor_app.application.workflows import account_auth
from refactor_app.application.workflows.account_auth import (
    AccountAuthWorkflowError,
    BackfillRtWorkflow,
    BackfillSessionWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    SpaceModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
)


def _workspace_access_token(chatgpt_account_id: str) -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return ".".join(
        (
            encode({"alg": "none", "typ": "JWT"}),
            encode(
                {
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": chatgpt_account_id,
                        "chatgpt_user_id": "user-test",
                    }
                }
            ),
            "",
        )
    )


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


def test_codex_select_channel_failure_sets_permanent_account_marker_only() -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-codex-select-channel-account"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="select-channel@example.test",
                account_status="active",
                session_status="active",
                last_login_error_code="existing-session-error",
                last_login_error_message="must remain untouched",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    workflow = BackfillRtWorkflow(session_factory=session_factory, mail_provider=object())
    workflow._write_rt_failure(
        user_account_id=account_id,
        error_code="phone_otp_select_channel",
        error_message="select channel",
    )

    with session_factory() as session:
        account = session.get(UserAccountModel, account_id)
        assert account is not None
        assert account.codex_select_channel_required is True
        assert account.codex_select_channel_detected_at is not None
        assert account.account_status == "active"
        assert account.session_status == "active"
        assert account.last_login_error_code == "existing-session-error"
        assert account.last_login_error_message == "must remain untouched"

        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_codex_account_deactivated_failure_marks_account_invalid_and_exits() -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-codex-account-deactivated"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="codex-deactivated@example.test",
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    workflow = BackfillRtWorkflow(session_factory=session_factory, mail_provider=object())
    result = account_auth.CodexBrowserRtResult(
        ok=False,
        failure_code="account_deactivated",
        failure_message=("You do not have an account because it has been deleted or deactivated."),
        final_url="https://auth.openai.com/log-in/password",
    )

    with pytest.raises(AccountAuthWorkflowError, match="account_deactivated"):
        workflow._raise_terminal_rt_failure(
            result=result,
            user_account_id=account_id,
            run_id="",
            step_id="",
            phone_provider=None,
        )

    with session_factory() as session:
        account = session.get(UserAccountModel, account_id)
        assert account is not None
        assert account.account_status == "invalid"
        assert account.session_status == "dead"
        assert account.last_login_error_code == "account_deactivated"
        assert "deleted or deactivated" in account.last_login_error_message

        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_codex_proxy_override_bypasses_account_proxy_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = SimpleNamespace(id="account-1", email="account@example.test")
    auth = SimpleNamespace(cookie_header="session=value")
    events: list[tuple[str, dict]] = []
    workflow = BackfillRtWorkflow(session_factory=lambda: None, mail_provider=object())

    monkeypatch.setattr(
        workflow,
        "_load_account_auth_proxy",
        lambda _user_account_id: (account, auth, None),
    )
    monkeypatch.setattr(
        workflow,
        "_load_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("proxy selection must be bypassed")
        ),
    )
    monkeypatch.setattr(
        workflow,
        "_write_event",
        lambda _run_id, event_type, _message, data, **_kwargs: events.append((event_type, data)),
    )

    loaded = workflow._load_rt_input(
        user_account_id="account-1",
        run_id="run-1",
        proxy_url_override="http://registration-proxy.example:8080",
    )

    assert loaded == (account, auth, "http://registration-proxy.example:8080", "US")
    assert events == [
        (
            "account_auth.proxy_override_used",
            {
                "user_account_id": "account-1",
                "proxy_used": True,
                "proxy_source": "registration_current_proxy",
            },
        )
    ]


def test_backfill_session_uses_cliproxy_instead_of_account_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-cliproxy-backfill-account"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(
            delete(UserAccountProxyBindingModel).where(
                UserAccountProxyBindingModel.user_account_id == account_id
            )
        )
        session.execute(delete(SpaceModel).where(SpaceModel.owner_user_account_id == account_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="cliproxy-backfill@example.test",
                password="test-password",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    calls: list[str] = []
    proxy_calls: list[dict] = []
    personal_space_id = "test-personal-space-after-cliproxy-backfill"
    personal_access_token = _workspace_access_token(personal_space_id)

    def resolve_proxy(**kwargs):
        proxy_calls.append(kwargs)
        return SimpleNamespace(
            proxy_url="http://cliproxy.example:443",
            provider="cliproxy",
            country_code="US",
            egress_ip="203.0.113.11",
            sid_source="email_sha256",
            proxy_mode="cliproxy_sticky",
        )

    monkeypatch.setattr(account_auth, "resolve_cliproxy_proxy", resolve_proxy)

    def fake_acquire_chatgpt_session(**kwargs):
        calls.append(str(kwargs["proxy"]))
        auth_result = SimpleNamespace(
            session_token="session-token",
            access_token=personal_access_token,
            refresh_token="",
            id_token="",
            cookie_header="",
            device_id="device-id",
            csrf_token="csrf-token",
            chatgpt_account_structure="personal",
            chatgpt_account_id=personal_space_id,
        )
        return SimpleNamespace(
            ok=True,
            auth_result=auth_result,
            cookie_header="__Secure-next-auth.session-token=session-token",
            auth_cookie_header="",
            snapshot={},
        )

    monkeypatch.setattr(account_auth, "acquire_chatgpt_session", fake_acquire_chatgpt_session)

    workflow = BackfillSessionWorkflow(session_factory=session_factory, mail_provider=object())
    assert workflow.run(user_account_id=account_id) == account_id

    with session_factory() as session:
        account = session.get(UserAccountModel, account_id)
        assert account is not None
        assert account.session_status == "active"
        assert account.access_token == personal_access_token
        assert account.last_login_error_code == ""
        assert calls == ["http://cliproxy.example:443"]
        assert proxy_calls == [
            {
                "email": "cliproxy-backfill@example.test",
                "country_code": "US",
            }
        ]

        session.execute(
            delete(UserAccountProxyBindingModel).where(
                UserAccountProxyBindingModel.user_account_id == account_id
            )
        )
        session.execute(delete(SpaceModel).where(SpaceModel.owner_user_account_id == account_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def _skip_if_schema_is_not_current(engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("user_accounts")}
    if {
        "password",
        "session_status",
        "last_login_error_code",
        "codex_select_channel_required",
    } - columns:
        pytest.skip("local Postgres schema has not applied Space migrations")
