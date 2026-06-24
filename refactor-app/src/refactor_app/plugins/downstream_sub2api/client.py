from __future__ import annotations

from dataclasses import dataclass
import json

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
    concurrency: int = 0
    group_ids: tuple[int, ...] = ()

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
        body = build_sub2api_import_payload(
            payload,
            update_existing=self._config.update_existing,
            concurrency=self._config.concurrency,
            group_ids=self._config.group_ids,
        )
        response = self._client.post("/api/v1/admin/accounts/import/codex-session", json=body)
        raw = _safe_json(response)
        import_error = _sub2api_import_error(raw)
        if response.is_error or import_error:
            return DownstreamPushResult(
                pushed=False,
                error_code=f"http_{response.status_code}",
                error_message=import_error or str(raw.get("message") or raw.get("error") or ""),
                raw=raw,
            )
        return DownstreamPushResult(
            pushed=True,
            downstream_external_id=_sub2api_external_id(raw),
            raw=raw,
        )

def build_sub2api_import_payload(
    payload: DownstreamCodexPayload,
    *,
    update_existing: bool = False,
    concurrency: int = 0,
    group_ids: tuple[int, ...] = (),
) -> dict:
    validate_codex_payload(payload)
    credentials = codex_credentials_body(payload)
    body = {
        "content": json.dumps(credentials, ensure_ascii=False, separators=(",", ":")),
        "name": f"codex-{payload.email}-{payload.plan_type or payload.plan_tag or 'team'}.json",
        "update_existing": update_existing,
    }
    if concurrency > 0:
        body["concurrency"] = int(concurrency)
    if group_ids:
        body["group_ids"] = [int(group_id) for group_id in group_ids]
    return body


def _safe_json(response: httpx.Response) -> dict:
    if not response.text:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {"body": response.text}
    return payload if isinstance(payload, dict) else {"body": payload}


def _sub2api_import_error(raw: dict) -> str:
    if raw.get("code") not in (None, 0):
        return str(raw.get("message") or raw.get("error") or f"code={raw.get('code')}")
    data = raw.get("data")
    if not isinstance(data, dict):
        return ""
    if int(data.get("failed") or 0) > 0:
        for key in ("errors", "items"):
            seq = data.get(key)
            if isinstance(seq, list):
                for item in seq:
                    if isinstance(item, dict) and item.get("message"):
                        return str(item["message"])
                    if item:
                        return str(item)
        return f"failed={data.get('failed')}"
    for item in data.get("items") or []:
        if isinstance(item, dict) and item.get("action") == "failed":
            return str(item.get("message") or "item failed")
    return ""


def _sub2api_external_id(raw: dict) -> str:
    direct = raw.get("id") or raw.get("account_id")
    if direct:
        return str(direct)
    data = raw.get("data")
    if isinstance(data, dict):
        for item in data.get("items") or []:
            if isinstance(item, dict):
                value = item.get("id") or item.get("account_id")
                if value:
                    return str(value)
    return ""
