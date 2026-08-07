from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)
APP_ROOT = Path(__file__).resolve().parents[3]

CACHE_VERSION = 2
CACHEABLE_RESOURCE_TYPES = frozenset({"script", "stylesheet", "image"})
DEFAULT_TTL_S = 7 * 24 * 60 * 60
MAX_TTL_S = 30 * 24 * 60 * 60
MAX_SCRIPT_STYLE_TTL_S = 60 * 60
_CACHEABLE_HOSTS = frozenset(
    {
        "auth.openai.com",
        "chatgpt.com",
        "cdn.openai.com",
    }
)
_CACHEABLE_PATH_PREFIXES = ("/cdn/assets/", "/assets/", "/common/fonts/")
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


class BrowserStaticAssetCache:
    """Persistent disk cache for browser JavaScript, CSS, and image responses."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else default_browser_static_cache_dir()
        self.objects_dir = self.root / "objects"
        self.requests_dir = self.root / "requests"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._stored = 0
        self._bytes_served = 0
        self._bytes_stored = 0
        self._upstream_failures = 0
        self._bypass = False
        self._pending_requests: dict[int, tuple[str, str, str]] = {}

    def bypass(self) -> None:
        """Disable replay for the remainder of the browser context."""
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
        )

    def log_summary(self, *, flow: str) -> None:
        stats = self.stats()
        logger.info(
            "browser static cache: flow=%s root=%s hits=%s misses=%s stored=%s "
            "bytes_served=%s bytes_stored=%s upstream_failures=%s",
            flow,
            self.root,
            stats.hits,
            stats.misses,
            stats.stored,
            stats.bytes_served,
            stats.bytes_stored,
            stats.upstream_failures,
        )

    def _handle_route(self, route: Any, request: Any) -> None:
        resource_type = str(getattr(request, "resource_type", "") or "").lower()
        method = str(getattr(request, "method", "") or "").upper()
        headers = _request_headers(request)
        if (
            resource_type not in CACHEABLE_RESOURCE_TYPES
            or method != "GET"
            or "range" in headers
            or not is_browser_static_asset_url(str(getattr(request, "url", "") or ""))
            or self._bypass
        ):
            route.continue_()
            return

        key = _request_cache_key(request, resource_type=resource_type, headers=headers)
        cached = self._read_entry(key, request_url=str(getattr(request, "url", "") or ""))
        if cached is not None:
            status, response_headers, body = cached
            self._hits += 1
            self._bytes_served += len(body)
            route.fulfill(status=status, headers=response_headers, body=body)
            return

        self._misses += 1
        self._pending_requests[id(request)] = (
            key,
            str(getattr(request, "url", "") or ""),
            resource_type,
        )
        try:
            # A route.fetch() miss is issued by Playwright's request client,
            # not the browser network stack. Protected static assets can reject
            # that different request fingerprint and leave the rendered button
            # without its React click handler. Let Camoufox perform the original
            # request, then persist the completed browser response below.
            route.continue_()
        except Exception:
            self._pending_requests.pop(id(request), None)
            raise

    def _handle_request_finished(self, request: Any) -> None:
        pending = self._pending_requests.pop(id(request), None)
        if pending is None:
            return
        key, request_url, resource_type = pending
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
            body = bytes(response.body())
            ttl_s = _response_ttl_s(response_headers, resource_type=resource_type)
            if status == 200 and body and ttl_s > 0:
                self._write_entry(
                    key,
                    request_url=request_url,
                    resource_type=resource_type,
                    status=status,
                    headers=response_headers,
                    body=body,
                    ttl_s=ttl_s,
                )
        except Exception:
            logger.debug("browser static cache write failed", exc_info=True)

    def _handle_request_failed(self, request: Any) -> None:
        self._pending_requests.pop(id(request), None)

    def _read_entry(
        self,
        key: str,
        *,
        request_url: str = "",
    ) -> tuple[int, dict[str, str], bytes] | None:
        metadata_path = self._request_path(key)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if int(metadata.get("version") or 0) != CACHE_VERSION:
                return None
            if request_url and str(metadata.get("url") or "") != request_url:
                return None
            if float(metadata.get("expires_at") or 0) <= time.time():
                return None
            object_digest = str(metadata.get("object_sha256") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", object_digest):
                return None
            body = self._object_path(object_digest).read_bytes()
            if hashlib.sha256(body).hexdigest() != object_digest:
                return None
            headers = metadata.get("headers")
            if not isinstance(headers, dict):
                return None
            return (
                int(metadata.get("status") or 200),
                {str(name): str(value) for name, value in headers.items()},
                body,
            )
        except (OSError, ValueError, TypeError):
            return None

    def _write_entry(
        self,
        key: str,
        *,
        request_url: str,
        resource_type: str,
        status: int,
        headers: dict[str, str],
        body: bytes,
        ttl_s: int,
    ) -> None:
        object_digest = hashlib.sha256(body).hexdigest()
        object_path = self._object_path(object_digest)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if not object_path.exists():
            _atomic_write_bytes(object_path, body)

        now = time.time()
        metadata = {
            "version": CACHE_VERSION,
            "url": request_url,
            "resource_type": resource_type,
            "status": int(status),
            "headers": _replay_headers(headers),
            "object_sha256": object_digest,
            "body_size": len(body),
            "stored_at": now,
            "expires_at": now + max(1, int(ttl_s)),
        }
        metadata_path = self._request_path(key)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(
            metadata_path,
            json.dumps(metadata, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
        )
        self._stored += 1
        self._bytes_stored += len(body)

    def _object_path(self, digest: str) -> Path:
        return self.objects_dir / digest[:2] / digest

    def _request_path(self, key: str) -> Path:
        return self.requests_dir / key[:2] / f"{key}.json"


def install_browser_static_asset_cache(
    context: Any,
    *,
    cache_dir: str | Path | None = None,
) -> BrowserStaticAssetCache | None:
    if not browser_static_asset_cache_enabled():
        return None
    try:
        return BrowserStaticAssetCache(cache_dir).install(context)
    except Exception:
        logger.warning("browser static cache initialization failed", exc_info=True)
        return None


def browser_static_asset_cache_enabled() -> bool:
    """Use the local static-asset cache only when it is explicitly enabled."""
    value = str(os.environ.get("REFACTOR_APP_BROWSER_STATIC_ASSET_CACHE_ENABLED") or "")
    if not value.strip():
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


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
    return (
        parsed.scheme == "https"
        and host in _CACHEABLE_HOSTS
        and parsed.path.startswith(_CACHEABLE_PATH_PREFIXES)
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
    material = "\0".join(
        (
            str(CACHE_VERSION),
            str(getattr(request, "url", "") or ""),
            resource_type,
            headers.get("accept", ""),
            headers.get("accept-language", ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _response_ttl_s(headers: dict[str, str], *, resource_type: str = "") -> int:
    cache_control = str(headers.get("cache-control") or "").lower()
    directives = {part.strip() for part in cache_control.split(",") if part.strip()}
    if "no-store" in directives or "private" in directives:
        return 0
    max_age = _MAX_AGE_PATTERN.search(cache_control)
    if max_age:
        ttl_s = min(MAX_TTL_S, max(0, int(max_age.group(1))))
    else:
        ttl_s = DEFAULT_TTL_S
    if "no-cache" in directives:
        return 0
    if resource_type in {"script", "stylesheet"}:
        return min(MAX_SCRIPT_STYLE_TTL_S, ttl_s)
    return ttl_s


def _replay_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        str(name).lower(): str(value)
        for name, value in headers.items()
        if str(name).lower() not in _DROP_RESPONSE_HEADERS
    }


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
