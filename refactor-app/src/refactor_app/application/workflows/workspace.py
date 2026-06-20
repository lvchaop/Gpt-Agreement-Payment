from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.domain.enums import WorkspaceStatus
from refactor_app.infrastructure.db.models import TeamWorkspaceModel
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork


class WorkspaceWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportTeamWorkspaceInput:
    external_workspace_id: str
    name: str
    plan_type: str = ""
    seat_limit: int = 0
    workspace_status: str = WorkspaceStatus.UNKNOWN.value
    provider: str = "openai_chatgpt"


class ImportTeamWorkspaceWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, input_: ImportTeamWorkspaceInput) -> str:
        if not input_.external_workspace_id:
            raise WorkspaceWorkflowError("external_workspace_id is required")
        if not input_.name:
            raise WorkspaceWorkflowError("name is required")
        if input_.provider != "openai_chatgpt":
            raise WorkspaceWorkflowError("team workspace provider must be openai_chatgpt")
        if input_.seat_limit < 0:
            raise WorkspaceWorkflowError("seat_limit must be non-negative")

        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.team_workspaces is None:
                raise WorkspaceWorkflowError("team workspace repository is not initialized")
            workspace = uow.team_workspaces.upsert_from_values(
                {
                    "id": f"team-workspace-{uuid4()}",
                    "provider": input_.provider,
                    "external_workspace_id": input_.external_workspace_id,
                    "name": input_.name,
                    "plan_type": input_.plan_type,
                    "seat_limit": input_.seat_limit,
                    "workspace_status": input_.workspace_status,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return workspace.id


def imported_team_workspace_model(
    input_: ImportTeamWorkspaceInput,
    now: datetime,
) -> TeamWorkspaceModel:
    return TeamWorkspaceModel(
        id=f"team-workspace-{uuid4()}",
        provider=input_.provider,
        external_workspace_id=input_.external_workspace_id,
        name=input_.name,
        plan_type=input_.plan_type,
        seat_limit=input_.seat_limit,
        workspace_status=input_.workspace_status,
        created_at=now,
        updated_at=now,
    )
