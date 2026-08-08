from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

BrowserLogEmitter = Callable[[str, dict[str, Any], str], None]

_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|set-cookie|proxy-authorization|api[-_]?key|"
    r"access[-_]?token|refresh[-_]?token|id[-_]?token|client[-_]?secret|"
    r"password|passwd|passcode|secret|otp|one[-_]?time|cvc|cvv|card[-_]?number)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:token|secret|key|code|otp|cvc|cvv|password|session|authorization)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(\bBearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_CARD_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_TEXT_CONTENT_TYPE = re.compile(
    r"(?:application/(?:json|graphql|javascript|x-www-form-urlencoded)|"
    r"text/|xml|javascript)",
    re.IGNORECASE,
)


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or ""))
        if not parsed.scheme and not parsed.netloc:
            return _redact_text(str(value or ""))
        query = [
            (key, "<redacted>" if _SENSITIVE_QUERY_KEY.search(key) else item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
        if parsed.username:
            hostname = f"<redacted>@{hostname}"
        netloc = hostname
        return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), ""))
    except Exception:
        return "<invalid-url>"


def _redact_text(value: str) -> str:
    text = str(value or "")
    text = _BEARER.sub(r"\1<redacted>", text)
    text = _JWT.sub("<redacted-jwt>", text)
    return _CARD_NUMBER.sub("<redacted-card>", text)


def redact_browser_value(value: Any, *, key: str = "") -> Any:
    """Return JSON-safe browser diagnostics with credential/payment data removed."""
    if _SENSITIVE_KEY.search(str(key or "")):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(name): redact_browser_value(item, key=str(name))
            for name, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_browser_value(item) for item in value]
    if isinstance(value, bytes):
        return _redact_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, str):
        return (
            _redact_url(value)
            if key.lower() in {"url", "href", "referrer"}
            else _redact_text(value)
        )
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _body_for_log(value: Any, *, max_chars: int) -> dict[str, Any]:
    text = str(value or "")
    if not text:
        return {"body": "", "body_truncated": False}
    try:
        parsed = json.loads(text)
    except Exception:
        safe: Any = _redact_text(text)
    else:
        safe = redact_browser_value(parsed)
    serialized = (
        safe
        if isinstance(safe, str)
        else json.dumps(safe, ensure_ascii=True, separators=(",", ":"))
    )
    truncated = len(serialized) > max_chars
    return {
        "body": serialized[:max_chars],
        "body_truncated": truncated,
        "body_chars": len(serialized),
    }


def _read_attr(obj: Any, name: str, default: Any = "") -> Any:
    try:
        value = getattr(obj, name, default)
        return value() if callable(value) else value
    except Exception as exc:
        return f"<read-error:{type(exc).__name__}>"


def _request_page_url(request: Any) -> str:
    try:
        frame = request.frame
        page = getattr(frame, "page", None)
        return _redact_url(str(getattr(page, "url", "") or "")) if page is not None else ""
    except Exception:
        return ""


class BrowserLogRecorder:
    """Capture Playwright browser events into JSONL and the existing job trace."""

    def __init__(
        self,
        *,
        path: Path | None,
        emitter: BrowserLogEmitter | None,
        capture_bodies: bool = False,
        max_body_chars: int = 20_000,
    ) -> None:
        self.path = path
        self._emitter = emitter
        self._capture_bodies = bool(capture_bodies)
        self._max_body_chars = max(1_000, int(max_body_chars or 20_000))
        self._lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        self._bindings: list[tuple[Any, str, Callable[..., Any]]] = []
        self._request_ids: dict[int, tuple[str, float]] = {}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def install(self, context: Any) -> BrowserLogRecorder:
        self._bind(context, "page", self._on_page)
        self._bind(context, "request", self._on_request)
        self._bind(context, "response", self._on_response)
        self._bind(context, "requestfailed", self._on_request_failed)
        self._bind(context, "requestfinished", self._on_request_finished)
        for page in list(getattr(context, "pages", []) or []):
            self._on_page(page)
        self.record(
            "browser.log.enabled",
            {
                "path": str(self.path) if self.path else "",
                "capture_bodies": self._capture_bodies,
                "max_body_chars": self._max_body_chars,
            },
        )
        return self

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for target, event, callback in reversed(self._bindings):
            try:
                target.remove_listener(event, callback)
            except Exception:
                pass
        self.record(
            "browser.log.closed",
            {"path": str(self.path) if self.path else ""},
            notify=True,
        )

    def record(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        level: str = "INFO",
        *,
        notify: bool = True,
    ) -> None:
        safe_data = redact_browser_value(data or {})
        with self._lock:
            self._sequence += 1
            entry = {
                "ts": time.time(),
                "sequence": self._sequence,
                "event": str(event_type),
                "level": str(level),
                "data": safe_data,
            }
            if self.path is not None:
                try:
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(entry, ensure_ascii=True, separators=(",", ":")))
                        handle.write("\n")
                except Exception:
                    pass
        if notify and self._emitter is not None:
            try:
                self._emitter(str(event_type), safe_data, str(level))
            except Exception:
                pass

    def _bind(self, target: Any, event: str, callback: Callable[..., Any]) -> None:
        try:
            target.on(event, callback)
            self._bindings.append((target, event, callback))
        except Exception as exc:
            self.record(
                "browser.log.listener_error",
                {"event": event, "error": f"{type(exc).__name__}: {exc}"},
                "WARN",
            )

    def _on_page(self, page: Any) -> None:
        self._bind(page, "console", self._on_console)
        self._bind(page, "pageerror", self._on_page_error)
        self._bind(page, "framenavigated", self._on_frame_navigated)
        self._bind(
            page,
            "close",
            lambda: self.record(
                "browser.page.closed",
                {"url": _redact_url(_read_attr(page, "url"))},
            ),
        )
        self.record("browser.page.created", {"url": _redact_url(_read_attr(page, "url"))})

    def _request_data(self, request: Any) -> dict[str, Any]:
        request_id = self._request_ids.setdefault(id(request), (str(uuid4()), time.monotonic()))[0]
        data: dict[str, Any] = {
            "request_id": request_id,
            "method": str(_read_attr(request, "method") or "").upper(),
            "url": _redact_url(str(_read_attr(request, "url") or "")),
            "resource_type": str(_read_attr(request, "resource_type") or ""),
            "page_url": _request_page_url(request),
        }
        headers = _read_attr(request, "all_headers", {})
        if isinstance(headers, dict):
            data["headers"] = redact_browser_value(headers)
        if self._capture_bodies:
            data.update(
                _body_for_log(
                    _read_attr(request, "post_data", ""),
                    max_chars=self._max_body_chars,
                )
            )
        return data

    def _on_request(self, request: Any) -> None:
        self.record("browser.request", self._request_data(request))

    def _on_response(self, response: Any) -> None:
        request = _read_attr(response, "request", None)
        data = self._request_data(request) if request is not None else {}
        data.update(
            {
                "status": int(_read_attr(response, "status", 0) or 0),
                "status_text": str(_read_attr(response, "status_text", "") or ""),
            }
        )
        headers = _read_attr(response, "all_headers", {})
        if isinstance(headers, dict):
            data["response_headers"] = redact_browser_value(headers)
        if self._capture_bodies:
            raw_content_type = next(
                (
                    str(value)
                    for key, value in headers.items()
                    if str(key).casefold() == "content-type"
                ),
                "",
            ) if isinstance(headers, dict) else ""
            raw_content_length = next(
                (
                    str(value)
                    for key, value in headers.items()
                    if str(key).casefold() == "content-length"
                ),
                "",
            ) if isinstance(headers, dict) else ""
            try:
                content_length = int(raw_content_length or 0)
            except ValueError:
                content_length = 0
            if content_length > self._max_body_chars * 4:
                data["body_skipped"] = "content_length_exceeds_limit"
            elif raw_content_type and not _TEXT_CONTENT_TYPE.search(raw_content_type):
                data["body_skipped"] = "non_text_content_type"
            else:
                try:
                    data.update(
                        _body_for_log(
                            _read_attr(response, "text", ""),
                            max_chars=self._max_body_chars,
                        )
                    )
                except Exception as exc:
                    data["body_error"] = f"{type(exc).__name__}: {exc}"
        self.record("browser.response", data, "WARN" if data.get("status", 0) >= 400 else "INFO")

    def _on_request_failed(self, request: Any) -> None:
        data = self._request_data(request)
        data["failure"] = str(_read_attr(request, "failure", "") or "")
        self._request_ids.pop(id(request), None)
        self.record("browser.requestfailed", data, "WARN")

    def _on_request_finished(self, request: Any) -> None:
        data = self._request_data(request)
        started = self._request_ids.pop(id(request), ("", time.monotonic()))[1]
        data["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
        self.record("browser.requestfinished", data)

    def _on_console(self, message: Any) -> None:
        self.record(
            "browser.console",
            {
                "type": str(_read_attr(message, "type", "") or ""),
                "text": str(_read_attr(message, "text", "") or ""),
                "location": redact_browser_value(_read_attr(message, "location", {})),
            },
        )

    def _on_page_error(self, error: Any) -> None:
        self.record("browser.pageerror", {"error": f"{type(error).__name__}: {error}"}, "ERROR")

    def _on_frame_navigated(self, frame: Any) -> None:
        self.record(
            "browser.framenavigated",
            {"url": _redact_url(str(_read_attr(frame, "url", "") or ""))},
        )


__all__ = ["BrowserLogRecorder", "redact_browser_value"]
