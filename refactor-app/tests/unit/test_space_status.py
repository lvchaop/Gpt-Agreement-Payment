from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from refactor_app.api.routes.resources import PatchSpaceRequest, patch_space
from refactor_app.domain.space_status import space_status_after_discovery
from refactor_app.infrastructure.db.models import SpaceModel


class _Session:
    def __init__(self, space: SpaceModel | None) -> None:
        self.space = space
        self.commit_count = 0

    def get(self, model: type[SpaceModel], key: str) -> SpaceModel | None:
        if model is SpaceModel and self.space is not None and self.space.id == key:
            return self.space
        return None

    def commit(self) -> None:
        self.commit_count += 1


def test_patch_space_disables_and_enables_without_deleting_data() -> None:
    space = _space("active")
    session = _Session(space)

    disabled = patch_space(
        space.id,
        PatchSpaceRequest(space_status="disabled"),
        session,  # type: ignore[arg-type]
    )
    enabled = patch_space(
        space.id,
        PatchSpaceRequest(space_status="active"),
        session,  # type: ignore[arg-type]
    )

    assert disabled["space_status"] == "disabled"
    assert enabled["space_status"] == "active"
    assert session.commit_count == 2
    assert space.external_space_id == "workspace-status-test"


def test_patch_space_rejects_non_operator_status() -> None:
    space = _space("active")

    with pytest.raises(HTTPException) as exc_info:
        patch_space(
            space.id,
            PatchSpaceRequest(space_status="error"),
            _Session(space),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400


def test_discovery_preserves_operator_disabled_status() -> None:
    assert space_status_after_discovery("disabled") == "disabled"
    assert space_status_after_discovery("active") == "active"
    assert space_status_after_discovery("error") == "active"


def _space(status: str) -> SpaceModel:
    now = datetime.now(UTC)
    return SpaceModel(
        id="space-status-test",
        provider="openai_chatgpt",
        external_space_id="workspace-status-test",
        owner_user_account_id="",
        name="Status test",
        space_type="business",
        auth_mode="backend_access_token",
        credential_type="team_monthly",
        plan_type="team",
        seat_limit=0,
        seats_in_use=0,
        seats_entitled=0,
        space_status=status,
        source_admin_session_id="",
        raw_space_json={},
        last_subscription_sync_at=None,
        last_probe_at=None,
        created_at=now,
        updated_at=now,
    )
