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
    ProxyInventoryModel,
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

    assert loaded == (account, auth, "http://registration-proxy.example:8080")
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


def test_backfill_session_reassigns_proxy_after_cloudflare_csrf_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    engine = make_engine(settings)
    _skip_if_schema_is_not_current(engine)
    session_factory = make_session_factory(engine)
    account_id = "test-cloudflare-403-reassign-account"
    proxy_1_id = "test-cloudflare-403-proxy-1"
    proxy_2_id = "test-cloudflare-403-proxy-2"
    binding_id = "test-cloudflare-403-binding"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(
            delete(UserAccountProxyBindingModel).where(
                UserAccountProxyBindingModel.user_account_id == account_id
            )
        )
        session.execute(delete(SpaceModel).where(SpaceModel.owner_user_account_id == account_id))
        session.execute(
            delete(ProxyInventoryModel).where(ProxyInventoryModel.id.in_([proxy_1_id, proxy_2_id]))
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="cloudflare-reassign@example.test",
                password="test-password",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        for proxy_id, port, status in (
            (proxy_1_id, 18081, "bound"),
            (proxy_2_id, 18082, "available"),
        ):
            session.add(
                ProxyInventoryModel(
                    id=proxy_id,
                    provider="webshare",
                    proxy_type="proxyserver",
                    external_proxy_id=proxy_id,
                    connection_mode="direct",
                    proxy_host="127.0.0.1",
                    proxy_port=port,
                    proxy_scheme="http",
                    proxy_username="",
                    proxy_password="",
                    country_code="",
                    city_name="",
                    asn_name="",
                    proxy_status=status,
                    provider_valid=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            UserAccountProxyBindingModel(
                id=binding_id,
                user_account_id=account_id,
                proxy_id=proxy_1_id,
                bind_status="active",
                bind_reason="test",
                bound_by_job_id="",
                bound_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(account_auth, "_probe_proxy_alive", lambda proxy_url: True)
    monkeypatch.setattr(
        account_auth,
        "_least_bound_proxy_for_update",
        lambda session: session.get(ProxyInventoryModel, proxy_2_id),
    )
    calls: list[str] = []
    personal_space_id = "test-personal-space-after-proxy-reassign"
    personal_access_token = _workspace_access_token(personal_space_id)

    def fake_acquire_chatgpt_session(**kwargs):
        calls.append(str(kwargs["proxy"]))
        if len(calls) == 1:
            raise RuntimeError("cloudflare_csrf_403_after_3_retries")
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
        binding = session.get(UserAccountProxyBindingModel, binding_id)
        proxy_1 = session.get(ProxyInventoryModel, proxy_1_id)
        proxy_2 = session.get(ProxyInventoryModel, proxy_2_id)
        account = session.get(UserAccountModel, account_id)
        assert binding is not None
        assert binding.proxy_id == proxy_2_id
        assert binding.bind_status == "active"
        assert proxy_1 is not None
        assert proxy_1.proxy_status == "error"
        assert proxy_1.provider_valid is False
        assert proxy_2 is not None
        assert proxy_2.proxy_status == "bound"
        assert account is not None
        assert account.session_status == "active"
        assert account.access_token == personal_access_token
        assert account.last_login_error_code == ""
        assert len(calls) == 2
        assert ":18081" in calls[0]
        assert ":18082" in calls[1]

        session.execute(
            delete(UserAccountProxyBindingModel).where(
                UserAccountProxyBindingModel.user_account_id == account_id
            )
        )
        session.execute(delete(SpaceModel).where(SpaceModel.owner_user_account_id == account_id))
        session.execute(
            delete(ProxyInventoryModel).where(ProxyInventoryModel.id.in_([proxy_1_id, proxy_2_id]))
        )
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
