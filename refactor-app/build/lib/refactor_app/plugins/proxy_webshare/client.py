from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import httpx

from refactor_app.plugins.contracts import ProxyNode

WEB_SHARE_PROVIDER = "webshare"
DEFAULT_BASE_URL = "https://proxy.webshare.io"


class WebshareClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebshareClientConfig:
    api_token: str
    base_url: str = DEFAULT_BASE_URL
    download_url: str = ""
    proxy_type: str = "proxyserver"
    page_size: int = 100
    timeout_s: float = 30.0

    def validate(self) -> None:
        if not self.api_token and not self.download_url:
            raise WebshareClientError("webshare api_token or download_url is required")
        if self.page_size <= 0:
            raise WebshareClientError("webshare page_size must be positive")


class WebshareClient:
    def __init__(
        self,
        config: WebshareClientConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self._config = config
        headers = {"Authorization": f"Token {config.api_token}"} if config.api_token else {}
        self._client = http_client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_s,
            headers=headers,
        )

    def list_proxy_nodes(self) -> list[ProxyNode]:
        if self._config.download_url:
            return self._download_proxy_nodes()
        if not self._config.api_token:
            raise WebshareClientError("webshare api_token is required for proxy list api")

        proxies: list[ProxyNode] = []
        path_or_url = "/api/v2/proxy/list/"
        params: dict[str, Any] | None = {
            "mode": "direct",
            "page": 1,
            "page_size": self._config.page_size,
        }

        while path_or_url:
            response = self._client.get(path_or_url, params=params)
            if response.status_code == 429:
                raise WebshareClientError("webshare rate limited: retry after at least 60 seconds")
            if response.is_error:
                raise WebshareClientError(
                    f"webshare list proxies failed: http_status={response.status_code}"
                )

            payload = response.json()
            results = payload.get("results")
            if not isinstance(results, list):
                raise WebshareClientError("webshare list proxies response missing results list")

            proxies.extend(parse_proxy_node(item) for item in results)
            path_or_url = payload.get("next") or ""
            params = None

        return proxies

    def _download_proxy_nodes(self) -> list[ProxyNode]:
        response = self._client.get(self._config.download_url)
        if response.status_code == 429:
            raise WebshareClientError("webshare download rate limited")
        if response.is_error:
            raise WebshareClientError(
                f"webshare download proxies failed: http_status={response.status_code}"
            )
        return parse_download_proxy_text(response.text, proxy_type=self._config.proxy_type)


def parse_proxy_node(item: dict[str, Any]) -> ProxyNode:
    external_proxy_id = _required_str(item, "id")
    proxy_host = _required_str(item, "proxy_address")
    proxy_port = _required_int(item, "port")

    return ProxyNode(
        provider=WEB_SHARE_PROVIDER,
        external_proxy_id=external_proxy_id,
        connection_mode="direct",
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_scheme="http",
        proxy_type=str(item.get("proxy_type") or "proxyserver"),
        proxy_username=str(item.get("username") or ""),
        proxy_password=str(item.get("password") or ""),
        country_code=str(item.get("country_code") or ""),
        city_name=str(item.get("city_name") or ""),
        asn_name=str(item.get("asn_name") or ""),
        provider_valid=bool(item.get("valid", False)),
        last_provider_verification_at=_parse_datetime(item.get("last_verification")),
    )


def parse_download_proxy_text(text: str, *, proxy_type: str = "proxyserver") -> list[ProxyNode]:
    proxies: list[ProxyNode] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        proxies.append(parse_download_proxy_line(line, line_number=line_number, proxy_type=proxy_type))
    return proxies


def parse_download_proxy_line(
    line: str,
    *,
    line_number: int,
    proxy_type: str = "proxyserver",
) -> ProxyNode:
    parts = line.split(":")
    if len(parts) != 4:
        raise WebshareClientError(
            f"webshare download line must be host:port:username:password at line {line_number}"
        )

    host, port_text, username, password = (part.strip() for part in parts)
    item = {
        "proxy_address": host,
        "port": port_text,
    }
    proxy_host = _required_str(item, "proxy_address")
    proxy_port = _required_int(item, "port")
    external_proxy_id = _download_external_proxy_id(proxy_host, proxy_port, username)

    return ProxyNode(
        provider=WEB_SHARE_PROVIDER,
        external_proxy_id=external_proxy_id,
        connection_mode="direct",
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_scheme="http",
        proxy_type=proxy_type,
        proxy_username=username,
        proxy_password=password,
        provider_valid=True,
        last_provider_verification_at=datetime.now(UTC),
    )


def _download_external_proxy_id(proxy_host: str, proxy_port: int, username: str) -> str:
    fingerprint = sha256(f"{proxy_host}:{proxy_port}:{username}".encode()).hexdigest()[:16]
    return f"download-{proxy_host}-{proxy_port}-{fingerprint}"


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if value is None or value == "":
        raise WebshareClientError(f"webshare proxy missing required field: {key}")
    return str(value)


def _required_int(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WebshareClientError(f"webshare proxy field must be int: {key}") from exc
    if parsed <= 0 or parsed > 65535:
        raise WebshareClientError(f"webshare proxy port out of range: {parsed}")
    return parsed


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise WebshareClientError("webshare last_verification must be string")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
