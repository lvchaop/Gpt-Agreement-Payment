from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.domain.enums import CredentialStatus, HeartbeatStatus
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import OpenAIChatGPTProvider

CODEX_HEARTBEAT_ATTEMPTS = 40
CODEX_HEARTBEAT_MODEL = "gpt-5.5"


class HeartbeatWorkflowError(RuntimeError):
    pass


class HeartbeatCodexCredentialWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(self, *, codex_credential_id: str) -> str:
        failed_message = ""
        credential_id = codex_credential_id
        with UnitOfWork(self._session_factory) as uow:
            if uow.codex_oauth_credentials is None:
                raise HeartbeatWorkflowError("credential repository is not initialized")
            if uow.team_workspaces is None:
                raise HeartbeatWorkflowError("team workspace repository is not initialized")

            credential = uow.codex_oauth_credentials.get(codex_credential_id)
            if credential is None:
                raise HeartbeatWorkflowError(f"codex credential not found: {codex_credential_id}")
            workspace = uow.team_workspaces.get(credential.team_workspace_id)
            if workspace is None:
                raise HeartbeatWorkflowError(
                    f"team workspace not found: {credential.team_workspace_id}"
                )
            access_token = credential.access_token
            team_id = workspace.external_workspace_id
            proxy_url = ensure_account_proxy_url(
                self._session_factory,
                credential.user_account_id,
                bind_reason="codex_heartbeat",
            )

            if credential.token_chatgpt_account_id != team_id:
                credential.last_heartbeat_status = HeartbeatStatus.FAILED.value
                credential.last_heartbeat_error_code = "workspace_mismatch"
                credential.last_heartbeat_error_message = (
                    "token workspace does not match target workspace"
                )
                failed_message = credential.last_heartbeat_error_message
            else:
                ok, failed_message = self._run_heartbeat_with_refresh_recovery(
                    credential=credential,
                    access_token=access_token,
                    team_id=team_id,
                    proxy_url=proxy_url,
                )
                if ok:
                    credential.last_heartbeat_status = HeartbeatStatus.OK.value
                    credential.last_heartbeat_error_code = ""
                    credential.last_heartbeat_error_message = (
                        f"heartbeat ok: {CODEX_HEARTBEAT_ATTEMPTS} consecutive attempts"
                    )
                else:
                    credential.last_heartbeat_status = HeartbeatStatus.FAILED.value
                    credential.last_heartbeat_error_code = "heartbeat_failed"
                    credential.last_heartbeat_error_message = failed_message[:500]
            completed_at = datetime.now(UTC)
            credential.last_heartbeat_at = completed_at
            credential.updated_at = completed_at
            credential_id = credential.id
        if failed_message:
            raise HeartbeatWorkflowError(failed_message)
        return credential_id

    def _run_heartbeat_with_refresh_recovery(
        self,
        *,
        credential,
        access_token: str,
        team_id: str,
        proxy_url: str,
    ) -> tuple[bool, str]:
        ok, message = self._run_heartbeat_attempts(
            access_token=access_token,
            team_id=team_id,
            proxy_url=proxy_url,
        )
        if ok or not _is_unauthorized_heartbeat_error(message):
            return ok, message

        if not credential.refresh_token:
            return False, f"{message}; refresh skipped: missing_refresh_token"
        try:
            tokens = self._openai_provider.refresh_workspace_token(
                refresh_token=credential.refresh_token,
                external_workspace_id=team_id,
                client_id=credential.codex_client_id,
            )
        except Exception as exc:
            credential.credential_status = CredentialStatus.ERROR.value
            credential.failure_code = type(exc).__name__[:200]
            credential.failure_message = str(exc)[:1000]
            return False, f"{message}; refresh failed: {type(exc).__name__}: {exc}"

        now = datetime.now(UTC)
        credential.access_token = tokens.access_token
        credential.id_token = tokens.id_token
        credential.refresh_token = tokens.refresh_token
        credential.expires_at = tokens.expires_at
        credential.last_refresh_at = now
        credential.credential_status = CredentialStatus.ACTIVE.value
        credential.failure_code = ""
        credential.failure_message = ""
        credential.updated_at = now
        return self._run_heartbeat_attempts(
            access_token=tokens.access_token,
            team_id=team_id,
            proxy_url=proxy_url,
        )

    def _run_heartbeat_attempts(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str,
    ) -> tuple[bool, str]:
        current_attempt = 0
        try:
            for attempt in range(1, CODEX_HEARTBEAT_ATTEMPTS + 1):
                current_attempt = attempt
                self._openai_provider.heartbeat_codex_credential(
                    access_token=access_token,
                    team_id=team_id,
                    proxy_url=proxy_url,
                    model=CODEX_HEARTBEAT_MODEL,
                )
        except Exception as exc:
            return (
                False,
                f"attempt={current_attempt}/{CODEX_HEARTBEAT_ATTEMPTS}: {exc}",
            )
        return True, ""


def _is_unauthorized_heartbeat_error(message: str) -> bool:
    text = str(message or "").lower()
    return "http_status=401" in text or "http_401" in text or " 401" in text
