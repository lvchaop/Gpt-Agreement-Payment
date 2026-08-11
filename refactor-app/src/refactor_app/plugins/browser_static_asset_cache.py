from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from refactor_app.plugins.browser_static_asset_store import (
    CACHE_SCHEMA_VERSION,
    CorruptStaticAssetError,
    DiskStaticAssetStore,
)

logger = logging.getLogger(__name__)
APP_ROOT = Path(__file__).resolve().parents[3]

CACHE_VERSION = CACHE_SCHEMA_VERSION
CACHEABLE_RESOURCE_TYPES = frozenset({"script", "stylesheet", "image", "font"})
DEFAULT_TTL_S = 7 * 24 * 60 * 60
MAX_TTL_S = 30 * 24 * 60 * 60
DEFAULT_MAX_OBJECT_BYTES = 20 * 1024 * 1024
_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled"})
_BASE_VARIANT_HEADERS = ("accept",)
_SENSITIVE_VARY_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)
_CACHEABLE_HOST_PATHS: dict[str, tuple[str, ...]] = {
    "auth.openai.com": ("/assets/", "/cdn/assets/", "/common/fonts/"),
    "chatgpt.com": ("/assets/", "/cdn/assets/", "/common/fonts/"),
    "cdn.openai.com": ("/",),
    "auth-cdn.oaistatic.com": ("/",),
    "persistent.oaistatic.com": ("/",),
    "js.stripe.com": ("/",),
    "b.stripecdn.com": ("/",),
    "applepay.cdn-apple.com": ("/",),
    "fonts.gstatic.com": ("/",),
    "www.gstatic.com": ("/",),
}
_MAX_AGE_PATTERN = re.compile(r"(?:^|,)\s*(?:s-maxage|max-age)\s*=\s*(\d+)", re.I)
_DROP_RESPONSE_HEADERS = frozenset(
    {
        "age",
        "connection",
        "content-encoding",
        "content-length",
        "date",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


@dataclass(frozen=True)
class StaticAssetCacheStats:
    hits: int
    misses: int
    stored: int
    bytes_served: int
    bytes_stored: int
    upstream_failures: int = 0
    corrupt_entries: int = 0


@dataclass(frozen=True)
class _PendingRequest:
    request_id: str
    request_url: str
    resource_type: str
    request_headers: dict[str, str]


class BrowserStaticAssetCache:
    """Global browser interceptor backed by a content-versioned disk store."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        max_object_bytes: int | None = None,
    ) -> None:
        self.root = Path(root) if root else default_browser_static_cache_dir()
        self.store = DiskStaticAssetStore(self.root)
        self.schema_root = self.store.schema_root
        self.objects_dir = self.store.objects_dir
        self.requests_dir = self.store.requests_dir
        self.max_object_bytes = (
            max(1, int(max_object_bytes))
            if max_object_bytes is not None
            else browser_static_cache_max_object_bytes()
        )
        self._hits = 0
        self._misses = 0
        self._stored = 0
        self._bytes_served = 0
        self._bytes_stored = 0
        self._upstream_failures = 0
        self._corrupt_entries = 0
        self._bypass = False
        self._pending_requests: dict[int, _PendingRequest] = {}

    def bypass(self) -> None:
        self._bypass = True

    def install(self, context: Any) -> BrowserStaticAssetCache:
        context.route("**/*", self._handle_route)
        context.on("requestfinished", self._handle_request_finished)
        context.on("requestfailed", self._handle_request_failed)
        return self

    def stats(self) -> StaticAssetCacheStats:
        return StaticAssetCacheStats(
            hits=self._hits,
            misses=self._misses,
            stored=self._stored,
            bytes_served=self._bytes_served,
            bytes_stored=self._bytes_stored,
            upstream_failures=self._upstream_failures,
            corrupt_entries=self._corrupt_entries,
        )

    def log_summary(self, *, flow: str) -> None:
        stats = self.stats()
        logger.info(
            "browser static cache: flow=%s root=%s hits=%s misses=%s stored=%s "
            "bytes_served=%s bytes_stored=%s upstream_failures=%s corrupt_entries=%s",
            flow,
            self.schema_root,
            stats.hits,
            stats.misses,
            stats.stored,
            stats.bytes_served,
            stats.bytes_stored,
            stats.upstream_failures,
            stats.corrupt_entries,
        )

    def _handle_route(self, route: Any, request: Any) -> None:
        resource_type = str(getattr(request, "resource_type", "") or "").lower()
        method = str(getattr(request, "method", "") or "").upper()
        request_url = str(getattr(request, "url", "") or "")
        headers = _request_headers(request)
        if (
            self._bypass
            or resource_type not in CACHEABLE_RESOURCE_TYPES
            or method != "GET"
            or "range" in headers
            or not is_browser_static_asset_url(request_url)
        ):
            _route_fallback(route)
            return

        request_id = _request_cache_key(
            request,
            resource_type=resource_type,
            headers=headers,
        )
        try:
            cached = self.store.read(
                request_id,
                request_url=request_url,
                resource_type=resource_type,
                request_headers=headers,
            )
        except CorruptStaticAssetError:
            self._corrupt_entries += 1
            cached = None
        if cached is not None:
            self._hits += 1
            self._bytes_served += len(cached.body)
            route.fulfill(status=cached.status, headers=cached.headers, body=cached.body)
            return

        self._misses += 1
        self._pending_requests[id(request)] = _PendingRequest(
            request_id=request_id,
            request_url=request_url,
            resource_type=resource_type,
            request_headers=headers,
        )
        try:
            # Keep misses in the browser network stack. route.fetch() changes
            # the request client and can break protected JavaScript responses.
            _route_fallback(route)
        except Exception:
            self._pending_requests.pop(id(request), None)
            raise

    def _handle_request_finished(self, request: Any) -> None:
        pending = self._pending_requests.pop(id(request), None)
        if pending is None or self._bypass:
            return
        try:
            response_getter = getattr(request, "response", None)
            response = response_getter() if callable(response_getter) else response_getter
            if response is None:
                return
            status = int(getattr(response, "status", 0) or 0)
            response_headers = _response_headers(response)
            if status >= 400:
                self._upstream_failures += 1
                return
            if status != 200 or not _response_is_cacheable(
                response_headers,
                resource_type=pending.resource_type,
            ):
                return
            content_length = _positive_int(response_headers.get("content-length"))
            if content_length and content_length > self.max_object_bytes:
                return
            body = bytes(response.body())
            if not body or len(body) > self.max_object_bytes:
                return
            ttl_s = _response_ttl_s(response_headers, resource_type=pending.resource_type)
            vary_headers = _response_vary_headers(response_headers)
            if ttl_s <= 0 or vary_headers is None:
                return
            self.store.write(
                pending.request_id,
                request_url=pending.request_url,
                resource_type=pending.resource_type,
                request_headers=pending.request_headers,
                vary_headers=vary_headers,
                status=status,
                replay_headers=_replay_headers(response_headers),
                validators={
                    "etag": str(response_headers.get("etag") or ""),
                    "content_md5": str(response_headers.get("content-md5") or ""),
                    "last_modified": str(response_headers.get("last-modified") or ""),
                },
                body=body,
                ttl_s=ttl_s,
            )
            self._stored += 1
            self._bytes_stored += len(body)
        except Exception:
            logger.debug("browser static cache write failed", exc_info=True)

    def _handle_request_failed(self, request: Any) -> None:
        self._pending_requests.pop(id(request), None)


def install_browser_static_asset_cache(
    context: Any,
    *,
    cache_dir: str | Path | None = None,
) -> BrowserStaticAssetCache | None:
    if not browser_static_asset_cache_enabled():
        return None
    if not callable(getattr(context, "route", None)) or not callable(
        getattr(context, "on", None)
    ):
        return None
    try:
        return BrowserStaticAssetCache(cache_dir).install(context)
    except Exception:
        logger.warning("browser static cache initialization failed", exc_info=True)
        return None


def browser_static_asset_cache_enabled() -> bool:
    value = str(os.environ.get("REFACTOR_APP_BROWSER_STATIC_ASSET_CACHE_ENABLED") or "")
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return normalized in _TRUE_VALUES


def browser_static_cache_max_object_bytes() -> int:
    value = str(os.environ.get("REFACTOR_APP_BROWSER_STATIC_CACHE_MAX_OBJECT_BYTES") or "")
    try:
        return max(1, int(value)) if value.strip() else DEFAULT_MAX_OBJECT_BYTES
    except ValueError:
        return DEFAULT_MAX_OBJECT_BYTES


def default_browser_static_cache_dir() -> Path:
    explicit = str(os.environ.get("REFACTOR_APP_BROWSER_STATIC_CACHE_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg_cache = str(os.environ.get("XDG_CACHE_HOME") or "").strip()
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "refactor-app" / "browser-static-assets"
    return APP_ROOT / "runtime" / "cache" / "browser-static-assets"


def is_browser_static_asset_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = str(parsed.hostname or "").lower().rstrip(".")
    prefixes = _CACHEABLE_HOST_PATHS.get(host)
    return bool(
        parsed.scheme == "https"
        and prefixes
        and any(parsed.path.startswith(prefix) for prefix in prefixes)
    )


def _request_headers(request: Any) -> dict[str, str]:
    try:
        raw = request.all_headers()
    except Exception:
        raw = getattr(request, "headers", {})
    if not isinstance(raw, dict):
        return {}
    return {str(name).lower(): str(value) for name, value in raw.items()}


def _response_headers(response: Any) -> dict[str, str]:
    try:
        raw = response.all_headers()
    except Exception:
        raw = getattr(response, "headers", {})
    if not isinstance(raw, dict):
        return {}
    return {str(name).lower(): str(value) for name, value in raw.items()}


def _request_cache_key(
    request: Any,
    *,
    resource_type: str,
    headers: dict[str, str],
) -> str:
    del headers
    material = "\0".join(
        (
            str(CACHE_SCHEMA_VERSION),
            "GET",
            str(getattr(request, "url", "") or ""),
            resource_type,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _response_vary_headers(headers: dict[str, str]) -> tuple[str, ...] | None:
    values = {
        part.strip().lower()
        for part in str(headers.get("vary") or "").split(",")
        if part.strip()
    }
    if "*" in values or values.intersection(_SENSITIVE_VARY_HEADERS):
        return None
    values.update(_BASE_VARIANT_HEADERS)
    return tuple(sorted(values))


def _response_ttl_s(headers: dict[str, str], *, resource_type: str = "") -> int:
    del resource_type
    cache_control = str(headers.get("cache-control") or "").lower()
    directives = {part.strip() for part in cache_control.split(",") if part.strip()}
    if any(
        directive == blocked or directive.startswith(f"{blocked}=")
        for directive in directives
        for blocked in ("no-store", "private", "no-cache")
    ):
        return 0
    max_age = _MAX_AGE_PATTERN.search(cache_control)
    if max_age:
        return min(MAX_TTL_S, max(0, int(max_age.group(1))))
    return DEFAULT_TTL_S


def _response_is_cacheable(headers: dict[str, str], *, resource_type: str) -> bool:
    if "set-cookie" in headers:
        return False
    content_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if resource_type == "script":
        return content_type in {
            "application/ecmascript",
            "application/javascript",
            "application/x-javascript",
            "text/ecmascript",
            "text/javascript",
        }
    if resource_type == "stylesheet":
        return content_type == "text/css"
    if resource_type == "image":
        return content_type.startswith("image/")
    if resource_type == "font":
        return content_type.startswith("font/") or content_type in {
            "application/font-sfnt",
            "application/font-woff",
            "application/octet-stream",
            "application/vnd.ms-fontobject",
            "application/x-font-ttf",
            "application/x-font-woff",
        }
    return False


def _replay_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        str(name).lower(): str(value)
        for name, value in headers.items()
        if str(name).lower() not in _DROP_RESPONSE_HEADERS
    }


def _route_fallback(route: Any) -> None:
    fallback = getattr(route, "fallback", None)
    if callable(fallback):
        fallback()
        return
    route.continue_()


def _positive_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except ValueError:
        return 0


__all__ = [
    "BrowserStaticAssetCache",
    "CACHE_SCHEMA_VERSION",
    "CACHE_VERSION",
    "StaticAssetCacheStats",
    "browser_static_asset_cache_enabled",
    "default_browser_static_cache_dir",
    "install_browser_static_asset_cache",
    "is_browser_static_asset_url",
]
