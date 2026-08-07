#!/usr/bin/env python3
"""Temporary Claude Max SEPA browser workflow.

The mailbox service is read-only in this workflow: it is queried by email for a
fresh Claude magic link. No mailbox allocation or lifecycle endpoint is used.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote, unquote, urlsplit

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / "refactor-app" / ".env"
DEFAULT_EXTENSION = Path(
    "/Users/chaopenglv/Downloads/claude-sepa-helper-v1.0.8-protected"
)
MAGIC_LINK_REGEX = (
    r"(https://claude\.ai/[Mm][Aa][Gg][Ii][Cc]-[Ll][Ii][Nn][Kk]"
    r"#[A-Za-z0-9._~%-]+)"
)
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
BIRTH_AGE_MIN = 25
BIRTH_AGE_MAX = 38
MAX_UPGRADE_URL = "https://claude.ai/upgrade/max?from=onboarding"
BACKBONE_USERNAME_REGEX = re.compile(
    r"^(?P<base>.+?)(?:-[A-Z]{2})?-(?P<endpoint>[0-9]+)$",
    re.I,
)


class ClaudeSepaError(RuntimeError):
    pass


class MailLookupError(ClaudeSepaError):
    pass


class BrowserFlowError(ClaudeSepaError):
    pass


class AccountTerminalError(BrowserFlowError):
    pass


class PaymentAttemptError(BrowserFlowError):
    pass


class ProxyPoolError(ClaudeSepaError):
    pass


@dataclass(frozen=True)
class BillingProfile:
    full_name: str
    country: str
    line1: str
    line2: str
    postal_code: str
    city: str
    state: str = ""


@dataclass(frozen=True)
class BackboneProxyConfig:
    country: str
    database_url: str
    gateway_host: str = "p.webshare.io"
    gateway_port: int = 80
    username: str = ""
    password: str = ""
    ip_check_url: str = "https://ipv4.webshare.io/"
    geo_check_url: str = "https://ipinfo.io/json"
    verify_timeout_s: float = 15.0
    scan_concurrency: int = 12
    max_endpoint: int = 20_000


@dataclass(frozen=True)
class BackboneProxyCandidate:
    endpoint: int
    proxy_url: str


@dataclass(frozen=True)
class BackboneProxyAssignment:
    endpoint: int
    proxy_url: str
    exit_ip: str
    country: str

    @property
    def endpoint_id(self) -> str:
        return hashlib.sha256(f"webshare-backbone:{self.endpoint}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class UpgradeConfig:
    emails_file: Path
    ibans_file: Path
    billing: BillingProfile
    extension_path: Path
    output_dir: Path
    mail_base_url: str
    mail_api_key: str
    proxy: BackboneProxyConfig
    addresses_file: Path | None = None
    names_file: Path | None = None
    browser_executable: Path | None = None
    browser_concurrency: int = 3
    step_delay_ms: int = 2_000
    page_settle_ms: int = 10_000
    mail_timeout_s: float = 30.0
    mail_poll_interval_s: float = 3.0
    magic_link_timeout_s: int = 180
    navigation_timeout_ms: int = 60_000
    success_timeout_s: int = 120
    headless: bool = False
    submit_payment: bool = True


@dataclass(frozen=True)
class AccountInput:
    email: str
    iban: str
    index: int
    billing: BillingProfile


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _resolve_browser_executable(value: object, *, base_dir: Path) -> Path | None:
    configured = str(value or os.environ.get("PPS_CHROMIUM_EXECUTABLE") or "").strip()
    if configured:
        return _resolve_path(configured, base_dir=base_dir)
    return None


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ClaudeSepaError(f"config field is required: {key}")
    return value


def load_config(path: Path) -> UpgradeConfig:
    _load_env_file(DEFAULT_ENV_FILE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ClaudeSepaError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ClaudeSepaError(f"config is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaudeSepaError("config root must be a JSON object")

    base_dir = path.resolve().parent
    addresses_value = str(payload.get("addresses_file") or "").strip()
    addresses_file = (
        _resolve_path(addresses_value, base_dir=base_dir) if addresses_value else None
    )
    names_value = str(payload.get("names_file") or "").strip()
    names_file = _resolve_path(names_value, base_dir=base_dir) if names_value else None
    billing_raw = payload.get("billing")
    if not isinstance(billing_raw, dict):
        raise ClaudeSepaError("config field billing must be an object")
    billing = BillingProfile(
        full_name=(
            str(billing_raw.get("full_name") or "").strip()
            if names_file is not None
            else _require_text(billing_raw, "full_name")
        ),
        country=_require_text(billing_raw, "country").upper(),
        line1=(
            str(billing_raw.get("line1") or "").strip()
            if addresses_file is not None
            else _require_text(billing_raw, "line1")
        ),
        line2=str(billing_raw.get("line2") or "").strip(),
        postal_code=(
            str(billing_raw.get("postal_code") or "").strip()
            if addresses_file is not None
            else _require_text(billing_raw, "postal_code")
        ),
        city=(
            str(billing_raw.get("city") or "").strip()
            if addresses_file is not None
            else _require_text(billing_raw, "city")
        ),
        state=str(billing_raw.get("state") or "").strip(),
    )
    if billing.country != "DE":
        raise ClaudeSepaError(
            f"this temporary workflow requires a German billing address: {billing.country}"
        )

    mail_raw = payload.get("mail") if isinstance(payload.get("mail"), dict) else {}
    base_url = str(
        mail_raw.get("base_url")
        or os.environ.get("REFACTOR_APP_EXTERNAL_MAIL_API_BASE_URL")
        or ""
    ).strip()
    api_key = str(
        mail_raw.get("api_key")
        or os.environ.get("REFACTOR_APP_EXTERNAL_MAIL_API_KEY")
        or ""
    ).strip()
    if not base_url:
        raise ClaudeSepaError("mail base URL is missing")
    if not api_key:
        raise ClaudeSepaError("mail API key is missing")

    proxy_raw = payload.get("proxy")
    if not isinstance(proxy_raw, dict):
        raise ClaudeSepaError("config field proxy must be an object")
    proxy = BackboneProxyConfig(
        country=str(proxy_raw.get("country") or "DE").strip().upper(),
        database_url=str(
            proxy_raw.get("database_url")
            or os.environ.get("REFACTOR_APP_DATABASE_URL")
            or ""
        ).strip(),
        gateway_host=str(proxy_raw.get("gateway_host") or "p.webshare.io").strip(),
        gateway_port=int(proxy_raw.get("gateway_port") or 80),
        username=str(
            proxy_raw.get("username")
            or os.environ.get("CLAUDE_SEPA_WEBSHARE_USERNAME")
            or ""
        ).strip(),
        password=str(
            proxy_raw.get("password")
            or os.environ.get("CLAUDE_SEPA_WEBSHARE_PASSWORD")
            or ""
        ),
        ip_check_url=str(
            proxy_raw.get("ip_check_url") or "https://ipv4.webshare.io/"
        ).strip(),
        geo_check_url=str(
            proxy_raw.get("geo_check_url") or "https://ipinfo.io/json"
        ).strip(),
        verify_timeout_s=float(proxy_raw.get("verify_timeout_s") or 15),
        scan_concurrency=int(proxy_raw.get("scan_concurrency") or 12),
        max_endpoint=int(proxy_raw.get("max_endpoint") or 20_000),
    )

    config = UpgradeConfig(
        emails_file=_resolve_path(_require_text(payload, "emails_file"), base_dir=base_dir),
        ibans_file=_resolve_path(_require_text(payload, "ibans_file"), base_dir=base_dir),
        billing=billing,
        extension_path=_resolve_path(
            str(payload.get("extension_path") or DEFAULT_EXTENSION), base_dir=base_dir
        ),
        output_dir=_resolve_path(
            str(payload.get("output_dir") or ROOT / "output" / "claude-sepa"),
            base_dir=base_dir,
        ),
        mail_base_url=base_url.rstrip("/"),
        mail_api_key=api_key,
        proxy=proxy,
        addresses_file=addresses_file,
        names_file=names_file,
        browser_executable=_resolve_browser_executable(
            payload.get("browser_executable"), base_dir=base_dir
        ),
        browser_concurrency=int(payload.get("browser_concurrency") or 3),
        step_delay_ms=int(payload.get("step_delay_ms") or 2_000),
        page_settle_ms=int(payload.get("page_settle_ms") or 10_000),
        mail_timeout_s=float(mail_raw.get("request_timeout_s") or 30),
        mail_poll_interval_s=float(mail_raw.get("poll_interval_s") or 3),
        magic_link_timeout_s=int(payload.get("magic_link_timeout_s") or 180),
        navigation_timeout_ms=int(payload.get("navigation_timeout_ms") or 60_000),
        success_timeout_s=int(payload.get("success_timeout_s") or 120),
        headless=bool(payload.get("headless", False)),
        submit_payment=bool(payload.get("submit_payment", True)),
    )
    validate_config(config)
    return config


def validate_config(config: UpgradeConfig) -> None:
    if not config.emails_file.is_file():
        raise ClaudeSepaError(f"emails file not found: {config.emails_file}")
    if not config.ibans_file.is_file():
        raise ClaudeSepaError(f"IBAN file not found: {config.ibans_file}")
    if config.addresses_file is not None and not config.addresses_file.is_file():
        raise ClaudeSepaError(f"addresses file not found: {config.addresses_file}")
    if config.names_file is not None and not config.names_file.is_file():
        raise ClaudeSepaError(f"names file not found: {config.names_file}")
    if not (config.extension_path / "manifest.json").is_file():
        raise ClaudeSepaError(f"Chrome extension manifest not found: {config.extension_path}")
    if config.magic_link_timeout_s <= 0 or config.success_timeout_s <= 0:
        raise ClaudeSepaError("timeouts must be positive")
    if config.browser_concurrency <= 0:
        raise ClaudeSepaError("browser_concurrency must be positive")
    if config.step_delay_ms < 0 or config.page_settle_ms < 0:
        raise ClaudeSepaError("browser delays cannot be negative")
    if config.browser_executable is not None and not config.browser_executable.is_file():
        raise ClaudeSepaError(
            f"Chromium executable not found: {config.browser_executable}"
        )
    if config.proxy.country != "DE":
        raise ClaudeSepaError(
            f"this temporary workflow requires German proxy country DE: {config.proxy.country}"
        )
    if not config.proxy.gateway_host or not 1 <= config.proxy.gateway_port <= 65535:
        raise ClaudeSepaError("invalid Webshare Backbone gateway")
    if (
        config.proxy.verify_timeout_s <= 0
        or config.proxy.scan_concurrency <= 0
        or config.proxy.max_endpoint <= 0
    ):
        raise ClaudeSepaError("proxy verification settings must be positive")
    if bool(config.proxy.username) != bool(config.proxy.password):
        raise ClaudeSepaError("proxy username and password must be configured together")
    if not config.proxy.username and not config.proxy.database_url:
        raise ClaudeSepaError(
            "proxy credentials are missing: configure database_url or username/password"
        )


def _data_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def load_emails(path: Path) -> list[str]:
    emails = _data_lines(path)
    invalid = [email for email in emails if EMAIL_REGEX.fullmatch(email) is None]
    if invalid:
        raise ClaudeSepaError(f"invalid email in {path}: {invalid[0]!r}")
    normalized = [email.lower() for email in emails]
    if len(set(normalized)) != len(normalized):
        raise ClaudeSepaError(f"duplicate email found in {path}")
    return emails


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def iban_is_valid(value: str) -> bool:
    iban = normalize_iban(value)
    if not re.fullmatch(r"DE[0-9]{20}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    remainder = 0
    for char in numeric:
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def load_ibans(path: Path) -> list[str]:
    ibans = [normalize_iban(value) for value in _data_lines(path)]
    invalid = [iban for iban in ibans if not iban_is_valid(iban)]
    if invalid:
        redacted = f"{invalid[0][:4]}...{invalid[0][-4:]}"
        raise ClaudeSepaError(f"invalid German IBAN in {path}: {redacted}")
    return list(dict.fromkeys(ibans))


def iban_retry_candidates(
    path: Path,
    preferred: str,
    *,
    shuffle: Callable[[list[str]], None] | None = None,
) -> list[str]:
    preferred = normalize_iban(preferred)
    remaining = [iban for iban in load_ibans(path) if iban != preferred]
    (shuffle or secrets.SystemRandom().shuffle)(remaining)
    return [preferred, *remaining]


def load_german_addresses(path: Path, *, full_name: str) -> list[BillingProfile]:
    profiles: list[BillingProfile] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream), start=1):
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) < 3:
                raise ClaudeSepaError(
                    f"German address must have at least 3 CSV fields at {path}:{line_number}"
                )
            line1 = ", ".join(value.strip() for value in row[:-2])
            postal_city = row[-2].strip()
            country_name = row[-1].strip()
            match = re.fullmatch(r"(?P<postal>[0-9]{5})\s+(?P<city>.+)", postal_city)
            if not line1 or match is None:
                raise ClaudeSepaError(f"invalid German address at {path}:{line_number}")
            if country_name.casefold() not in {"de", "deutschland", "germany"}:
                raise ClaudeSepaError(
                    f"address country is not Germany at {path}:{line_number}"
                )
            profiles.append(
                BillingProfile(
                    full_name=full_name,
                    country="DE",
                    line1=line1,
                    line2="",
                    postal_code=match.group("postal"),
                    city=match.group("city"),
                )
            )
    if not profiles:
        raise ClaudeSepaError(f"German address file is empty: {path}")
    return profiles


def load_names(path: Path) -> list[str]:
    names = _data_lines(path)
    invalid = [name for name in names if len(name) > 120 or len(name.split()) < 2]
    if invalid:
        raise ClaudeSepaError(f"invalid full name in {path}: {invalid[0]!r}")
    unique_names = list(dict.fromkeys(names))
    if not unique_names:
        raise ClaudeSepaError(f"name file is empty: {path}")
    return unique_names


def load_account_inputs(
    config: UpgradeConfig,
    *,
    randbelow: Callable[[int], int] = secrets.randbelow,
) -> list[AccountInput]:
    emails = load_emails(config.emails_file)
    ibans = load_ibans(config.ibans_file)
    if not ibans:
        raise ClaudeSepaError(f"IBAN file is empty: {config.ibans_file}")
    billing_profiles = (
        load_german_addresses(
            config.addresses_file,
            full_name="",
        )
        if config.addresses_file is not None
        else [config.billing]
    )
    names = load_names(config.names_file) if config.names_file is not None else [config.billing.full_name]
    accounts: list[AccountInput] = []
    for index, email in enumerate(emails, start=1):
        billing = billing_profiles[randbelow(len(billing_profiles))]
        accounts.append(
            AccountInput(
                email=email,
                iban=ibans[randbelow(len(ibans))],
                index=index,
                billing=replace(billing, full_name=names[randbelow(len(names))]),
            )
        )
    return accounts


def _database_dsn(value: str) -> str:
    return str(value or "").replace("postgresql+psycopg://", "postgresql://", 1)


def _backbone_base_username(value: str) -> str:
    username = str(value or "").strip()
    if not username:
        raise ProxyPoolError("Webshare proxy username is empty")
    match = BACKBONE_USERNAME_REGEX.fullmatch(username)
    return match.group("base") if match else username


def _load_backbone_inventory(config: BackboneProxyConfig) -> tuple[str, str, list[int]]:
    if config.username and config.password:
        return (
            _backbone_base_username(config.username),
            config.password,
            list(range(1, config.max_endpoint + 1)),
        )
    try:
        import psycopg
    except ImportError as exc:
        raise ProxyPoolError(
            "psycopg is required to read Webshare credentials from proxy inventory"
        ) from exc

    try:
        with psycopg.connect(_database_dsn(config.database_url), connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT proxy_username, proxy_password
                    FROM proxy_inventory
                    WHERE proxy_type = 'static_proxy'
                      AND provider_valid IS TRUE
                      AND proxy_status = 'available'
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()
    except Exception as exc:
        raise ProxyPoolError(
            f"static proxy inventory query failed: {type(exc).__name__}"
        ) from exc
    if not rows:
        raise ProxyPoolError("static proxy inventory has no available endpoints")

    base_username = ""
    password = ""
    endpoints: list[int] = []
    seen_endpoints: set[int] = set()
    for raw_username, raw_password in rows:
        username = str(raw_username or "").strip()
        candidate_password = str(raw_password or "")
        match = BACKBONE_USERNAME_REGEX.fullmatch(username)
        if match is None or not candidate_password:
            continue
        candidate_base = match.group("base")
        endpoint = int(match.group("endpoint"))
        if not base_username:
            base_username = candidate_base
            password = candidate_password
        if candidate_base != base_username or candidate_password != password:
            raise ProxyPoolError("static proxy inventory contains mixed Webshare credentials")
        if endpoint <= config.max_endpoint and endpoint not in seen_endpoints:
            endpoints.append(endpoint)
            seen_endpoints.add(endpoint)
    if not base_username or not password or not endpoints:
        raise ProxyPoolError("static proxy inventory has no usable Backbone credentials")
    return base_username, password, endpoints


def _valid_ip(value: str) -> str:
    candidate = str(value or "").strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError as exc:
        raise ProxyPoolError("proxy verification returned an invalid IP address") from exc


def _probe_backbone_proxy(
    proxy_url: str,
    *,
    config: BackboneProxyConfig,
) -> tuple[str, str, str]:
    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=config.verify_timeout_s,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            ip_response = client.get(config.ip_check_url)
            ip_response.raise_for_status()
            first_ip = _valid_ip(ip_response.text)
            geo_response = client.get(config.geo_check_url)
            geo_response.raise_for_status()
            payload = geo_response.json()
    except Exception as exc:
        raise ProxyPoolError(f"proxy verification failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ProxyPoolError("proxy geo verification returned invalid JSON")
    second_ip = _valid_ip(str(payload.get("ip") or ""))
    country = str(payload.get("country") or "").strip().upper()
    return first_ip, second_ip, country


class WebshareBackboneProxyPool:
    def __init__(
        self,
        config: BackboneProxyConfig,
        *,
        inventory_loader: Callable[[], tuple[str, str, list[int]]] | None = None,
        probe: Callable[[str], tuple[str, str, str]] | None = None,
        shuffle: Callable[[list[int]], None] | None = None,
    ) -> None:
        self.config = config
        self._inventory_loader = inventory_loader or (
            lambda: _load_backbone_inventory(config)
        )
        self._probe = probe or (lambda proxy_url: _probe_backbone_proxy(proxy_url, config=config))
        self._shuffle = shuffle or secrets.SystemRandom().shuffle
        self._used_endpoints: set[int] = set()
        self._used_exit_ips: set[str] = set()

    def allocate(self, required_count: int) -> list[BackboneProxyAssignment]:
        count = int(required_count)
        if count <= 0:
            return []
        base_username, password, endpoints = self._inventory_loader()
        endpoints = [
            endpoint for endpoint in endpoints if endpoint not in self._used_endpoints
        ]
        self._shuffle(endpoints)
        candidates = [
            BackboneProxyCandidate(
                endpoint=endpoint,
                proxy_url=self._proxy_url(
                    base_username=base_username,
                    password=password,
                    endpoint=endpoint,
                ),
            )
            for endpoint in endpoints
        ]
        assignments: list[BackboneProxyAssignment] = []
        seen_exit_ips: set[str] = set(self._used_exit_ips)
        scanned = 0
        workers = min(self.config.scan_concurrency, len(candidates))
        batch_size = max(workers, workers * 2)
        for offset in range(0, len(candidates), batch_size):
            batch = candidates[offset : offset + batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self._verify_candidate, batch))
            scanned += len(batch)
            for assignment in results:
                if assignment is None or assignment.exit_ip in seen_exit_ips:
                    continue
                assignments.append(assignment)
                seen_exit_ips.add(assignment.exit_ip)
                if len(assignments) == count:
                    self._used_endpoints.update(item.endpoint for item in assignments)
                    self._used_exit_ips.update(item.exit_ip for item in assignments)
                    return assignments
        raise ProxyPoolError(
            f"insufficient verified DE Backbone exits: required={count} "
            f"verified={len(assignments)} scanned={scanned}"
        )

    def _proxy_url(self, *, base_username: str, password: str, endpoint: int) -> str:
        username = f"{base_username}-{self.config.country}-{endpoint}"
        return (
            f"http://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{self.config.gateway_host}:{self.config.gateway_port}"
        )

    def _verify_candidate(
        self,
        candidate: BackboneProxyCandidate,
    ) -> BackboneProxyAssignment | None:
        try:
            first_ip, second_ip, country = self._probe(candidate.proxy_url)
        except Exception:
            return None
        if first_ip != second_ip or country != self.config.country:
            return None
        return BackboneProxyAssignment(
            endpoint=candidate.endpoint,
            proxy_url=candidate.proxy_url,
            exit_ip=first_ip,
            country=country,
        )


def playwright_proxy(proxy_url: str) -> dict[str, str]:
    parsed = urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        raise ProxyPoolError(f"unsupported browser proxy scheme: {parsed.scheme}")
    if not parsed.hostname or parsed.port is None:
        raise ProxyPoolError("browser proxy URL is incomplete")
    scheme = "socks5" if parsed.scheme == "socks5h" else parsed.scheme
    result = {"server": f"{scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        result["username"] = unquote(parsed.username)
    if parsed.password:
        result["password"] = unquote(parsed.password)
    return result


def chromium_fingerprint_launch_options(
    *,
    config: UpgradeConfig,
    proxy_assignment: BackboneProxyAssignment,
    profile_dir: Path,
    extension_dir: Path,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": config.headless,
        "proxy": playwright_proxy(proxy_assignment.proxy_url),
        "ignore_default_args": ["--enable-automation"],
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-size=1440,1000",
            f"--disable-extensions-except={extension_dir}",
            f"--load-extension={extension_dir}",
        ],
        "locale": "en-DE",
        "timezone_id": "Europe/Berlin",
        "viewport": {"width": 1440, "height": 1000},
    }
    if config.browser_executable is not None:
        options["executable_path"] = str(config.browser_executable)
    return options


def camoufox_fingerprint_launch_options(
    *,
    config: UpgradeConfig,
    proxy_assignment: BackboneProxyAssignment,
    profile_dir: Path,
) -> dict[str, Any]:
    from browserforge.fingerprints import Screen

    return {
        "headless": config.headless,
        "humanize": True,
        "persistent_context": True,
        "user_data_dir": str(profile_dir),
        "os": "windows",
        "screen": Screen(max_width=1920, max_height=1080),
        "proxy": playwright_proxy(proxy_assignment.proxy_url),
        "geoip": proxy_assignment.exit_ip,
        "locale": "de-DE",
    }


def age_on_date(birth_date: date, *, today: date) -> int:
    before_birthday = (today.month, today.day) < (birth_date.month, birth_date.day)
    return today.year - birth_date.year - int(before_birthday)


def random_birth_date(
    *,
    today: date | None = None,
    min_age: int = BIRTH_AGE_MIN,
    max_age: int = BIRTH_AGE_MAX,
    randbelow: Callable[[int], int] = secrets.randbelow,
) -> str:
    if min_age < 0 or max_age < min_age:
        raise ValueError(f"invalid age range: {min_age}..{max_age}")
    reference = today or date.today()
    target_age = min_age + randbelow(max_age - min_age + 1)

    # An exact age spans parts of two birth years. Filtering this bounded
    # interval handles month/day boundaries and leap days without approximation.
    cursor = date(reference.year - target_age - 1, 1, 1)
    end = date(reference.year - target_age, 12, 31)
    candidates: list[date] = []
    while cursor <= end:
        if age_on_date(cursor, today=reference) == target_age:
            candidates.append(cursor)
        cursor += timedelta(days=1)
    if not candidates:
        raise RuntimeError(f"no birth date candidates for age {target_age}")
    selected = candidates[randbelow(len(candidates))]
    return selected.strftime("%m/%d/%Y")


def birth_date_parts(value: str) -> tuple[str, str, str]:
    parsed = datetime.strptime(value, "%m/%d/%Y")
    return str(parsed.day), str(parsed.month), str(parsed.year)


def validate_magic_link(value: str) -> str:
    link = str(value or "").strip()
    parsed = urlsplit(link)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "claude.ai"
        or parsed.path.lower() != "/magic-link"
        or not parsed.fragment
    ):
        raise MailLookupError("mail API returned an invalid Claude magic link")
    return link


def magic_link_from_payload(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    candidates: list[object] = []
    links = data.get("links")
    if isinstance(links, list):
        candidates.extend(links)
    candidates.extend(
        (
            data.get("verification_link"),
            data.get("verification_code"),
            data.get("code"),
            payload.get("verification_link"),
            payload.get("verification_code"),
        )
    )
    for value in candidates:
        try:
            return validate_magic_link(str(value or ""))
        except MailLookupError:
            continue
    return ""


def mail_received_timestamp(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class ReadOnlyMagicLinkClient:
    """Only issues GET requests to the external mailbox API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_s: float,
        poll_interval_s: float,
        client: httpx.Client | None = None,
        sleep_fn: Any = time.sleep,
        monotonic_fn: Any = time.monotonic,
        wall_time_fn: Any = time.time,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout_s,
            trust_env=False,
        )
        self._owns_client = client is None
        self._poll_interval_s = max(0.5, poll_interval_s)
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._wall_time = wall_time_fn

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def wait_for_magic_link(
        self,
        *,
        email: str,
        issued_after: float,
        timeout_s: int,
    ) -> str:
        deadline = self._monotonic() + max(1, timeout_s)
        last_error = ""
        while self._monotonic() < deadline:
            elapsed = max(0.0, self._wall_time() - issued_after)
            since_minutes = max(2, int(math.ceil(elapsed / 60.0)) + 1)
            try:
                response = self._client.get(
                    "/api/external/verification-code",
                    params={
                        "email": email,
                        "since_minutes": str(since_minutes),
                        "code_length": "20-500",
                        "code_regex": MAGIC_LINK_REGEX,
                        "code_source": "all",
                    },
                )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise MailLookupError("mail API response must be a JSON object")
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                candidate = magic_link_from_payload(payload)
                received_at = mail_received_timestamp(data.get("received_at"))
                fresh = received_at is None or received_at >= issued_after - 5
                if payload.get("success") is True and candidate and fresh:
                    return candidate
                code = str(
                    payload.get("code") or (payload.get("error") or {}).get("code") or ""
                ).strip()
                message = str(
                    payload.get("message") or (payload.get("error") or {}).get("message") or ""
                ).strip()
                last_error = f"{code}: {message}".strip(": ")
                if response.status_code >= 400 and code not in {
                    "MAIL_NOT_FOUND",
                    "VERIFICATION_CODE_NOT_FOUND",
                }:
                    raise MailLookupError(
                        f"mail API failed HTTP {response.status_code}: {last_error}"
                    )
            except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            self._sleep(min(self._poll_interval_s, remaining))
        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(f"Claude magic-link timeout email={email}{suffix}")


class JsonlRecorder:
    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.success_path = output_dir / "success.jsonl"
        self.failed_path = output_dir / "failed.jsonl"
        self.events_path = output_dir / "events.jsonl"
        self._write_lock = threading.Lock()

    def successful_emails(self) -> set[str]:
        if not self.success_path.is_file():
            return set()
        emails: set[str] = set()
        for line in self.success_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            email = str(item.get("email") or "").strip().lower()
            if email:
                emails.add(email)
        return emails

    def failed_emails(self) -> set[str]:
        if not self.failed_path.is_file():
            return set()
        emails: set[str] = set()
        for line in self.failed_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            email = str(item.get("email") or "").strip().lower()
            if email:
                emails.add(email)
        return emails

    def uncertain_payment_emails(self) -> set[str]:
        if not self.events_path.is_file():
            return set()
        uncertain: set[str] = set()
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            email = str(item.get("email") or "").strip().lower()
            if not email:
                continue
            if item.get("stage") == "payment" and item.get("status") == "submitting":
                uncertain.add(email)
            if item.get("stage") == "payment" and item.get("status") == "failed":
                uncertain.discard(email)
            if item.get("stage") == "workflow" and item.get("status") == "succeeded":
                uncertain.discard(email)
        return uncertain

    def event(self, *, email: str, stage: str, status: str, detail: str = "") -> None:
        self._append(
            self.events_path,
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "email": email,
                "stage": stage,
                "status": status,
                "detail": detail[:1000],
            },
        )

    def success(self, *, email: str) -> None:
        self._append(
            self.success_path,
            {
                "email": email,
                "plan": "claude_max_20x_monthly",
                "payment_method": "sepa_direct_debit",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def failure(self, *, email: str, reason: str) -> None:
        self._append(
            self.failed_path,
            {
                "email": email,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason[:1000],
            },
        )

    def _append(self, path: Path, item: dict[str, Any]) -> None:
        with self._write_lock:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(item, ensure_ascii=True, separators=(",", ":")) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())


def prepare_extension(source: Path, target: Path) -> Path:
    """Create a derived runtime copy with deterministic automation access.

    The protected JavaScript files are copied unchanged. The derived manifest
    adds only claude.ai host access and an empty service worker so Playwright can
    discover the generated extension ID without interacting with Chrome chrome.
    """

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    host_permissions = list(manifest.get("host_permissions") or [])
    if "https://claude.ai/*" not in host_permissions:
        host_permissions.append("https://claude.ai/*")
    manifest["host_permissions"] = host_permissions
    manifest["background"] = {"service_worker": "codex-automation-background.js"}
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "codex-automation-background.js").write_text(
        "chrome.runtime.onInstalled.addListener(() => {});\n", encoding="utf-8"
    )
    return target


def _visible(locator: Any) -> Any | None:
    try:
        count = locator.count()
    except Exception:
        return None
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


def _wait_visible(locator_factory: Any, *, timeout_s: float, error: str) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidate = _visible(locator_factory())
        if candidate is not None:
            return candidate
        time.sleep(0.25)
    raise BrowserFlowError(error)


def _wait_hidden(locator_factory: Any, *, timeout_s: float, error: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _visible(locator_factory()) is None:
            return
        time.sleep(0.25)
    raise BrowserFlowError(error)


def _wait_for_authenticated_page(page: Any, *, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        onboarding_marker = _visible(
            page.locator(
                '[data-test-id="terms-acceptance"], '
                'input[name="day"][data-input="true"]'
            )
        )
        if onboarding_marker is not None:
            return
        path = urlsplit(page.url).path.lower().rstrip("/")
        if path not in {"/login", "/magic-link"}:
            return
        time.sleep(0.25)
    raise BrowserFlowError(f"magic link did not establish a session: url={page.url}")


def _raise_if_terminal_account_state(page: Any) -> None:
    phone_input = _visible(
        page.locator('input[type="tel"][autocomplete="tel"]')
    )
    if phone_input is not None:
        raise AccountTerminalError("Claude requires phone verification")
    page_text = page.locator("body").inner_text()
    if re.search(r"account_banned|Your account is on hold", page_text, re.I):
        raise AccountTerminalError("Claude account is on hold (account_banned)")


def _wait_for_max_checkout(page: Any, *, timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _raise_if_terminal_account_state(page)
        path = urlsplit(page.url).path.lower().rstrip("/")
        if path == "/upgrade/max":
            return
        if path == "/login":
            raise BrowserFlowError(
                f"Max checkout redirected to login without authorization: url={page.url}"
            )
        time.sleep(0.25)
    raise BrowserFlowError(f"Max checkout did not load: url={page.url}")


def _button(page: Any, names: Iterable[str], *, timeout_s: float = 30) -> Any:
    patterns = [re.compile(name, re.I) for name in names]

    def locate() -> Any:
        combined = page.locator("button").filter(has_text=patterns[0])
        for pattern in patterns[1:]:
            combined = combined.or_(page.locator("button").filter(has_text=pattern))
        return combined

    return _wait_visible(locate, timeout_s=timeout_s, error=f"button not found: {list(names)}")


def _input_by_label(page: Any, patterns: Iterable[str], *, timeout_s: float = 30) -> Any:
    compiled = [re.compile(pattern, re.I) for pattern in patterns]

    def locate() -> Any:
        locator = page.get_by_label(compiled[0])
        for pattern in compiled[1:]:
            locator = locator.or_(page.get_by_label(pattern))
        return locator

    return _wait_visible(locate, timeout_s=timeout_s, error=f"input not found: {list(patterns)}")


def _field_in_frames(
    page: Any,
    patterns: Iterable[str],
    *,
    selectors: Iterable[str] = (),
    frames: Iterable[Any] | None = None,
    timeout_s: float = 30,
) -> Any:
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    selector_list = list(selectors)
    frame_list = list(frames) if frames is not None else list(page.frames)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in frame_list:
            for selector in selector_list:
                candidate = _visible(frame.locator(selector))
                if candidate is not None:
                    return candidate
            for pattern in compiled:
                candidate = _visible(frame.get_by_label(pattern))
                if candidate is not None:
                    return candidate
        time.sleep(0.25)
    raise BrowserFlowError(f"field not found in frames: {list(patterns)}")


def _plugin_stripe_frame(page: Any, selector: str, *, timeout_s: float = 30) -> Any:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        iframe = page.locator(selector).first
        if iframe.count():
            handle = iframe.element_handle()
            frame = handle.content_frame() if handle is not None else None
            if frame is not None:
                return frame
        time.sleep(0.25)
    raise BrowserFlowError(f"plugin Stripe iframe not found: {selector}")


def _submit_button(page: Any, names: Iterable[str], *, timeout_s: float = 30) -> Any:
    try:
        return _button(page, names, timeout_s=min(timeout_s, 10))
    except BrowserFlowError:
        return _wait_visible(
            lambda: page.locator('button[type="submit"], input[type="submit"]'),
            timeout_s=timeout_s,
            error=f"submit button not found: {list(names)}",
        )


def _button_following_input(field: Any) -> Any:
    return _wait_visible(
        lambda: field.locator("xpath=following::button[1]"),
        timeout_s=10,
        error="button following email input not found",
    )


def full_address_query(profile: BillingProfile) -> str:
    return f"{profile.line1}, {profile.postal_code} {profile.city}, Germany"


def _check_checkbox(checkbox: Any) -> None:
    if checkbox.is_checked():
        return
    checkbox.evaluate(
        """element => {
          const label = (element.labels && element.labels[0]) || element.closest('label');
          (label || element).click();
        }"""
    )
    if checkbox.is_checked():
        return
    checkbox.evaluate(
        """element => {
          const setter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype,
            'checked'
          ).set;
          setter.call(element, true);
          element.dispatchEvent(new Event('input', {bubbles: true}));
          element.dispatchEvent(new Event('change', {bubbles: true}));
        }"""
    )
    if not checkbox.is_checked():
        raise BrowserFlowError("checkbox state did not change after label and native events")


def _fill_exact(field: Any, value: str) -> None:
    field.click()
    field.fill(value)
    actual = field.input_value()
    if actual != value:
        raise BrowserFlowError(
            f"input value mismatch: expected_length={len(value)} actual_length={len(actual)}"
        )


def _fill_iban_exact(field: Any, iban: str) -> None:
    expected = re.sub(r"\s+", "", iban).upper()
    field.click()
    field.fill(expected)
    actual = re.sub(r"\s+", "", field.input_value()).upper()
    if actual != expected:
        raise BrowserFlowError(
            "IBAN input value mismatch: "
            f"expected_length={len(expected)} actual_length={len(actual)}"
        )


def _screenshot(page: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass


class ExtensionController:
    def __init__(self, context: Any) -> None:
        workers = context.service_workers
        if not workers:
            try:
                workers = [context.wait_for_event("serviceworker", timeout=15_000)]
            except Exception as exc:
                raise BrowserFlowError("loaded extension service worker was not discovered") from exc
        worker_url = workers[0].url
        parsed = urlsplit(worker_url)
        if parsed.scheme != "chrome-extension" or not parsed.netloc:
            raise BrowserFlowError(f"unexpected extension worker URL: {worker_url}")
        self.extension_id = parsed.netloc
        self.page = context.new_page()
        self.page.goto(f"chrome-extension://{self.extension_id}/popup.html")

    def inject(self, target_page: Any, script_file: str) -> Any:
        target_url = target_page.url
        result = self.page.evaluate(
            """async ({targetUrl, scriptFile}) => {
                const tabs = await chrome.tabs.query({url: ['https://claude.ai/*']});
                const target = tabs.find((tab) => tab.url === targetUrl) || tabs[0];
                if (!target || target.id === undefined) {
                    throw new Error(`Claude tab not found for ${targetUrl}`);
                }
                await chrome.scripting.executeScript({
                    target: {tabId: target.id},
                    files: [scriptFile],
                });
                return true;
            }""",
            {"targetUrl": target_url, "scriptFile": script_file},
        )
        target_page.bring_to_front()
        return result


class DirectScriptController:
    """Inject the protected content script without a browser-extension wrapper."""

    def __init__(self, extension_dir: Path) -> None:
        self.extension_dir = extension_dir

    def inject(self, target_page: Any, script_file: str) -> bool:
        script_path = self.extension_dir / script_file
        if not script_path.is_file():
            raise BrowserFlowError(f"extension script not found: {script_path}")
        target_page.add_script_tag(path=str(script_path))
        target_page.bring_to_front()
        return True


class ClaudeSepaBrowserFlow:
    def __init__(
        self,
        config: UpgradeConfig,
        artifacts_dir: Path,
        proxy_assignment: BackboneProxyAssignment,
        *,
        on_payment_submit: Callable[[], None] | None = None,
        on_payment_failure: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.artifacts_dir = artifacts_dir
        self.proxy_assignment = proxy_assignment
        self.on_payment_submit = on_payment_submit
        self.on_payment_failure = on_payment_failure

    def run(self, account: AccountInput, magic_client: ReadOnlyMagicLinkClient) -> bool:
        try:
            from camoufox.sync_api import Camoufox
        except ImportError as exc:
            raise BrowserFlowError(
                "camoufox and browserforge are required in the active Python"
            ) from exc

        profile_dir = Path(tempfile.mkdtemp(prefix="claude_sepa_profile_"))
        try:
            with Camoufox(
                **camoufox_fingerprint_launch_options(
                    config=self.config,
                    proxy_assignment=self.proxy_assignment,
                    profile_dir=profile_dir,
                )
            ) as context:
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(60_000)
                    extension = DirectScriptController(self.config.extension_path)
                    return self._run_page(page, extension, account, magic_client)
                except Exception:
                    if context.pages:
                        failed_page = context.pages[0]
                        _screenshot(failed_page, self.artifacts_dir / "failed.png")
                        try:
                            (self.artifacts_dir / "failed.html").write_text(
                                failed_page.content(), encoding="utf-8"
                            )
                        except Exception:
                            pass
                        frame_rows: list[dict[str, Any]] = []
                        for index, frame in enumerate(failed_page.frames):
                            frame_rows.append({"index": index, "url": frame.url})
                            try:
                                (self.artifacts_dir / f"failed-frame-{index:02d}.html").write_text(
                                    frame.content(), encoding="utf-8"
                                )
                            except Exception:
                                pass
                        try:
                            (self.artifacts_dir / "failed-frames.json").write_text(
                                json.dumps(frame_rows, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                        except Exception:
                            pass
                    raise
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)

    def _pause(self, page: Any, *, page_settle: bool = False) -> None:
        delay_ms = (
            self.config.page_settle_ms if page_settle else self.config.step_delay_ms
        )
        if delay_ms > 0:
            page.wait_for_timeout(delay_ms)

    def _slow_fill(self, page: Any, field: Any, value: str) -> None:
        _fill_exact(field, value)
        input_delay_ms = min(self.config.step_delay_ms, 300)
        if input_delay_ms > 0:
            page.wait_for_timeout(input_delay_ms)

    def _click(self, page: Any, target: Any, *, page_settle: bool = False) -> None:
        target.click()
        self._pause(page, page_settle=page_settle)

    def _run_page(
        self,
        page: Any,
        extension: ExtensionController | DirectScriptController,
        account: AccountInput,
        magic_client: ReadOnlyMagicLinkClient,
    ) -> bool:
        email_selector = 'input[type="email"], input[placeholder*="email" i]'
        email_input = None
        navigation_status: int | None = None
        navigation_error = ""
        for attempt in range(1, 4):
            try:
                response = page.goto(
                    "https://claude.ai/login",
                    wait_until="domcontentloaded",
                    timeout=self.config.navigation_timeout_ms,
                )
            except Exception as exc:
                if page.is_closed():
                    raise
                navigation_error = f"{type(exc).__name__}: {exc}"
                if attempt < 3:
                    self._pause(page, page_settle=True)
                    continue
                response = None
            navigation_status = response.status if response is not None else None
            try:
                email_input = _wait_visible(
                    lambda: page.locator(email_selector),
                    timeout_s=120,
                    error="Claude email input is still loading",
                )
            except BrowserFlowError:
                email_input = None
            if email_input is not None:
                break
            if attempt < 3:
                self._pause(page, page_settle=True)
        if email_input is None:
            try:
                title = page.title()[:120]
                body_length = len(page.locator("body").inner_text())
            except Exception:
                title = ""
                body_length = -1
            raise BrowserFlowError(
                "Claude email input not found after 3 navigations: "
                f"url={page.url} status={navigation_status} "
                f"title={title!r} body_length={body_length} "
                f"navigation_error={navigation_error!r}"
            )
        self._dismiss_cookie_banner(page)
        self._slow_fill(page, email_input, account.email)
        issued_after = time.time()
        self._click(page, _button_following_input(email_input))
        _wait_hidden(
            lambda: page.locator(email_selector),
            timeout_s=30,
            error="email submission was not accepted",
        )
        print(f"STEP {account.email} email_submitted", flush=True)
        magic_link = magic_client.wait_for_magic_link(
            email=account.email,
            issued_after=issued_after,
            timeout_s=self.config.magic_link_timeout_s,
        )
        page.goto(
            magic_link,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout_ms,
        )
        _wait_for_authenticated_page(page)
        self._pause(page)
        print(f"STEP {account.email} magic_link_opened", flush=True)
        invalid_link = _visible(
            page.get_by_text(re.compile(r"unable to verify you with this link", re.I))
        )
        if invalid_link is not None:
            raise MailLookupError("Claude rejected the extracted magic link")
        self._complete_account_creation(page)
        print(f"STEP {account.email} account_created", flush=True)
        self._complete_birthday(page)
        print(f"STEP {account.email} birthday_completed", flush=True)
        self._select_max_plan(page)
        print(f"STEP {account.email} max_plan_selected", flush=True)
        extension.inject(page, "claude-sepa.js")
        self._pause(page)
        self._create_sepa_form(page)
        print(f"STEP {account.email} sepa_form_created", flush=True)
        self._fill_billing(page, account.billing)
        print(f"STEP {account.email} billing_completed", flush=True)
        iban_candidates = iban_retry_candidates(self.config.ibans_file, account.iban)
        for attempt, iban in enumerate(iban_candidates, start=1):
            self._fill_iban(page, iban)
            print(
                f"STEP {account.email} iban_completed attempt={attempt}",
                flush=True,
            )
            try:
                return self._submit_and_verify(page)
            except PaymentAttemptError as exc:
                if self.on_payment_failure is not None:
                    self.on_payment_failure(str(exc))
                _screenshot(
                    page,
                    self.artifacts_dir / f"iban-failed-attempt-{attempt:02d}.png",
                )
                print(
                    f"IBAN_RETRY {account.email} next_attempt={attempt + 1}",
                    flush=True,
                )
        raise AccountTerminalError("all test IBAN candidates were rejected")

    def _complete_account_creation(self, page: Any) -> None:
        _raise_if_terminal_account_state(page)
        if _visible(self._birthday_inputs(page)) is not None:
            return
        terms_checkbox = _visible(
            page.locator('[data-test-id="terms-acceptance"]')
        )
        if terms_checkbox is None and "/onboarding" not in page.url:
            return
        _wait_visible(
            lambda: page.locator('[data-test-id="terms-acceptance"]'),
            timeout_s=90,
            error="Claude account agreement checkboxes not found",
        )
        self._pause(page)
        all_checkboxes = page.get_by_role("checkbox")
        visible = [all_checkboxes.nth(i) for i in range(all_checkboxes.count()) if all_checkboxes.nth(i).is_visible()]
        if len(visible) < 2:
            raise BrowserFlowError(f"expected two account checkboxes, found {len(visible)}")
        for checkbox in visible[:2]:
            _check_checkbox(checkbox)
            self._pause(page)
        self._click(
            page,
            _submit_button(page, [r"^Create account$", r"^Konto erstellen$"]),
        )
        _wait_visible(
            lambda: self._birthday_inputs(page),
            timeout_s=30,
            error="birthday page did not appear after account creation",
        )

    def _complete_birthday(self, page: Any) -> None:
        _raise_if_terminal_account_state(page)
        if _visible(self._birthday_inputs(page)) is None and "/onboarding" not in page.url:
            return
        day_input = _wait_visible(
            lambda: page.locator('input[name="day"][data-input="true"]'),
            timeout_s=90,
            error="Claude birthday day input not found",
        )
        month_input = _wait_visible(
            lambda: page.locator('input[name="month"][data-input="true"]'),
            timeout_s=10,
            error="Claude birthday month input not found",
        )
        year_input = _wait_visible(
            lambda: page.locator('input[name="year"][data-input="true"]'),
            timeout_s=10,
            error="Claude birthday year input not found",
        )
        day, month, year = birth_date_parts(random_birth_date())
        for field, value, name in (
            (day_input, day, "day"),
            (month_input, month, "month"),
            (year_input, year, "year"),
        ):
            self._slow_fill(page, field, value)
            if field.input_value() != value:
                raise BrowserFlowError(f"birthday {name} input did not retain its value")
        year_input.press("Tab")
        self._pause(page)
        self._click(
            page,
            _submit_button(page, [r"^Continue$", r"^Weiter$"]),
        )
        _wait_hidden(
            lambda: self._birthday_inputs(page),
            timeout_s=30,
            error="birthday input was not accepted",
        )

    @staticmethod
    def _birthday_inputs(page: Any) -> Any:
        return page.locator('input[name="day"][data-input="true"]')

    def _select_max_plan(self, page: Any) -> None:
        _raise_if_terminal_account_state(page)
        if "/upgrade/max" in page.url:
            return
        if "/onboarding" not in page.url:
            page.goto(
                MAX_UPGRADE_URL,
                wait_until="domcontentloaded",
                timeout=self.config.navigation_timeout_ms,
            )
            _wait_for_max_checkout(page)
            self._pause(page)
            return

        def locate() -> Any:
            _raise_if_terminal_account_state(page)
            heading = page.get_by_text(re.compile(r"^Max$", re.I))
            return heading.locator("xpath=ancestor::*[.//button][1]").get_by_role("button")

        self._click(
            page,
            _wait_visible(locate, timeout_s=60, error="Max plan button not found"),
            page_settle=True,
        )
        _wait_for_max_checkout(page)

    def _dismiss_cookie_banner(self, page: Any) -> None:
        dismiss = _visible(
            page.get_by_role(
                "button",
                name=re.compile(
                    r"Reject all cookies|Alle Cookies ablehnen|Rifiuta tutti i cookies",
                    re.I,
                ),
            )
        )
        if dismiss is not None:
            self._click(page, dismiss)

    def _create_sepa_form(self, page: Any) -> None:
        _wait_visible(
            lambda: page.get_by_text(re.compile(r"Claude SEPA Helper", re.I)),
            timeout_s=30,
            error="Claude SEPA Helper panel did not open",
        )
        self._click(
            page,
            _button(page, [r"创建表单", r"Create.*form"], timeout_s=30),
            page_settle=True,
        )

    def _fill_billing(self, page: Any, profile: BillingProfile) -> None:
        address_frame = _plugin_stripe_frame(
            page,
            '#csh-billing-address iframe[src*="elements-inner-address"]',
        )
        self._slow_fill(
            page,
            _field_in_frames(
                page,
                [
                    r"^姓名$",
                    r"全名",
                    r"Full name",
                    r"^Name$",
                    r"Vollständiger Name",
                ],
                selectors=[
                    'input[name="name"]',
                    '#billingAddress-nameInput',
                    'input[autocomplete="name"]',
                    'input[autocomplete$=" name"]',
                ],
                frames=[address_frame],
            ),
            profile.full_name,
        )
        country = _field_in_frames(
            page,
            [r"国家", r"Country", r"Land oder Region"],
            selectors=[
                'select[name="country"]',
                '#billingAddress-countryInput',
                'select[autocomplete="country"]',
                'select[autocomplete="country-name"]',
                'select[autocomplete$=" country"]',
            ],
            frames=[address_frame],
        )
        try:
            country.select_option(profile.country)
        except Exception:
            self._slow_fill(page, country, "Germany")
        else:
            self._pause(page)
        address_frame = _plugin_stripe_frame(
            page,
            '#csh-billing-address iframe[src*="elements-inner-address"]',
        )
        address_selected = False
        for attempt in range(1, 4):
            address_frame = _plugin_stripe_frame(
                page,
                '#csh-billing-address iframe[src*="elements-inner-address"]',
            )
            line1 = _field_in_frames(
                page,
                [r"地址第一行", r"Address line 1", r"Street", r"^Adresse$"],
                selectors=[
                    'input[name="addressLine1"]',
                    '#billingAddress-addressLine1Input',
                    'input[autocomplete="address-line1"]',
                    'input[autocomplete$=" address-line1"]',
                ],
                frames=[address_frame],
            )
            if attempt > 1:
                line1.fill("")
                page.wait_for_timeout(300)
            self._slow_fill(page, line1, full_address_query(profile))
            if self._choose_google_address(page, profile, timeout_s=6):
                if self._wait_for_plugin_address(page, profile, timeout_s=6):
                    address_selected = True
                    break
        if not address_selected:
            raise BrowserFlowError(
                "plugin Google address suggestion was not selected after 3 attempts"
            )
        address_frame = _plugin_stripe_frame(
            page,
            '#csh-billing-address iframe[src*="elements-inner-address"]',
        )
        if profile.line2:
            self._slow_fill(
                page,
                _field_in_frames(
                    page,
                    [r"地址第二行", r"Address line 2", r"Adresszeile 2"],
                    selectors=[
                        'input[name="addressLine2"]',
                        '#billingAddress-addressLine2Input',
                        'input[autocomplete="address-line2"]',
                        'input[autocomplete$=" address-line2"]',
                    ],
                    frames=[address_frame],
                    timeout_s=10,
                ),
                profile.line2,
            )
        self._slow_fill(
            page,
            _field_in_frames(
                page,
                [r"邮编", r"Postal", r"ZIP", r"Postleitzahl"],
                selectors=[
                    'input[name="postalCode"]',
                    '#billingAddress-postalCodeInput',
                    'input[autocomplete="postal-code"]',
                    'input[autocomplete$=" postal-code"]',
                ],
                frames=[address_frame],
            ),
            profile.postal_code,
        )
        self._slow_fill(
            page,
            _field_in_frames(
                page,
                [r"城市", r"City", r"Ort"],
                selectors=[
                    'input[name="locality"]',
                    '#billingAddress-localityInput',
                    'input[autocomplete="address-level2"]',
                    'input[autocomplete$=" address-level2"]',
                ],
                frames=[address_frame],
            ),
            profile.city,
        )
        if profile.state:
            self._slow_fill(
                page,
                _field_in_frames(
                    page,
                    [r"州", r"省", r"State"],
                    selectors=['input[autocomplete="address-level1"]'],
                    frames=[address_frame],
                    timeout_s=10,
                ),
                profile.state,
            )

    def _choose_google_address(
        self,
        page: Any,
        profile: BillingProfile,
        *,
        timeout_s: float,
    ) -> bool:
        suggestions_frame = _plugin_stripe_frame(
            page,
            '#csh-billing-address iframe[src*="autocomplete-suggestions"]',
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            options = suggestions_frame.locator('[role="option"]')
            for index in range(options.count()):
                option = options.nth(index)
                if not option.is_visible():
                    continue
                text = option.inner_text().lower()
                if profile.city.lower() in text or profile.postal_code.lower() in text:
                    self._click(page, option)
                    return True
            time.sleep(0.25)
        return False

    @staticmethod
    def _wait_for_plugin_address(
        page: Any,
        profile: BillingProfile,
        *,
        timeout_s: float,
    ) -> bool:
        expected_city = re.sub(r"[^a-z0-9]+", "", profile.city.casefold())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frame = _plugin_stripe_frame(
                page,
                '#csh-billing-address iframe[src*="elements-inner-address"]',
                timeout_s=1,
            )
            postal = frame.locator('input[name="postalCode"]')
            city = frame.locator('input[name="locality"]')
            if postal.count() and city.count():
                actual_postal = re.sub(r"\s+", "", postal.input_value())
                actual_city = re.sub(
                    r"[^a-z0-9]+", "", city.input_value().casefold()
                )
                if actual_postal == profile.postal_code and (
                    actual_city == expected_city
                    or actual_city in expected_city
                    or expected_city in actual_city
                ):
                    return True
            time.sleep(0.25)
        return False

    def _fill_iban(self, page: Any, iban: str) -> None:
        payment_frame = _plugin_stripe_frame(
            page,
            '#csh-payment-element iframe[src*="elements-inner-payment"]',
        )
        selectors = (
            'input[name="iban"]',
            'input[autocomplete="iban"]',
            'input[placeholder*="IBAN" i]',
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            for selector in selectors:
                field = _visible(payment_frame.locator(selector))
                if field is not None:
                    _fill_iban_exact(field, iban)
                    self._pause(page)
                    return
            time.sleep(0.25)
        raise BrowserFlowError("SEPA IBAN input not found")

    def _submit_and_verify(self, page: Any) -> bool:
        confirmation = _wait_visible(
            lambda: page.locator("#csh-consent"),
            timeout_s=30,
            error="SEPA subscription confirmation checkbox not found",
        )
        if not confirmation.is_checked():
            confirmation.check(force=True, timeout=5_000)
            self._pause(page)

        submit = _wait_visible(
            lambda: page.locator("#csh-pay"),
            timeout_s=30,
            error="plugin SEPA submit button not found",
        )
        _screenshot(page, self.artifacts_dir / "before-submit.png")
        if not self.config.submit_payment:
            raise BrowserFlowError("submit_payment=false; stopped before SEPA submission")
        if self.on_payment_submit is not None:
            self.on_payment_submit()
        self._click(page, submit)

        deadline = time.monotonic() + self.config.success_timeout_s
        sepa_text = re.compile(r"SEPA\s*(Direct Debit|借记)", re.I)
        while time.monotonic() < deadline:
            submit_gone = not submit.is_visible()
            success_marker = _visible(page.locator("#csh-status").filter(has_text=sepa_text))
            if submit_gone and success_marker is not None:
                _screenshot(page, self.artifacts_dir / "success.png")
                return True
            error_marker = _visible(
                page.locator('#csh-status[data-tone="error"]')
            )
            if error_marker is not None and submit.is_enabled():
                detail = " ".join(error_marker.inner_text().split())[:300]
                raise PaymentAttemptError(
                    f"plugin rejected SEPA attempt: {detail}"
                )
            time.sleep(0.5)
        _screenshot(page, self.artifacts_dir / "submit-timeout.png")
        raise BrowserFlowError("SEPA submit did not reach the required post-submit state")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the temporary Claude Max SEPA workflow")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args(argv)


def run_browser_preflight(config: UpgradeConfig) -> int:
    try:
        from camoufox.sync_api import Camoufox
    except ImportError as exc:
        raise BrowserFlowError("camoufox is required in the active Python") from exc

    assignment = WebshareBackboneProxyPool(config.proxy).allocate(1)[0]
    profile_dir = Path(tempfile.mkdtemp(prefix="claude_sepa_preflight_"))
    screenshot_path = config.output_dir / "camoufox-preflight.png"
    config.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Camoufox(
            **camoufox_fingerprint_launch_options(
                config=config,
                proxy_assignment=assignment,
                profile_dir=profile_dir,
            )
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()
            response = page.goto(
                "https://claude.ai/login",
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            page.wait_for_timeout(config.page_settle_ms)
            _screenshot(page, screenshot_path)
            body = page.locator("body").inner_text()
            email_inputs = page.locator(
                'input[type="email"], input[placeholder*="email" i]'
            ).count()
            challenge = bool(
                re.search(
                    r"performing security verification|verify you are human|just a moment",
                    f"{page.title()}\n{body}",
                    re.I,
                )
            )
            result = {
                "ok": email_inputs > 0 and not challenge,
                "status": response.status if response is not None else None,
                "url": page.url,
                "title": page.title(),
                "email_inputs": email_inputs,
                "cloudflare_challenge": challenge,
                "proxy": {
                    "country": assignment.country,
                    "endpoint": assignment.endpoint,
                    "exit_ip": assignment.exit_ip,
                },
                "fingerprint": page.evaluate(
                    """() => ({
                      userAgent: navigator.userAgent,
                      webdriver: navigator.webdriver,
                      platform: navigator.platform,
                      languages: navigator.languages,
                      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                      screen: [screen.width, screen.height],
                      hardwareConcurrency: navigator.hardwareConcurrency,
                    })"""
                ),
                "screenshot": str(screenshot_path),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def run(config: UpgradeConfig, *, limit: int = 0) -> int:
    accounts = load_account_inputs(config)
    recorder = JsonlRecorder(config.output_dir)
    completed = recorder.successful_emails()
    failed = recorder.failed_emails()
    uncertain = recorder.uncertain_payment_emails() - completed
    for email in sorted(failed):
        print(f"SKIPPED_FAILED {email}", file=sys.stderr)
    for email in sorted(uncertain):
        print(f"SKIPPED_UNCERTAIN {email}: verify payment status before retry", file=sys.stderr)
    pending = [
        account
        for account in accounts
        if account.email.lower() not in completed
        and account.email.lower() not in failed
        and account.email.lower() not in uncertain
    ]
    if not pending:
        print("No pending emails.")
        return 0

    target_successes = min(limit, len(pending)) if limit > 0 else len(pending)
    proxy_pool = WebshareBackboneProxyPool(config.proxy)

    def run_account(
        account: AccountInput,
        proxy_assignment: BackboneProxyAssignment,
    ) -> str:
        artifact_dir = config.output_dir / "artifacts" / f"{account.index:04d}"
        mail_client: ReadOnlyMagicLinkClient | None = None
        try:
            recorder.event(email=account.email, stage="workflow", status="started")
            recorder.event(
                email=account.email,
                stage="input",
                status="selected",
                detail=json.dumps(
                    {
                        "full_name": account.billing.full_name,
                        "country": account.billing.country,
                        "line1": account.billing.line1,
                        "line2": account.billing.line2,
                        "postal_code": account.billing.postal_code,
                        "city": account.billing.city,
                        "state": account.billing.state,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            recorder.event(
                email=account.email,
                stage="proxy",
                status="allocated",
                detail=json.dumps(
                    {
                        "provider": "webshare_backbone",
                        "country": proxy_assignment.country,
                        "endpoint": proxy_assignment.endpoint,
                        "endpoint_id": proxy_assignment.endpoint_id,
                        "exit_ip": proxy_assignment.exit_ip,
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            )
            print(
                f"BROWSER_START {account.email} "
                f"endpoint={proxy_assignment.endpoint} exit_ip={proxy_assignment.exit_ip}",
                flush=True,
            )
            mail_client = ReadOnlyMagicLinkClient(
                base_url=config.mail_base_url,
                api_key=config.mail_api_key,
                timeout_s=config.mail_timeout_s,
                poll_interval_s=config.mail_poll_interval_s,
            )
            succeeded = ClaudeSepaBrowserFlow(
                config,
                artifact_dir,
                proxy_assignment,
                on_payment_submit=lambda email=account.email: recorder.event(
                    email=email,
                    stage="payment",
                    status="submitting",
                ),
                on_payment_failure=lambda detail, email=account.email: recorder.event(
                    email=email,
                    stage="payment",
                    status="failed",
                    detail=detail,
                ),
            ).run(account, mail_client)
            if not succeeded:
                raise BrowserFlowError("workflow ended without SEPA success")
            recorder.success(email=account.email)
            recorder.event(email=account.email, stage="workflow", status="succeeded")
            print(f"SUCCESS {account.email}")
            return "success"
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, AccountTerminalError):
                try:
                    recorder.failure(email=account.email, reason=detail)
                except Exception:
                    pass
            try:
                recorder.event(
                    email=account.email,
                    stage="workflow",
                    status="failed",
                    detail=detail,
                )
            except Exception:
                pass
            print(f"FAILED {account.email}: {detail}", file=sys.stderr)
            return "terminal" if isinstance(exc, AccountTerminalError) else "failed"
        finally:
            if mail_client is not None:
                mail_client.close()

    next_account = 0
    successes = 0
    hard_failure = False
    while next_account < len(pending) and successes < target_successes:
        worker_count = min(
            config.browser_concurrency,
            target_successes - successes,
            len(pending) - next_account,
        )
        batch = pending[next_account : next_account + worker_count]
        next_account += worker_count
        proxy_assignments = proxy_pool.allocate(worker_count)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="claude-sepa-browser",
        ) as executor:
            futures = [
                executor.submit(run_account, account, proxy_assignment)
                for account, proxy_assignment in zip(
                    batch, proxy_assignments, strict=True
                )
            ]
            for future in concurrent.futures.as_completed(futures):
                outcome = future.result()
                if outcome == "success":
                    successes += 1
                elif outcome == "failed":
                    hard_failure = True
        if hard_failure:
            break
    return 0 if successes == target_successes else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = load_config(args.config.resolve())
        accounts = load_account_inputs(config)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "valid": True,
                        "accounts": len(accounts),
                        "extension": str(config.extension_path),
                        "output_dir": str(config.output_dir),
                        "mail_mode": "read_only_by_email",
                        "browser_mode": "persistent_camoufox_fingerprint",
                        "browser_concurrency": config.browser_concurrency,
                        "browser_geoip": "verified_proxy_exit_ip",
                        "proxy_mode": "webshare_backbone",
                        "proxy_country": config.proxy.country,
                        "submit_payment": config.submit_payment,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.preflight:
            return run_browser_preflight(config)
        return run(config, limit=max(0, args.limit))
    except ClaudeSepaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
