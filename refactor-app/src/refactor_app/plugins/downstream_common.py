from __future__ import annotations

from datetime import UTC, datetime

from refactor_app.plugins.contracts import DownstreamCodexPayload


class DownstreamPayloadError(RuntimeError):
    pass


def validate_codex_payload(payload: DownstreamCodexPayload) -> None:
    if not payload.access_token:
        raise DownstreamPayloadError("access_token is required")
    if not payload.refresh_token:
        raise DownstreamPayloadError("refresh_token is required")
    if not payload.email:
        raise DownstreamPayloadError("email is required")
    if not payload.account_id:
        raise DownstreamPayloadError("account_id is required")
    if not payload.downstream_chatgpt_account_id:
        raise DownstreamPayloadError("downstream_chatgpt_account_id is required")
    if not payload.token_chatgpt_account_id:
        raise DownstreamPayloadError("token_chatgpt_account_id is required")


def codex_credentials_body(payload: DownstreamCodexPayload) -> dict:
    validate_codex_payload(payload)
    expires_at = int(payload.expires_at.timestamp()) if payload.expires_at else None
    return {
        "id_token": payload.id_token,
        "access_token": payload.access_token,
        "refresh_token": payload.refresh_token,
        "account_id": payload.account_id,
        "email": payload.email,
        "last_refresh": now_iso(),
        "expired": expires_at,
        "type": "codex",
        "chatgpt_account_id": payload.downstream_chatgpt_account_id,
        "chatgpt_user_id": payload.chatgpt_user_id,
        "client_id": payload.client_id,
        "expires_at": expires_at,
        "plan_type": payload.plan_type or payload.plan_tag,
    }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
