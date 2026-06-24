from __future__ import annotations

from dataclasses import dataclass

import httpx

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult
from refactor_app.plugins.downstream_common import codex_credentials_body
from refactor_app.plugins.downstream_cpa.client import build_cpa_auth_file


class CustomHttpClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class CustomHttpClientConfig:
    url: str
    auth_header_name: str
    auth_header_value: str
    payload_type: str
    timeout_s: float = 30.0
    sub2api_concurrency: int = 0
    sub2api_group_ids: tuple[int, ...] = ()

    def validate(self) -> None:
        if not self.url:
            raise CustomHttpClientError("custom http url is required")
        if self.payload_type not in {"sub2api", "sub2api_admin_accounts", "cpa"}:
            raise CustomHttpClientError("custom http payload_type must be sub2api, sub2api_admin_accounts or cpa")
        if bool(self.auth_header_name) != bool(self.auth_header_value):
            raise CustomHttpClientError("custom http auth header name/value must be both set or both empty")
        if self.timeout_s <= 0:
            raise CustomHttpClientError("custom http timeout_s must be positive")


class CustomHttpClient:
    def __init__(
        self,
        config: CustomHttpClientConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._client = http_client or httpx.Client(timeout=config.timeout_s)

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        body = build_custom_http_payload(
            payload,
            payload_type=self._config.payload_type,
            sub2api_concurrency=self._config.sub2api_concurrency,
            sub2api_group_ids=self._config.sub2api_group_ids,
        )
        headers = {"Content-Type": "application/json"}
        if self._config.auth_header_name:
            headers[self._config.auth_header_name] = self._config.auth_header_value
        response = self._client.post(self._config.url, json=body, headers=headers)
        raw = _safe_json(response)
        if response.is_error:
            return DownstreamPushResult(
                pushed=False,
                error_code=f"http_{response.status_code}",
                error_message=str(raw.get("message") or raw.get("error") or raw.get("body") or ""),
                raw=raw,
            )
        return DownstreamPushResult(
            pushed=True,
            downstream_external_id=_custom_http_external_id(raw),
            raw=raw,
        )


def build_custom_http_payload(
    payload: DownstreamCodexPayload,
    *,
    payload_type: str,
    sub2api_concurrency: int = 0,
    sub2api_group_ids: tuple[int, ...] = (),
) -> dict:
    if payload_type == "sub2api":
        return codex_credentials_body(payload)
    if payload_type == "sub2api_admin_accounts":
        credentials = codex_credentials_body(payload)
        plan = payload.plan_type or payload.plan_tag or "team"
        body = {
            "name": f"codex-{payload.email}-{plan}",
            "platform": "openai",
            "type": "oauth",
            "credentials": credentials,
            "expires_at": credentials.get("expires_at"),
        }
        if sub2api_concurrency > 0:
            body["concurrency"] = int(sub2api_concurrency)
        if sub2api_group_ids:
            body["group_ids"] = [int(group_id) for group_id in sub2api_group_ids]
        return body
    if payload_type == "cpa":
        _, body = build_cpa_auth_file(payload)
        return body
    raise CustomHttpClientError("custom http payload_type must be sub2api, sub2api_admin_accounts or cpa")


def _custom_http_external_id(raw: dict) -> str:
    data = raw.get("data")
    if isinstance(data, dict):
        value = data.get("id") or data.get("account_id")
        if value:
            return str(value)
    return str(raw.get("id") or raw.get("account_id") or raw.get("body") or "")


def _safe_json(response: httpx.Response) -> dict:
    if not response.text:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {"body": response.text}
    return payload if isinstance(payload, dict) else {"body": payload}
