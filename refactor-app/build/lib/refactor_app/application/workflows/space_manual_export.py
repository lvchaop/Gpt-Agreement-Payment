from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.space_credential_payload import (
    build_space_credential_payload,
)
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceModel,
    SpacePushAttemptModel,
    SpacePushBindingModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import DownstreamCodexPayload
from refactor_app.plugins.downstream_common import codex_credentials_body

MANUAL_EXPORT_ENDPOINT = "manual_export"
MANUAL_EXPORT_PREFIX = "manual-export-"
SUPPORTED_CREDENTIAL_TYPES = {"personal_account", "team_5h_weekly", "team_monthly"}


class SpaceManualExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceManualExportResult:
    content: bytes
    filename: str
    export_batch_id: str
    exported_count: int


def export_unpushed_sub2api_jsonl(
    *,
    session: Session,
    credential_type: str = "",
    space_id: str = "",
    limit: int = 0,
) -> SpaceManualExportResult:
    normalized_type = credential_type.strip()
    if normalized_type and normalized_type not in SUPPORTED_CREDENTIAL_TYPES:
        raise SpaceManualExportError(f"unsupported_credential_type:{normalized_type}")
    normalized_limit = max(0, int(limit or 0))
    stmt = (
        select(SpaceCredentialModel, SpaceModel, UserAccountModel)
        .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
        .join(UserAccountModel, UserAccountModel.id == SpaceCredentialModel.user_account_id)
        .outerjoin(
            SpacePushBindingModel,
            SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
        )
        .where(
            SpaceCredentialModel.credential_status == "active",
            SpaceCredentialModel.access_token != "",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type.in_(SUPPORTED_CREDENTIAL_TYPES),
            or_(
                SpacePushBindingModel.space_credential_id.is_(None),
                SpacePushBindingModel.push_status.in_(("none", "skipped")),
            ),
            or_(
                SpaceModel.credential_type != "personal_account",
                SpaceCredentialModel.refresh_token != "",
            ),
            or_(
                SpaceModel.credential_type == "personal_account",
                SpaceCredentialModel.account_id != "",
                UserAccountModel.openai_user_id != "",
            ),
        )
        .order_by(SpaceCredentialModel.updated_at.asc(), SpaceCredentialModel.id.asc())
        .with_for_update(skip_locked=True, of=SpaceCredentialModel)
    )
    if normalized_type:
        stmt = stmt.where(SpaceModel.credential_type == normalized_type)
    if space_id.strip():
        stmt = stmt.where(SpaceCredentialModel.space_id == space_id.strip())
    if normalized_limit:
        stmt = stmt.limit(normalized_limit)
    rows = session.execute(stmt).all()
    if not rows:
        raise SpaceManualExportError("no_unpushed_credentials")

    exported_at = datetime.now(UTC)
    export_batch_id = f"{MANUAL_EXPORT_PREFIX}{uuid4()}"
    lines = _render_rows(rows=rows, session=session, exported_at=exported_at)
    for credential, space, user in rows:
        binding = session.get(SpacePushBindingModel, credential.id)
        if binding is None:
            binding = SpacePushBindingModel(
                space_credential_id=credential.id,
                space_id=space.id,
                downstream_channel_id=None,
                push_status="pushed",
                downstream_external_id=export_batch_id,
                pushed_count=1,
                failed_push_count=0,
                used_count=0,
                recycle_status="none",
                created_at=exported_at,
                updated_at=exported_at,
            )
            session.add(binding)
        else:
            binding.space_id = space.id
            binding.downstream_channel_id = None
            binding.push_status = "pushed"
            binding.downstream_external_id = export_batch_id
            binding.pushed_count += 1
            binding.recycle_status = "none"
            binding.recycled_at = None
            binding.error_code = ""
            binding.error_message = ""
            binding.updated_at = exported_at
        session.add(
            SpacePushAttemptModel(
                id=f"space-push-attempt-{uuid4()}",
                space_credential_id=credential.id,
                space_id=space.id,
                downstream_channel_id=None,
                payload_type=space.credential_type,
                request_endpoint=MANUAL_EXPORT_ENDPOINT,
                request_body_json={
                    "export_batch_id": export_batch_id,
                    "format": "sub2api_jsonl",
                    "space_credential_id": credential.id,
                    "email": user.email,
                },
                response_json={"exported": True},
                attempt_status="pushed",
                started_at=exported_at,
                finished_at=exported_at,
                created_at=exported_at,
            )
        )
    return SpaceManualExportResult(
        content=_jsonl_bytes(lines),
        filename=_export_filename(prefix="sub2api-unpushed", at=exported_at),
        export_batch_id=export_batch_id,
        exported_count=len(lines),
    )


def redownload_sub2api_jsonl(
    *,
    session: Session,
    space_credential_ids: list[str] | None = None,
    export_batch_id: str = "",
) -> SpaceManualExportResult:
    requested_ids = list(
        dict.fromkeys(item.strip() for item in (space_credential_ids or []) if item.strip())
    )
    normalized_batch_id = export_batch_id.strip()
    if bool(requested_ids) == bool(normalized_batch_id):
        raise SpaceManualExportError(
            "provide_exactly_one_of_space_credential_ids_or_export_batch_id"
        )
    if normalized_batch_id and not normalized_batch_id.startswith(MANUAL_EXPORT_PREFIX):
        raise SpaceManualExportError("invalid_manual_export_batch_id")

    stmt = (
        select(SpaceCredentialModel, SpaceModel, UserAccountModel)
        .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
        .join(UserAccountModel, UserAccountModel.id == SpaceCredentialModel.user_account_id)
        .join(
            SpacePushBindingModel,
            SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
        )
        .where(
            SpacePushBindingModel.downstream_channel_id.is_(None),
            SpacePushBindingModel.downstream_external_id.like(f"{MANUAL_EXPORT_PREFIX}%"),
            SpaceCredentialModel.access_token != "",
        )
    )
    if requested_ids:
        stmt = stmt.where(SpaceCredentialModel.id.in_(requested_ids))
    else:
        stmt = stmt.where(SpacePushBindingModel.downstream_external_id == normalized_batch_id)
    rows = session.execute(
        stmt.order_by(SpaceCredentialModel.updated_at.asc(), SpaceCredentialModel.id.asc())
    ).all()
    found_ids = {credential.id for credential, _space, _user in rows}
    if requested_ids:
        missing_ids = [item for item in requested_ids if item not in found_ids]
        if missing_ids:
            raise SpaceManualExportError(
                f"credentials_not_manually_exported:{','.join(missing_ids)}"
            )
    if not rows:
        raise SpaceManualExportError("manual_export_credentials_not_found")

    original_export_times = _manual_export_times(
        session=session,
        credential_ids=[credential.id for credential, _space, _user in rows],
    )
    lines = _render_rows(
        rows=rows,
        session=session,
        exported_at_by_credential_id=original_export_times,
    )
    exported_at = min(original_export_times.values())
    batch_label = normalized_batch_id or "selected"
    return SpaceManualExportResult(
        content=_jsonl_bytes(lines),
        filename=_export_filename(prefix=f"sub2api-redownload-{batch_label}", at=exported_at),
        export_batch_id=normalized_batch_id,
        exported_count=len(lines),
    )


def _render_rows(
    *,
    rows: list,
    session: Session,
    exported_at: datetime | None = None,
    exported_at_by_credential_id: dict[str, datetime] | None = None,
) -> list[dict]:
    lines: list[dict] = []
    for credential, space, user in rows:
        line_exported_at = (exported_at_by_credential_id or {}).get(credential.id, exported_at)
        if line_exported_at is None:
            raise SpaceManualExportError(f"manual_export_time_missing:{credential.id}")
        try:
            payload, _payload_type = build_space_credential_payload(
                session=session,
                user=user,
                space=space,
                credential=credential,
                provider_type="sub2api",
                exported_at=line_exported_at,
            )
            if isinstance(payload, DownstreamCodexPayload):
                line = codex_credentials_body(payload, last_refresh=line_exported_at)
                line["account_id"] = f"{payload.account_id}_{space.external_space_id}"
                lines.append(line)
            else:
                lines.append(payload)
        except Exception as exc:
            raise SpaceManualExportError(
                f"credential_payload_invalid:{credential.id}:{type(exc).__name__}:{exc}"
            ) from exc
    return lines


def _manual_export_times(
    *,
    session: Session,
    credential_ids: list[str],
) -> dict[str, datetime]:
    rows = session.execute(
        select(
            SpacePushAttemptModel.space_credential_id,
            func.min(SpacePushAttemptModel.started_at),
        )
        .where(
            SpacePushAttemptModel.space_credential_id.in_(credential_ids),
            SpacePushAttemptModel.request_endpoint == MANUAL_EXPORT_ENDPOINT,
            SpacePushAttemptModel.attempt_status == "pushed",
        )
        .group_by(SpacePushAttemptModel.space_credential_id)
    ).all()
    result = {str(credential_id): exported_at for credential_id, exported_at in rows}
    missing_ids = [credential_id for credential_id in credential_ids if credential_id not in result]
    if missing_ids:
        raise SpaceManualExportError(f"manual_export_time_missing:{','.join(missing_ids)}")
    return result


def _jsonl_bytes(lines: list[dict]) -> bytes:
    text = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in lines
    )
    return f"{text}\n".encode()


def _export_filename(*, prefix: str, at: datetime) -> str:
    safe_prefix = "".join(char if char.isalnum() or char in "-_" else "-" for char in prefix)
    return f"{safe_prefix}-{at.strftime('%Y%m%d-%H%M%S')}.txt"
