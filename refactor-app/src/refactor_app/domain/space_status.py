from __future__ import annotations

from refactor_app.domain.enums import WorkspaceStatus

OPERATOR_SPACE_STATUSES = {
    WorkspaceStatus.ACTIVE.value,
    WorkspaceStatus.DISABLED.value,
}


def space_status_after_discovery(current_status: str) -> str:
    if str(current_status or "").strip() == WorkspaceStatus.DISABLED.value:
        return WorkspaceStatus.DISABLED.value
    return WorkspaceStatus.ACTIVE.value
