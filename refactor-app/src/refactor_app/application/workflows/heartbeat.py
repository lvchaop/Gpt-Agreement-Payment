from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import _active_proxy, _proxy_url
from refactor_app.domain.enums import HeartbeatStatus
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
            proxy = _active_proxy(uow.session, credential.user_account_id) if uow.session else None
            proxy_url = _proxy_url(proxy) if proxy is not None else ""

            if credential.token_chatgpt_account_id != team_id:
                credential.last_heartbeat_status = HeartbeatStatus.FAILED.value
                credential.last_heartbeat_error_code = "workspace_mismatch"
                credential.last_heartbeat_error_message = (
                    "token workspace does not match target workspace"
                )
                failed_message = credential.last_heartbeat_error_message
            else:
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
                    credential.last_heartbeat_status = HeartbeatStatus.FAILED.value
                    credential.last_heartbeat_error_code = "heartbeat_failed"
                    credential.last_heartbeat_error_message = (
                        f"attempt={current_attempt}/{CODEX_HEARTBEAT_ATTEMPTS}: {exc}"
                    )[:500]
                    failed_message = credential.last_heartbeat_error_message
                else:
                    credential.last_heartbeat_status = HeartbeatStatus.OK.value
                    credential.last_heartbeat_error_code = ""
                    credential.last_heartbeat_error_message = (
                        f"heartbeat ok: {CODEX_HEARTBEAT_ATTEMPTS} consecutive attempts"
                    )
            completed_at = datetime.now(UTC)
            credential.last_heartbeat_at = completed_at
            credential.updated_at = completed_at
            credential_id = credential.id
        if failed_message:
            raise HeartbeatWorkflowError(failed_message)
        return credential_id
