from __future__ import annotations

import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
GatewayResolver = Callable[[str, int], list[str]]


class StaticProxyPoolError(RuntimeError):
    pass


@dataclass(frozen=True)
class StaticProxyEndpoint:
    endpoint_id: str
    proxy_url: str
    gateway_host: str = ""
    gateway_ip: str = ""
    gateway_ips: tuple[str, ...] = ()


@dataclass(frozen=True)
class StaticProxyAssignment:
    slot: int
    endpoint_id: str
    proxy_url: str
    gateway_host: str = ""
    gateway_ip: str = ""
    gateway_ips: tuple[str, ...] = ()
    fallback_endpoints: tuple[StaticProxyEndpoint, ...] = ()


class StaticBackboneProxyPool:
    def __init__(
        self,
        *,
        gateway_host: str,
        gateway_port: int,
        username: str,
        password: str,
        country_code: str,
        gateway_resolver: GatewayResolver | None = None,
        fallback_endpoints_per_slot: int = 2,
    ) -> None:
        self._gateway_host = str(gateway_host or "").strip()
        self._gateway_port = int(gateway_port)
        self._username = str(username or "").strip()
        self._password = str(password or "")
        self._country_code = _normalize_country_code(country_code)
        self._gateway_resolver = gateway_resolver or _resolve_gateway_ipv4_addresses
        self._fallback_endpoints_per_slot = max(0, int(fallback_endpoints_per_slot))

    @property
    def configured(self) -> bool:
        return bool(
            self._gateway_host
            and 1 <= self._gateway_port <= 65535
            and self._username
            and self._password
        )

    def allocate(self, required_count: int) -> list[StaticProxyAssignment]:
        count = int(required_count)
        if count <= 0:
            return []
        self._validate_credentials()

        candidate_count = count * (1 + self._fallback_endpoints_per_slot)
        try:
            gateway_ips = list(
                dict.fromkeys(self._gateway_resolver(self._gateway_host, self._gateway_port))
            )
        except Exception as exc:
            raise StaticProxyPoolError(
                f"Webshare Backbone gateway DNS failed: {type(exc).__name__}"
            ) from exc
        if not gateway_ips:
            raise StaticProxyPoolError("Webshare Backbone gateway DNS returned no IPv4 address")

        endpoints: list[StaticProxyEndpoint] = []
        for endpoint_number in range(1, candidate_count + 1):
            gateway_ip = gateway_ips[(endpoint_number - 1) % len(gateway_ips)]
            endpoint_username = backbone_username_for_country(
                f"{self._username}-{endpoint_number}",
                self._country_code,
            )
            endpoints.append(
                StaticProxyEndpoint(
                    endpoint_id=f"backbone-{endpoint_number}",
                    proxy_url=_direct_proxy_url(
                        username=endpoint_username,
                        password=self._password,
                        proxy_host=gateway_ip,
                        proxy_port=self._gateway_port,
                    ),
                    gateway_host=self._gateway_host,
                    gateway_ip=gateway_ip,
                    gateway_ips=tuple(gateway_ips),
                )
            )

        assignments: list[StaticProxyAssignment] = []
        for index, endpoint in enumerate(endpoints[:count], start=1):
            fallback_endpoints = tuple(
                endpoints[fallback_index]
                for fallback_index in (
                    count * fallback_round + (index - 1)
                    for fallback_round in range(
                        1,
                        self._fallback_endpoints_per_slot + 1,
                    )
                )
                if fallback_index < len(endpoints)
            )
            assignments.append(
                StaticProxyAssignment(
                    slot=index,
                    endpoint_id=endpoint.endpoint_id,
                    proxy_url=endpoint.proxy_url,
                    gateway_host=endpoint.gateway_host,
                    gateway_ip=endpoint.gateway_ip,
                    gateway_ips=endpoint.gateway_ips,
                    fallback_endpoints=fallback_endpoints,
                )
            )
        return assignments

    def _validate_credentials(self) -> None:
        missing: list[str] = []
        if not self._gateway_host:
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_HOST")
        if not 1 <= self._gateway_port <= 65535:
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_PORT")
        if not self._username:
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_USERNAME")
        if not self._password:
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_PASSWORD")
        if missing:
            raise StaticProxyPoolError(
                "Webshare Backbone credentials are incomplete: " + ", ".join(missing)
            )


def backbone_username_for_country(username: str, country_code: str) -> str:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise StaticProxyPoolError("Webshare Backbone endpoint has no username")
    country = _normalize_country_code(country_code)
    parts = normalized_username.split("-")

    # Webshare's country-filtered Backbone format is username-COUNTRY-endpoint.
    if parts[-1].isdigit() or parts[-1].lower() == "rotate":
        if len(parts) >= 2 and _is_country_code(parts[-2]):
            parts[-2] = country
        else:
            parts.insert(-1, country)
        return "-".join(parts)

    if _is_country_code(parts[-1]):
        parts[-1] = country
    else:
        parts.append(country)
    return "-".join(parts)


def _direct_proxy_url(
    *,
    username: str,
    password: str,
    proxy_host: str,
    proxy_port: int,
) -> str:
    host = str(proxy_host or "").strip()
    if not host or not password:
        raise StaticProxyPoolError("Webshare Backbone endpoint credentials are incomplete")
    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{int(proxy_port)}"


def _normalize_country_code(country_code: str) -> str:
    normalized = str(country_code or "").strip().upper()
    if not _COUNTRY_CODE_PATTERN.fullmatch(normalized):
        raise StaticProxyPoolError("static proxy country must be a two-letter country code")
    return normalized


def _is_country_code(value: str) -> bool:
    return bool(_COUNTRY_CODE_PATTERN.fullmatch(str(value or "").upper()))


def _resolve_gateway_ipv4_addresses(host: str, port: int) -> list[str]:
    return sorted(
        {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if item[0] == socket.AF_INET
        }
    )
