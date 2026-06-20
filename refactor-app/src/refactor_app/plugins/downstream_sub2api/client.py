from __future__ import annotations

from dataclasses import dataclass

import httpx

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult
from refactor_app.plugins.downstream_common import codex_credentials_body, validate_codex_payload


class Sub2ApiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class Sub2ApiClientConfig:
    base_url: str
    admin_key: str
    timeout_s: float = 30.0
    update_existing: bool = False

    def validate(self) -> None:
        if not self.base_url:
            raise Sub2ApiClientError("sub2api base_url is required")
        if not self.admin_key:
            raise Sub2ApiClientError("sub2api admin_key is required")
        if self.timeout_s <= 0:
            raise Sub2ApiClientError("sub2api timeout_s must be positive")


class Sub2ApiClient:
    def __init__(
        self,
        config: Sub2ApiClientConfig,
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
        body = build_sub2api_import_payload(payload, update_existing=self._config.update_existing)
        response = self._client.post("/api/v1/admin/accounts/import/codex-session", json=body)
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
            downstream_external_id=str(raw.get("id") or raw.get("account_id") or ""),
            raw=raw,
        )


def build_sub2api_import_payload(
    payload: DownstreamCodexPayload,
    *,
    update_existing: bool = False,
) -> dict:
    validate_codex_payload(payload)
    credentials = codex_credentials_body(payload)
    account = {
        "name": payload.email,
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
    }
    return {
        "accounts": [account],
        "update_existing": update_existing,
    }


def _safe_json(response: httpx.Response) -> dict:
    if not response.text:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {"body": response.text}
    return payload if isinstance(payload, dict) else {"body": payload}
