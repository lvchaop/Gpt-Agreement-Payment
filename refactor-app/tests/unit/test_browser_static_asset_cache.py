from __future__ import annotations

import hashlib
import json
from pathlib import Path

from refactor_app.plugins.browser_static_asset_cache import (
    BrowserStaticAssetCache,
    browser_static_asset_cache_enabled,
    default_browser_static_cache_dir,
    is_browser_static_asset_url,
)


class _Request:
    def __init__(
        self,
        *,
        url: str,
        resource_type: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.resource_type = resource_type
        self.method = method
        self._headers = headers or {}
        self._response: _Response | None = None

    def all_headers(self) -> dict[str, str]:
        return dict(self._headers)

    def response(self) -> _Response | None:
        return self._response


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._headers = headers or {}

    def body(self) -> bytes:
        return self._body

    def all_headers(self) -> dict[str, str]:
        return dict(self._headers)


class _Route:
    def __init__(self, response: _Response | None = None) -> None:
        self.response = response
        self.fetch_count = 0
        self.continue_count = 0
        self.fallback_count = 0
        self.fulfill_calls: list[dict] = []

    def continue_(self) -> None:
        self.continue_count += 1

    def fallback(self) -> None:
        self.fallback_count += 1

    def fetch(self) -> _Response:
        self.fetch_count += 1
        assert self.response is not None
        return self.response

    def fulfill(self, **kwargs) -> None:
        self.fulfill_calls.append(kwargs)


class _Context:
    def __init__(self) -> None:
        self.pattern = ""
        self.handler = None
        self.events = {}

    def route(self, pattern: str, handler) -> None:
        self.pattern = pattern
        self.handler = handler

    def on(self, event: str, handler) -> None:
        self.events[event] = handler

    def finish(self, request: _Request, response: _Response) -> None:
        request._response = response
        self.events["requestfinished"](request)

    def fail(self, request: _Request) -> None:
        self.events["requestfailed"](request)


def test_script_is_written_once_and_served_from_disk(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/app.123.js",
        resource_type="script",
        headers={"Accept": "*/*", "Accept-Language": "en-US"},
    )
    response = _Response(
        b"console.log('cached')",
        headers={
            "Cache-Control": "public, max-age=3600, immutable",
            "Content-Type": "application/javascript",
            "Content-Encoding": "br",
        },
    )

    first = _Route()
    context.handler(first, request)
    assert first.fetch_count == 0
    assert first.fallback_count == 1
    assert first.fulfill_calls == []
    context.finish(request, response)

    second = _Route()
    context.handler(second, request)
    assert second.fetch_count == 0
    assert second.fulfill_calls[0]["status"] == 200
    assert second.fulfill_calls[0]["body"] == b"console.log('cached')"
    assert second.fulfill_calls[0]["headers"]["content-type"] == "application/javascript"
    assert "content-encoding" not in second.fulfill_calls[0]["headers"]
    assert cache.stats().hits == 1
    assert cache.stats().misses == 1
    assert cache.stats().stored == 1


def test_image_is_cached_and_document_bypasses_cache(tmp_path: Path) -> None:
    context = _Context()
    BrowserStaticAssetCache(tmp_path).install(context)
    image = _Request(
        url="https://chatgpt.com/cdn/assets/logo.webp",
        resource_type="image",
    )
    image_response = _Response(
        b"image-bytes",
        headers={"Cache-Control": "max-age=60", "Content-Type": "image/webp"},
    )
    image_route = _Route()
    context.handler(image_route, image)
    assert image_route.fallback_count == 1
    assert image_route.fetch_count == 0
    context.finish(image, image_response)

    document_route = _Route()
    context.handler(
        document_route,
        _Request(url="https://chatgpt.com/", resource_type="document"),
    )
    assert document_route.fallback_count == 1
    assert document_route.fetch_count == 0


def test_stylesheet_is_written_once_and_served_from_disk(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/app.123.css",
        resource_type="stylesheet",
        headers={"Accept": "text/css,*/*;q=0.1", "Accept-Language": "en-US"},
    )
    response = _Response(
        b"body { color: black; }",
        headers={
            "Cache-Control": "public, max-age=3600, immutable",
            "Content-Type": "text/css; charset=utf-8",
        },
    )

    first = _Route()
    context.handler(first, request)
    assert first.fallback_count == 1
    context.finish(request, response)
    replay = _Route()
    context.handler(replay, request)

    assert replay.fetch_count == 0
    assert replay.fulfill_calls[0]["body"] == b"body { color: black; }"
    assert replay.fulfill_calls[0]["headers"]["content-type"] == (
        "text/css; charset=utf-8"
    )
    assert cache.stats().hits == 1
    assert cache.stats().misses == 1
    assert cache.stats().stored == 1


def test_private_or_no_store_static_response_is_not_persisted(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/private.js",
        resource_type="script",
    )

    for cache_control in ("private, max-age=3600", "no-store"):
        response = _Response(
            b"private",
            headers={"Cache-Control": cache_control, "Content-Type": "text/javascript"},
        )
        first = _Route()
        context.handler(first, request)
        context.finish(request, response)
        second = _Route()
        context.handler(second, request)
        assert second.fallback_count == 1
        assert second.fetch_count == 0
        context.fail(request)

    assert cache.stats().hits == 0
    assert cache.stats().stored == 0


def test_cache_key_varies_by_accept_and_language(tmp_path: Path) -> None:
    context = _Context()
    BrowserStaticAssetCache(tmp_path).install(context)
    response = _Response(
        b"image",
        headers={"Cache-Control": "max-age=60", "Content-Type": "image/avif"},
    )
    first_request = _Request(
        url="https://chatgpt.com/cdn/assets/image",
        resource_type="image",
        headers={"Accept": "image/avif", "Accept-Language": "en-US"},
    )
    first = _Route()
    context.handler(first, first_request)
    context.finish(first_request, response)

    different_accept = _Route()
    different_request = _Request(
        url=first_request.url,
        resource_type="image",
        headers={"Accept": "image/webp", "Accept-Language": "en-US"},
    )
    context.handler(
        different_accept,
        different_request,
    )
    assert different_accept.fallback_count == 1
    assert different_accept.fetch_count == 0
    context.fail(different_request)


def test_default_cache_dir_uses_persistent_xdg_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("REFACTOR_APP_BROWSER_STATIC_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert default_browser_static_cache_dir() == (
        tmp_path / "refactor-app" / "browser-static-assets"
    )


def test_default_cache_dir_falls_back_to_project_runtime(monkeypatch) -> None:
    monkeypatch.delenv("REFACTOR_APP_BROWSER_STATIC_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    project_root = Path(__file__).resolve().parents[2]
    assert default_browser_static_cache_dir() == (
        project_root / "runtime" / "cache" / "browser-static-assets"
    )


def test_static_asset_cache_is_enabled_when_no_override_is_set(monkeypatch) -> None:
    monkeypatch.delenv("REFACTOR_APP_BROWSER_STATIC_ASSET_CACHE_ENABLED", raising=False)

    assert browser_static_asset_cache_enabled() is True


def test_static_asset_cache_can_be_explicitly_disabled(monkeypatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_STATIC_ASSET_CACHE_ENABLED", "false")

    assert browser_static_asset_cache_enabled() is False


def test_static_asset_cache_can_be_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_STATIC_ASSET_CACHE_ENABLED", "true")

    assert browser_static_asset_cache_enabled() is True


def test_same_url_keeps_distinct_content_versions_and_switches_current(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/app.js?release=stable",
        resource_type="script",
        headers={"Accept": "*/*"},
    )
    first_body = b"window.release = 'first'"
    first_response = _Response(
        first_body,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "application/javascript",
            "Content-MD5": "first-md5",
            "Last-Modified": "Sat, 08 Aug 2026 00:00:00 GMT",
        },
    )
    first_route = _Route()
    context.handler(first_route, request)
    context.finish(request, first_response)

    current_path = next((tmp_path / "v3" / "requests").glob("*/*/variants/*/current.json"))
    first_current = json.loads(current_path.read_text(encoding="utf-8"))
    first_version = first_current["asset_version"]
    first_metadata_path = current_path.parent / "versions" / f"{first_version}.json"
    first_metadata = json.loads(first_metadata_path.read_text(encoding="utf-8"))
    first_metadata["fresh_until"] = 0
    first_metadata_path.write_text(json.dumps(first_metadata), encoding="utf-8")

    stale_route = _Route()
    context.handler(stale_route, request)
    assert stale_route.fallback_count == 1
    second_body = b"window.release = 'second'"
    context.finish(
        request,
        _Response(
            second_body,
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Type": "application/javascript",
                "Content-MD5": "second-md5",
                "Last-Modified": "Sun, 09 Aug 2026 00:00:00 GMT",
            },
        ),
    )

    second_current = json.loads(current_path.read_text(encoding="utf-8"))
    second_version = second_current["asset_version"]
    assert first_version == hashlib.sha256(first_body).hexdigest()
    assert second_version == hashlib.sha256(second_body).hexdigest()
    assert second_version != first_version
    assert first_metadata_path.exists()
    assert (current_path.parent / "versions" / f"{second_version}.json").exists()
    assert (tmp_path / "v3" / "objects" / first_version[:2] / first_version).exists()
    assert (tmp_path / "v3" / "objects" / second_version[:2] / second_version).exists()

    replay = _Route()
    context.handler(replay, request)
    assert replay.fulfill_calls[0]["body"] == second_body
    assert cache.stats().stored == 2


def test_vary_header_creates_separate_disk_variant(tmp_path: Path) -> None:
    context = _Context()
    BrowserStaticAssetCache(tmp_path).install(context)
    english = _Request(
        url="https://auth-cdn.oaistatic.com/assets/messages.js",
        resource_type="script",
        headers={"Accept": "*/*", "Accept-Language": "en-US"},
    )
    first = _Route()
    context.handler(first, english)
    context.finish(
        english,
        _Response(
            b"window.locale='en'",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Type": "application/javascript",
                "Vary": "Accept-Language",
            },
        ),
    )

    chinese = _Request(
        url=english.url,
        resource_type="script",
        headers={"Accept": "*/*", "Accept-Language": "zh-CN"},
    )
    second = _Route()
    context.handler(second, chinese)
    assert second.fallback_count == 1
    assert second.fulfill_calls == []


def test_corrupt_body_invalidates_pointer_and_falls_back(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/corrupt.js",
        resource_type="script",
    )
    first = _Route()
    context.handler(first, request)
    context.finish(
        request,
        _Response(
            b"valid-body",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Type": "application/javascript",
            },
        ),
    )
    object_path = next((tmp_path / "v3" / "objects").glob("*/*"))
    object_path.write_bytes(b"corrupt-body")

    replay = _Route()
    context.handler(replay, request)
    assert replay.fallback_count == 1
    assert replay.fulfill_calls == []
    assert cache.stats().corrupt_entries == 1
    assert list((tmp_path / "v3" / "requests").glob("*/*/variants/*/current.json")) == []


def test_set_cookie_or_wrong_content_type_is_not_persisted(tmp_path: Path) -> None:
    context = _Context()
    cache = BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://chatgpt.com/cdn/assets/not-public.js",
        resource_type="script",
    )
    for headers in (
        {
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "application/javascript",
            "Set-Cookie": "private=value",
        },
        {
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "text/html",
        },
    ):
        route = _Route()
        context.handler(route, request)
        context.finish(request, _Response(b"not-cacheable", headers=headers))

    assert cache.stats().stored == 0
    assert list((tmp_path / "v3" / "objects").glob("*/*")) == []


def test_origin_max_age_is_not_reduced_to_one_hour(tmp_path: Path) -> None:
    context = _Context()
    BrowserStaticAssetCache(tmp_path).install(context)
    request = _Request(
        url="https://auth-cdn.oaistatic.com/assets/long-lived.js",
        resource_type="script",
    )
    route = _Route()
    context.handler(route, request)
    context.finish(
        request,
        _Response(
            b"long-lived",
            headers={
                "Cache-Control": "public, max-age=2592000",
                "Content-Type": "application/javascript",
                "Content-MD5": "content-version",
                "Last-Modified": "Sun, 09 Aug 2026 00:00:00 GMT",
            },
        ),
    )

    metadata_path = next((tmp_path / "v3" / "requests").glob("*/*/variants/*/versions/*.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert int(metadata["fresh_until"] - metadata["stored_at"]) == 2_592_000
    assert metadata["validators"] == {
        "etag": "",
        "content_md5": "content-version",
        "last_modified": "Sun, 09 Aug 2026 00:00:00 GMT",
    }


def test_only_observed_public_static_hosts_are_eligible() -> None:
    assert is_browser_static_asset_url(
        "https://auth-cdn.oaistatic.com/assets/app.js"
    ) is True
    assert is_browser_static_asset_url("https://js.stripe.com/v3/app.js") is True
    assert is_browser_static_asset_url("https://sentinel.openai.com/sdk.js") is False
    assert is_browser_static_asset_url("https://chatgpt.com/backend-api/me") is False
