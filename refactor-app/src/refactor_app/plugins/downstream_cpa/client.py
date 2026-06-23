from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult
from refactor_app.plugins.downstream_common import validate_codex_payload


class CpaClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class CpaClientConfig:
    base_url: str
    admin_key: str
    timeout_s: float = 30.0

    def validate(self) -> None:
        if not self.base_url:
            raise CpaClientError("cpa base_url is required")
        if not self.admin_key:
            raise CpaClientError("cpa admin_key is required")
        if self.timeout_s <= 0:
            raise CpaClientError("cpa timeout_s must be positive")


class CpaClient:
    def __init__(
        self,
        config: CpaClientConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._client = http_client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_s,
            headers={"Authorization": f"Bearer {config.admin_key}"},
        )

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        name, body = build_cpa_auth_file(payload)
        response = self._client.post(
            "/v0/management/auth-files",
            params={"name": name},
            json=body,
        )
        raw = _safe_json(response)
        if response.is_error:
            return DownstreamPushResult(
                pushed=False,
                error_code=f"http_{response.status_code}",
                error_message=str(raw.get("message") or raw.get("error") or ""),
                raw=raw,
            )
        return DownstreamPushResult(
            pushed=True,
            downstream_external_id=str(raw.get("id") or name),
            raw=raw,
        )


def build_cpa_auth_file(payload: DownstreamCodexPayload) -> tuple[str, dict]:
    validate_codex_payload(payload)
    plan_tag = payload.plan_tag or payload.plan_type or "team"
    tag = hashlib.md5(payload.email.encode()).hexdigest()[:8]
    name = f"codex-{tag}-{payload.email}-{plan_tag}.json"
    body = {
        "id_token": payload.id_token,
        "access_token": payload.access_token,
        "refresh_token": payload.refresh_token,
        "account_id": payload.account_id,
        "email": payload.email,
        "last_refresh": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expired": payload.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if payload.expires_at
        else "",
        "type": "codex",
    }
    return name, body


def _safe_json(response: httpx.Response) -> dict:
    if not response.text:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {"body": response.text}
    return payload if isinstance(payload, dict) else {"body": payload}
