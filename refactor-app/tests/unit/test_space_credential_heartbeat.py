from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from refactor_app.application.workflows.space_credential_heartbeat import (
    PersonalCodexCredentialHeartbeatError,
    PersonalCodexCredentialHeartbeatInput,
    PersonalCodexCredentialHeartbeatWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushBindingModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import OAuthTokenSet, OpenAIChatGPTProvider, TokenClaims
from refactor_app.plugins.openai_chatgpt import (
    OpenAIChatGPTClientError,
    OpenAIOAuthRefreshError,
)


@dataclass(frozen=True)
class _HeartbeatRows:
    session_factory: sessionmaker[Session]
    user_id: str
    space_id: str
    membership_id: str
    credential_id: str
    workspace_id: str
    openai_user_id: str


class _OpenAIProvider:
    def __init__(self, *, workspace_id: str, openai_user_id: str) -> None:
        self.claims_by_token: dict[str, TokenClaims | Exception] = {
            "access-initial": TokenClaims(
                token_chatgpt_account_id=workspace_id,
                account_id=openai_user_id,
            ),
            "access-refreshed": TokenClaims(
                token_chatgpt_account_id=workspace_id,
                account_id=openai_user_id,
            ),
            "access-reauthorized": TokenClaims(
                token_chatgpt_account_id=workspace_id,
                account_id=openai_user_id,
            ),
        }
        self.probe_results: list[dict[str, Any] | Exception] = [{"status": "ok"}]
        self.refresh_result: OAuthTokenSet | Exception | None = None
        self.probe_calls: list[dict[str, str]] = []
        self.refresh_calls: list[dict[str, str]] = []

    def decode_access_token(self, access_token: str) -> TokenClaims:
        claims = self.claims_by_token.get(access_token)
        if isinstance(claims, Exception):
            raise claims
        if claims is None:
            raise OpenAIChatGPTClientError(f"unknown test token: {access_token}")
        return claims

    def probe_codex_responses_usage(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict[str, Any]:
        self.probe_calls.append(
            {
                "access_token": access_token,
                "team_id": team_id,
                "proxy_url": proxy_url,
                "model": model,
            }
        )
        result = self.probe_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def refresh_workspace_token(
        self,
        *,
        refresh_token: str,
        external_workspace_id: str,
        client_id: str,
    ) -> OAuthTokenSet:
        self.refresh_calls.append(
            {
                "refresh_token": refresh_token,
                "external_workspace_id": external_workspace_id,
                "client_id": client_id,
            }
        )
        if isinstance(self.refresh_result, Exception):
            raise self.refresh_result
        if self.refresh_result is None:
            raise AssertionError("refresh was not configured")
        return self.refresh_result


@pytest.fixture
def heartbeat_rows() -> Iterator[_HeartbeatRows]:
    suffix = uuid4().hex
    user_id = f"heartbeat-user-{suffix}"
    space_id = f"heartbeat-space-{suffix}"
    membership_id = f"heartbeat-membership-{suffix}"
    credential_id = f"heartbeat-credential-{suffix}"
    workspace_id = f"heartbeat-workspace-{suffix}"
    openai_user_id = f"heartbeat-openai-user-{suffix}"
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=user_id,
                email=f"heartbeat-{suffix}@example.test",
                openai_user_id=openai_user_id,
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=space_id,
                external_space_id=workspace_id,
                owner_user_account_id=user_id,
                name=f"Heartbeat {suffix}",
                space_type="personal",
                auth_mode="codex_oauth",
                credential_type="personal_account",
                plan_type="plus",
                space_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            SpaceMembershipModel(
                id=membership_id,
                space_id=space_id,
                user_account_id=user_id,
                membership_status="active",
                session_account_detected=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceCredentialModel(
                id=credential_id,
                space_id=space_id,
                user_account_id=user_id,
                space_membership_id=None,
                external_credential_id="codex-client-1",
                auth_mode="codex_oauth",
                credential_status="active",
                access_token="access-initial",
                id_token="id-initial",
                refresh_token="refresh-initial",
                codex_client_id="codex-client-1",
                account_id=openai_user_id,
                token_chatgpt_account_id=workspace_id,
                last_authorized_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    rows = _HeartbeatRows(
        session_factory=session_factory,
        user_id=user_id,
        space_id=space_id,
        membership_id=membership_id,
        credential_id=credential_id,
        workspace_id=workspace_id,
        openai_user_id=openai_user_id,
    )
    try:
        yield rows
    finally:
        with session_factory() as session:
            session.execute(
                delete(SpacePushBindingModel).where(
                    SpacePushBindingModel.space_credential_id == credential_id
                )
            )
            session.execute(
                delete(SpaceCredentialModel).where(SpaceCredentialModel.id == credential_id)
            )
            session.execute(
                delete(SpaceMembershipModel).where(SpaceMembershipModel.id == membership_id)
            )
            session.execute(delete(SpaceModel).where(SpaceModel.id == space_id))
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == user_id))
            session.commit()


def test_active_personal_codex_credential_probe_succeeds(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    provider = _provider(heartbeat_rows)
    flow = _workflow(heartbeat_rows, provider)

    result = flow.run(
        PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id)
    )

    assert result["action"] == "ok"
    assert provider.probe_calls == [
        {
            "access_token": "access-initial",
            "team_id": "",
            "proxy_url": "http://jp-proxy.example.test:8080",
            "model": "",
        }
    ]
    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert credential.credential_status == "active"
        assert credential.last_probe_status == "ok"
        assert credential.last_probe_at is not None
        assert credential.failure_code == ""


def test_transient_probe_failure_keeps_credential_active(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    provider = _provider(heartbeat_rows)
    provider.probe_results = [
        {"status": "failed", "http_status": 429, "error_code": "http_429"}
    ]
    flow = _workflow(heartbeat_rows, provider)

    with pytest.raises(PersonalCodexCredentialHeartbeatError, match="http_429"):
        flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert credential.credential_status == "active"
        assert credential.last_probe_status == "error"
        assert credential.failure_code == "http_429"


def test_network_probe_failure_keeps_credential_active(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    provider = _provider(heartbeat_rows)
    provider.probe_results = [OSError("network unavailable")]
    flow = _workflow(heartbeat_rows, provider)

    with pytest.raises(
        PersonalCodexCredentialHeartbeatError,
        match="codex_probe_request_failed",
    ):
        flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert credential.credential_status == "active"
        assert credential.last_probe_status == "error"
        assert credential.failure_code == "codex_probe_request_failed"


def test_unauthorized_probe_refreshes_and_probes_again_without_reauthorization(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    provider = _provider(heartbeat_rows)
    provider.probe_results = [
        {"status": "failed", "http_status": 401, "unauthorized": True},
        {"status": "ok"},
    ]
    refreshed_claims = provider.claims_by_token["access-refreshed"]
    assert isinstance(refreshed_claims, TokenClaims)
    provider.refresh_result = OAuthTokenSet(
        access_token="access-refreshed",
        id_token="",
        refresh_token="refresh-next",
        expires_at=datetime.now(UTC),
        claims=refreshed_claims,
    )
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=reauthorize_calls.append,
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "refreshed"
    assert reauthorize_calls == []
    assert [call["access_token"] for call in provider.probe_calls] == [
        "access-initial",
        "access-refreshed",
    ]
    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert credential.access_token == "access-refreshed"
        assert credential.id_token == "id-initial"
        assert credential.refresh_token == "refresh-next"
        assert credential.credential_status == "active"
        assert credential.last_probe_status == "ok"


def test_invalid_grant_reauthorizes_and_repushes_original_channel(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    channel_id = f"channel-{uuid4().hex}"
    _add_binding(
        heartbeat_rows,
        downstream_channel_id=channel_id,
        push_status="pushed",
        downstream_external_id="remote-credential-1",
        pushed_count=1,
    )
    provider = _provider(heartbeat_rows)
    provider.probe_results = [
        {"status": "failed", "http_status": 401, "unauthorized": True}
    ]
    provider.refresh_result = OpenAIOAuthRefreshError(
        http_status=400,
        error_code="invalid_grant",
        error_description="refresh token is invalid",
    )
    reauthorize_calls: list[str] = []
    repush_calls: list[tuple[str, str]] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=_reauthorizer(heartbeat_rows, reauthorize_calls),
        repush=_repusher(heartbeat_rows, repush_calls),
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "reauthorized_repush"
    assert result["repushed"] is True
    assert reauthorize_calls == [heartbeat_rows.membership_id]
    assert repush_calls == [(heartbeat_rows.credential_id, channel_id)]
    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        binding = session.get(SpacePushBindingModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert binding is not None
        assert credential.credential_status == "active"
        assert credential.access_token == "access-reauthorized"
        assert binding.push_status == "pushed"
        assert binding.downstream_channel_id == channel_id
        assert binding.pushed_count == 2


def test_reauthorization_resets_manual_export_to_unpushed(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    _set_credential_status(heartbeat_rows, "invalid")
    _add_binding(
        heartbeat_rows,
        downstream_channel_id=None,
        push_status="pushed",
        downstream_external_id=f"manual-export-{uuid4()}",
        pushed_count=2,
        failed_push_count=1,
        recycle_status="failed",
        error_code="old-error",
        error_message="old-message",
    )
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=_reauthorizer(heartbeat_rows, reauthorize_calls),
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "reauthorized_manual_export_reset"
    assert reauthorize_calls == [heartbeat_rows.membership_id]
    assert provider.probe_calls == []
    with heartbeat_rows.session_factory() as session:
        binding = session.get(SpacePushBindingModel, heartbeat_rows.credential_id)
        assert binding is not None
        assert binding.push_status == "none"
        assert binding.downstream_external_id == ""
        assert binding.recycle_status == "none"
        assert binding.recycled_at is None
        assert binding.error_code == ""
        assert binding.error_message == ""
        assert binding.pushed_count == 2
        assert binding.failed_push_count == 1


def test_reauthorization_without_binding_does_not_repush(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    _set_credential_status(heartbeat_rows, "expired")
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    repush_calls: list[tuple[str, str]] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=_reauthorizer(heartbeat_rows, reauthorize_calls),
        repush=lambda credential_id, channel_id: repush_calls.append(
            (credential_id, channel_id)
        ),
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "reauthorized"
    assert reauthorize_calls == [heartbeat_rows.membership_id]
    assert repush_calls == []


def test_token_identity_mismatch_reauthorizes_before_probe(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    provider = _provider(heartbeat_rows)
    provider.claims_by_token["access-initial"] = TokenClaims(
        token_chatgpt_account_id="wrong-workspace",
        account_id=heartbeat_rows.openai_user_id,
    )
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=_reauthorizer(heartbeat_rows, reauthorize_calls),
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "reauthorized"
    assert result["reason"] == "token_workspace_mismatch"
    assert provider.probe_calls == []
    assert reauthorize_calls == [heartbeat_rows.membership_id]


def test_reauthorization_requires_active_personal_membership(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    _set_credential_status(heartbeat_rows, "invalid")
    with heartbeat_rows.session_factory() as session:
        membership = session.get(SpaceMembershipModel, heartbeat_rows.membership_id)
        assert membership is not None
        membership.membership_status = "disabled"
        session.commit()
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=reauthorize_calls.append,
    )

    with pytest.raises(
        PersonalCodexCredentialHeartbeatError,
        match="reauthorization_target_missing",
    ):
        flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert reauthorize_calls == []
    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        assert credential.credential_status == "invalid"
        assert credential.last_probe_status == "failed"
        assert credential.failure_code == "reauthorization_target_missing"


def test_revoked_credential_is_skipped(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    _set_credential_status(heartbeat_rows, "revoked")
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=reauthorize_calls.append,
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "skipped"
    assert result["reason"] == "credential_status_revoked"
    assert provider.probe_calls == []
    assert reauthorize_calls == []


def test_unauthorized_probe_with_missing_refresh_fields_reauthorizes_directly(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    with heartbeat_rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, heartbeat_rows.credential_id)
        assert credential is not None
        credential.refresh_token = ""
        credential.codex_client_id = ""
        session.commit()
    provider = _provider(heartbeat_rows)
    provider.probe_results = [
        {"status": "failed", "http_status": 401, "unauthorized": True}
    ]
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=_reauthorizer(heartbeat_rows, reauthorize_calls),
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "reauthorized"
    assert provider.refresh_calls == []
    assert reauthorize_calls == [heartbeat_rows.membership_id]


def test_business_codex_credential_is_outside_personal_heartbeat_scope(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    with heartbeat_rows.session_factory() as session:
        space = session.get(SpaceModel, heartbeat_rows.space_id)
        assert space is not None
        space.space_type = "business"
        space.credential_type = "team_monthly"
        session.commit()
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=reauthorize_calls.append,
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "skipped"
    assert result["reason"] == "not_personal_codex"
    assert provider.probe_calls == []
    assert reauthorize_calls == []


def test_free_personal_codex_credential_is_outside_personal_heartbeat_scope(
    heartbeat_rows: _HeartbeatRows,
) -> None:
    with heartbeat_rows.session_factory() as session:
        space = session.get(SpaceModel, heartbeat_rows.space_id)
        assert space is not None
        space.plan_type = "free"
        session.commit()
    provider = _provider(heartbeat_rows)
    reauthorize_calls: list[str] = []
    flow = _workflow(
        heartbeat_rows,
        provider,
        reauthorize=reauthorize_calls.append,
    )

    result = flow.run(PersonalCodexCredentialHeartbeatInput(heartbeat_rows.credential_id))

    assert result["action"] == "skipped"
    assert result["reason"] == "not_personal_codex"
    assert provider.probe_calls == []
    assert reauthorize_calls == []


def _provider(rows: _HeartbeatRows) -> _OpenAIProvider:
    return _OpenAIProvider(
        workspace_id=rows.workspace_id,
        openai_user_id=rows.openai_user_id,
    )


def _workflow(
    rows: _HeartbeatRows,
    provider: _OpenAIProvider,
    *,
    reauthorize: Callable[[str], Any] | None = None,
    repush: Callable[[str, str], Any] | None = None,
) -> PersonalCodexCredentialHeartbeatWorkflow:
    def unexpected_reauthorization(_membership_id: str) -> None:
        raise AssertionError("reauthorization was not expected")

    def unexpected_repush(_credential_id: str, _channel_id: str) -> None:
        raise AssertionError("repush was not expected")

    return PersonalCodexCredentialHeartbeatWorkflow(
        session_factory=rows.session_factory,
        openai_provider=cast(OpenAIChatGPTProvider, provider),
        proxy_resolver=lambda _user_account_id: "http://jp-proxy.example.test:8080",
        reauthorize=reauthorize or unexpected_reauthorization,
        repush=repush or unexpected_repush,
    )


def _reauthorizer(
    rows: _HeartbeatRows,
    calls: list[str],
) -> Callable[[str], None]:
    def reauthorize(membership_id: str) -> None:
        calls.append(membership_id)
        with rows.session_factory() as session:
            credential = session.get(SpaceCredentialModel, rows.credential_id)
            assert credential is not None
            assert credential.credential_status == "invalid"
            credential.credential_status = "active"
            credential.access_token = "access-reauthorized"
            credential.id_token = "id-reauthorized"
            credential.refresh_token = "refresh-reauthorized"
            credential.codex_client_id = "codex-client-1"
            credential.account_id = rows.openai_user_id
            credential.token_chatgpt_account_id = rows.workspace_id
            credential.last_authorized_at = datetime.now(UTC)
            credential.updated_at = datetime.now(UTC)
            session.commit()

    return reauthorize


def _repusher(
    rows: _HeartbeatRows,
    calls: list[tuple[str, str]],
) -> Callable[[str, str], None]:
    def repush(credential_id: str, downstream_channel_id: str) -> None:
        calls.append((credential_id, downstream_channel_id))
        with rows.session_factory() as session:
            binding = session.get(SpacePushBindingModel, credential_id)
            assert binding is not None
            assert binding.push_status == "failed"
            binding.push_status = "pushed"
            binding.downstream_external_id = "remote-credential-2"
            binding.pushed_count += 1
            binding.updated_at = datetime.now(UTC)
            session.commit()

    return repush


def _set_credential_status(rows: _HeartbeatRows, status: str) -> None:
    with rows.session_factory() as session:
        credential = session.get(SpaceCredentialModel, rows.credential_id)
        assert credential is not None
        credential.credential_status = status
        session.commit()


def _add_binding(
    rows: _HeartbeatRows,
    *,
    downstream_channel_id: str | None,
    push_status: str,
    downstream_external_id: str,
    pushed_count: int,
    failed_push_count: int = 0,
    recycle_status: str = "none",
    error_code: str = "",
    error_message: str = "",
) -> None:
    now = datetime.now(UTC)
    with rows.session_factory() as session:
        session.add(
            SpacePushBindingModel(
                space_credential_id=rows.credential_id,
                space_id=rows.space_id,
                downstream_channel_id=downstream_channel_id,
                push_status=push_status,
                downstream_external_id=downstream_external_id,
                pushed_count=pushed_count,
                failed_push_count=failed_push_count,
                recycle_status=recycle_status,
                error_code=error_code,
                error_message=error_message,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
