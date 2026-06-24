from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.domain.enums import CredentialStatus
from refactor_app.infrastructure.db.models import MembershipModel
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    acquire_codex_rt_with_browser_login,
)


class CodexCredentialWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildCodexCredentialInput:
    user_account_id: str
    team_workspace_id: str
    codex_client_id: str
    force_reauthorize: bool = False


@dataclass(frozen=True)
class BuildCodexCredentialWorkInput:
    user_account_id: str
    team_workspace_id: str
    codex_client_id: str
    force_reauthorize: bool = False


class BuildCodexCredentialWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._mail_provider = mail_provider

    def run(self, input_: BuildCodexCredentialInput) -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.user_account_auth is None:
                raise CodexCredentialWorkflowError(
                    "user_account_auth repository is not initialized"
                )
            if uow.team_workspaces is None:
                raise CodexCredentialWorkflowError("team workspace repository is not initialized")
            if uow.codex_oauth_credentials is None:
                raise CodexCredentialWorkflowError("credential repository is not initialized")

            auth = uow.user_account_auth.get(input_.user_account_id)
            workspace = uow.team_workspaces.get(input_.team_workspace_id)
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise CodexCredentialWorkflowError("missing_user_account")
            if auth is None:
                raise CodexCredentialWorkflowError("missing_auth")
            if not auth.password:
                raise CodexCredentialWorkflowError("missing_password")
            if workspace is None or not workspace.external_workspace_id:
                raise CodexCredentialWorkflowError("missing_workspace")

            existing = uow.codex_oauth_credentials.get_current(
                user_account_id=input_.user_account_id,
                team_workspace_id=input_.team_workspace_id,
                codex_client_id=input_.codex_client_id,
            )
            if (
                not input_.force_reauthorize
                and existing is not None
                and existing.credential_status == CredentialStatus.ACTIVE.value
                and existing.expires_at is not None
                and existing.expires_at > now
                and existing.token_chatgpt_account_id == workspace.external_workspace_id
            ):
                return existing.id

        proxy_url = self._active_proxy_url(input_.user_account_id)
        result = acquire_codex_rt_with_browser_login(
            email=user.email,
            password=auth.password,
            mail_provider=self._mail_provider,
            proxy=proxy_url,
            codex_client_id=input_.codex_client_id,
            target_workspace_id=workspace.external_workspace_id,
            target_workspace_name=workspace.name,
        )
        if not result.ok:
            raise CodexCredentialWorkflowError(_result_error(result))
        if not result.access_token:
            raise CodexCredentialWorkflowError("missing_access_token")

        claims = self._openai_provider.decode_access_token(result.access_token)
        if claims.token_chatgpt_account_id != workspace.external_workspace_id:
            raise CodexCredentialWorkflowError(
                "workspace_mismatch:"
                f"expected={workspace.external_workspace_id},"
                f"actual={claims.token_chatgpt_account_id}"
            )
        expires_at = _jwt_expires_at(result.access_token)
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            current_user = uow.user_accounts.get(input_.user_account_id)
            if current_user is None:
                raise CodexCredentialWorkflowError("missing_user_account")
            credential = uow.codex_oauth_credentials.upsert_from_values(
                {
                    "id": f"codex-credential-{uuid4()}",
                    "user_account_id": input_.user_account_id,
                    "team_workspace_id": input_.team_workspace_id,
                    "codex_client_id": input_.codex_client_id,
                    "credential_status": CredentialStatus.ACTIVE.value,
                    "account_id": claims.account_id,
                    "token_chatgpt_account_id": claims.token_chatgpt_account_id,
                    "access_token": result.access_token,
                    "id_token": result.id_token,
                    "refresh_token": result.refresh_token,
                    "expires_at": expires_at,
                    "last_refresh_at": now,
                    "failure_code": "",
                    "failure_message": "",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            membership = uow.session.scalars(
                select(MembershipModel).where(
                    MembershipModel.user_account_id == input_.user_account_id,
                    MembershipModel.team_workspace_id == input_.team_workspace_id,
                )
            ).first()
            if membership is not None and claims.chatgpt_account_user_id:
                membership.remote_user_id = claims.chatgpt_account_user_id
                membership.remote_synced_at = now
                membership.updated_at = now
            if (
                current_user.openai_user_id != claims.chatgpt_account_user_id
                and claims.chatgpt_account_user_id
            ):
                current_user.openai_user_id = claims.chatgpt_account_user_id
                current_user.updated_at = now
            return credential.id

    def _active_proxy_url(self, user_account_id: str) -> str:
        return ensure_account_proxy_url(
            self._session_factory,
            user_account_id,
            bind_reason="codex_credential_authorize",
        )


class BuildCodexCredentialWorkItemWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._workflow = BuildCodexCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=openai_provider,
            mail_provider=mail_provider,
        )

    def run(self, input_: BuildCodexCredentialWorkInput) -> str:
        return self._workflow.run(
            BuildCodexCredentialInput(
                user_account_id=input_.user_account_id,
                team_workspace_id=input_.team_workspace_id,
                codex_client_id=input_.codex_client_id,
                force_reauthorize=input_.force_reauthorize,
            )
        )


def _jwt_expires_at(access_token: str) -> datetime | None:
    parts = str(access_token or "").split(".")
    if len(parts) < 2:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        exp = int(data.get("exp") or 0)
    except Exception:
        return None
    if exp <= 0:
        return None
    return datetime.fromtimestamp(exp, tz=UTC)


def _result_error(result) -> str:
    code = str(getattr(result, "failure_code", "") or "codex_workspace_authorize_failed")
    message = str(getattr(result, "failure_message", "") or "")
    final_url = str(getattr(result, "final_url", "") or "")
    detail = code
    if message:
        detail = f"{detail}: {message}"
    if final_url:
        detail = f"{detail}; final_url={final_url}"
    return detail[:1000]
