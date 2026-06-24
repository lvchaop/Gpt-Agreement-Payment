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

    def validate(self) -> None:
        if not self.url:
            raise CustomHttpClientError("custom http url is required")
        if self.payload_type not in {"sub2api", "cpa"}:
            raise CustomHttpClientError("custom http payload_type must be sub2api or cpa")
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
        body = build_custom_http_payload(payload, payload_type=self._config.payload_type)
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
            downstream_external_id=str(raw.get("id") or raw.get("account_id") or raw.get("body") or ""),
            raw=raw,
        )


def build_custom_http_payload(payload: DownstreamCodexPayload, *, payload_type: str) -> dict:
    if payload_type == "sub2api":
        return codex_credentials_body(payload)
    if payload_type == "cpa":
        _, body = build_cpa_auth_file(payload)
        return body
    raise CustomHttpClientError("custom http payload_type must be sub2api or cpa")


def _safe_json(response: httpx.Response) -> dict:
    if not response.text:
        return {}
    try:
        payload = response.json()
    except ValueError:
        return {"body": response.text}
    return payload if isinstance(payload, dict) else {"body": payload}
