from __future__ import annotations

import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import ProxyInventoryModel

WEBSHARE_BACKBONE_HOST = "p.webshare.io"
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
GatewayResolver = Callable[[str, int], list[str]]


class RegistrationProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegistrationBackboneProxy:
    proxy_url: str = field(repr=False)
    endpoint_id: str
    endpoint_number: int
    endpoint_count: int
    country_code: str


def resolve_registration_backbone_proxy(
    session_factory: Callable[[], Session],
    *,
    email: str,
    country_code: str = "US",
) -> RegistrationBackboneProxy:
    normalized_email = normalize_registration_proxy_email(email)
    normalized_country = normalize_registration_proxy_country(country_code)

    with session_factory() as session:
        # Mutable health flags are intentionally excluded so a status refresh cannot remap an email.
        row = session.execute(
            select(
                ProxyInventoryModel.proxy_scheme,
                ProxyInventoryModel.proxy_host,
                ProxyInventoryModel.proxy_port,
                ProxyInventoryModel.proxy_username,
                ProxyInventoryModel.proxy_password,
                func.count(ProxyInventoryModel.id).over().label("endpoint_count"),
            )
            .where(
                ProxyInventoryModel.provider == "webshare",
                ProxyInventoryModel.proxy_type == "static_proxy",
                func.lower(ProxyInventoryModel.proxy_host) == WEBSHARE_BACKBONE_HOST,
                ProxyInventoryModel.proxy_username != "",
                ProxyInventoryModel.proxy_password != "",
            )
            .order_by(ProxyInventoryModel.id.asc())
            .limit(1)
        ).first()

    if row is None:
        raise RegistrationProxyError("Webshare Backbone static proxy inventory is empty")

    return build_registration_backbone_proxy(
        email=normalized_email,
        country_code=normalized_country,
        endpoint_count=int(row.endpoint_count or 0),
        source_scheme=str(row.proxy_scheme or "http"),
        source_host=str(row.proxy_host or ""),
        source_port=int(row.proxy_port or 0),
        source_username=str(row.proxy_username or ""),
        source_password=str(row.proxy_password or ""),
    )


def build_registration_backbone_proxy(
    *,
    email: str,
    country_code: str,
    endpoint_count: int,
    source_scheme: str,
    source_host: str,
    source_port: int,
    source_username: str,
    source_password: str,
    gateway_resolver: GatewayResolver | None = None,
) -> RegistrationBackboneProxy:
    normalized_email = normalize_registration_proxy_email(email)
    normalized_country = normalize_registration_proxy_country(country_code)
    count = int(endpoint_count)
    if count < 1:
        raise RegistrationProxyError("Webshare Backbone endpoint inventory is empty")

    host = str(source_host or "").strip().lower()
    port = int(source_port)
    scheme = str(source_scheme or "http").strip().lower() or "http"
    if host != WEBSHARE_BACKBONE_HOST or not 1 <= port <= 65535:
        raise RegistrationProxyError("Webshare Backbone gateway is invalid")
    if not source_password:
        raise RegistrationProxyError("Webshare Backbone password is missing")

    # Camoufox receives the resolved IPv4, matching invite-executor's working
    # proxy path. The username still selects the stable Backbone endpoint.
    resolver = gateway_resolver or _resolve_gateway_ipv4_addresses
    try:
        gateway_ips = list(dict.fromkeys(resolver(host, port)))
    except Exception as exc:
        raise RegistrationProxyError(
            f"Webshare Backbone gateway DNS failed: {type(exc).__name__}"
        ) from exc
    if not gateway_ips:
        raise RegistrationProxyError("Webshare Backbone gateway DNS returned no IPv4 address")

    endpoint_number = registration_backbone_endpoint_number(normalized_email, count)
    source_base, separator, source_endpoint = str(source_username or "").strip().rpartition("-")
    if not separator or not source_base or not source_endpoint.isdigit():
        raise RegistrationProxyError("Webshare Backbone username has no numeric endpoint")
    endpoint_username = backbone_username_for_country(
        f"{source_base}-{endpoint_number}",
        normalized_country,
    )
    gateway_ip = gateway_ips[(endpoint_number - 1) % len(gateway_ips)]
    proxy_url = (
        f"{scheme}://{quote(endpoint_username, safe='')}:{quote(source_password, safe='')}"
        f"@{gateway_ip}:{port}"
    )
    return RegistrationBackboneProxy(
        proxy_url=proxy_url,
        endpoint_id=f"backbone-{endpoint_number}",
        endpoint_number=endpoint_number,
        endpoint_count=count,
        country_code=normalized_country,
    )


def registration_backbone_endpoint_number(email: str, endpoint_count: int) -> int:
    normalized_email = normalize_registration_proxy_email(email)
    count = int(endpoint_count)
    if count < 1:
        raise RegistrationProxyError("Webshare Backbone endpoint count must be positive")
    digest = sha256(normalized_email.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % count + 1


def backbone_username_for_country(username: str, country_code: str) -> str:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise RegistrationProxyError("Webshare Backbone username is missing")
    country = normalize_registration_proxy_country(country_code)
    parts = normalized_username.split("-")
    if parts[-1].isdigit() or parts[-1].lower() == "rotate":
        if len(parts) >= 2 and _COUNTRY_CODE_PATTERN.fullmatch(parts[-2].upper()):
            parts[-2] = country
        else:
            parts.insert(-1, country)
        return "-".join(parts)
    if _COUNTRY_CODE_PATTERN.fullmatch(parts[-1].upper()):
        parts[-1] = country
    else:
        parts.append(country)
    return "-".join(parts)


def normalize_registration_proxy_email(email: str) -> str:
    normalized = str(email or "").strip().casefold()
    if not normalized or "@" not in normalized:
        raise RegistrationProxyError("registration target email is required for proxy hashing")
    return normalized


def normalize_registration_proxy_country(country_code: str) -> str:
    normalized = str(country_code or "US").strip().upper()
    if not _COUNTRY_CODE_PATTERN.fullmatch(normalized):
        raise RegistrationProxyError("registration proxy country must be a two-letter country code")
    return normalized


def _resolve_gateway_ipv4_addresses(host: str, port: int) -> list[str]:
    return sorted(
        {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if item[0] == socket.AF_INET
        }
    )
