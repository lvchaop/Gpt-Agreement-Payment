from __future__ import annotations

import gzip
import json
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthFlow,
    _resolve_auth_web_page_context,
)
from refactor_app.plugins.openai_auth_protocol.auth_web_runtime import (
    AuthWebRuntime,
    AuthWebRuntimeAssets,
    _parse_app_core_config,
    load_auth_web_runtime_assets,
)
from refactor_app.plugins.openai_auth_protocol.config import Config
from refactor_app.plugins.openai_auth_protocol.sentinel_quickjs import (
    create_sentinel_runtime_context,
)


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"{}",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self.content = body
        self.text = body.decode("utf-8", errors="replace")
        self.headers = headers or {"content-type": "application/json"}
        self.url = url
        self.reason = "OK"

    def json(self):
        return json.loads(self.text)


class _AssetSession:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.calls.append(url)
        return _Response(body=self.responses[url], url=url)


def _bootstrap() -> dict:
    return {
        "requestStartMillis": int(time.time() * 1_000) - 100,
        "track": "test",
        "immutableClientSessionMetadata": {
            "openai_client_id": "app_test",
            "app_name_enum": "chat",
            "auth_session_logging_id": "session-test",
        },
        "statsigClientInitData": {
            "identity": {
                "clientId": "app_test",
                "appNameEnum": "chat",
                "originator": "",
                "sessionLoggingId": "session-test",
                "deviceId": "device-test",
                "locale": "en-US",
                "country": "US",
                "userAgent": "Mozilla/5.0",
                "route": "/email-verification",
            },
            "bootstrap": "{}",
        },
    }


def test_load_assets_uses_html_entry_and_current_bundle_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_url = "https://auth.openai.com/email-verification"
    entry_url = "https://auth-cdn.oaistatic.com/assets/entry.client-current.js"
    statsig_url = "https://auth-cdn.oaistatic.com/assets/statsig-current.js"
    app_core_url = "https://auth-cdn.oaistatic.com/assets/app-core-current.js"
    datadog_url = "https://auth-cdn.oaistatic.com/assets/datadog-current.js"
    bootstrap = _bootstrap()
    html = (
        "<html><head><title>Email verification</title></head><body>"
        f'<script id="bootstrap-inert-script" type="application/json">'
        f"{json.dumps(bootstrap, separators=(',', ':'))}</script>"
        f'<script type="module">import "{entry_url}";'
        'window.__reactRouterRouteModules={"EMAIL_VERIFICATION":{}};</script>'
        "</body></html>"
    )
    entry = (
        'import "./statsig-current.js";import "./app-core-current.js";'
        'import "./datadog-current.js";' + "x" * 600
    ).encode()
    app_core = (
        'rum.init({applicationId:"application-test",clientToken:"token-test",'
        'site:"datadoghq.com",service:"login-web",env:"prod",version:"version-test",'
        "sessionSampleRate:100,sessionReplaySampleRate:1});"
        'const key="client-test";const api="https://ab.chatgpt.com/v1";'
        'const rumPath="/awe/api/v2/rum";' + "x" * 600
    ).encode()
    session = _AssetSession(
        {
            entry_url: entry,
            statsig_url: ("StatsigClient" + "x" * 600).encode(),
            app_core_url: app_core,
            datadog_url: ("startDurationVital setGlobalContext" + "x" * 600).encode(),
        }
    )
    monkeypatch.setenv("AUTH_WEB_RUNTIME_CACHE_DIR", str(tmp_path))

    assets = load_auth_web_runtime_assets(session, html_text=html, page_url=page_url)

    assert assets.entry_url == entry_url
    assert assets.statsig_url == statsig_url
    assert assets.app_core_url == app_core_url
    assert assets.datadog_url == datadog_url
    assert assets.route_id == "EMAIL_VERIFICATION"
    assert assets.auth_session_logging_id == "session-test"
    assert assets.statsig_log_event_url == "https://chatgpt.com/ces/v1/rgstr"
    assert assets.statsig_path.read_bytes() == session.responses[statsig_url]
    assert assets.datadog_path.read_bytes() == session.responses[datadog_url]
    assert session.calls == [entry_url, statsig_url, app_core_url, datadog_url]


class _RawSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.cookies = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Response(url=url)


class _RuntimeStub:
    def __init__(self) -> None:
        self.is_ready = True
        self.stages: list[dict] = []
        self.requests: list[tuple[str, str, dict]] = []
        self.navigations: list[dict] = []
        self.closed = False
        self.next_response = _Response()

    def record_stage(self, name: str, **kwargs) -> None:
        self.stages.append({"name": name, **kwargs})

    def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        self.next_response.url = url
        return self.next_response

    def navigate(self, **kwargs) -> bool:
        changed = not self.navigations or self.navigations[-1] != kwargs
        self.navigations.append(dict(kwargs))
        return changed

    def close(self) -> None:
        self.closed = True
        self.is_ready = False


def test_auth_flow_routes_only_auth_domain_through_sdk_runtime() -> None:
    flow = AuthFlow(Config())
    raw_session = _RawSession()
    flow.session.raw_session = raw_session
    runtime = _RuntimeStub()
    flow._auth_web_runtime = runtime
    flow._auth_web_runtime_page_url = "https://auth.openai.com/email-verification"
    auth_headers = flow._common_headers("https://auth.openai.com/email-verification")

    auth_response = flow.session.post(
        "https://auth.openai.com/api/accounts/email-otp/validate",
        headers=auth_headers,
        json={"code": "123456"},
        timeout=30,
    )
    direct_response = flow.session.get("https://chatgpt.com/api/auth/session", timeout=30)
    flow.close()

    assert auth_response.status_code == 200
    assert direct_response.status_code == 200
    assert len(runtime.requests) == 1
    assert runtime.requests[0][1].endswith("/api/accounts/email-otp/validate")
    assert runtime.stages[0]["phase"] == "post:/api/accounts/email-otp/validate"
    assert runtime.navigations[-1] == {
        "page_url": "https://auth.openai.com/email-verification",
        "page_title": "Email Verification",
        "route_id": "EMAIL_VERIFICATION",
    }
    assert raw_session.calls == [("GET", "https://chatgpt.com/api/auth/session", {"timeout": 30})]
    assert runtime.closed is True
    assert not {
        "traceparent",
        "tracestate",
        "x-datadog-origin",
        "x-datadog-parent-id",
        "x-datadog-sampling-priority",
        "x-datadog-trace-id",
    }.intersection({name.lower() for name in auth_headers})


def test_auth_flow_switches_runtime_view_from_auth_step_response() -> None:
    flow = AuthFlow(Config())
    runtime = _RuntimeStub()
    runtime.next_response = _Response(
        body=json.dumps(
            {
                "continue_url": "https://auth.openai.com/create-account/password",
                "page": {"type": "create_account_password"},
            }
        ).encode()
    )
    flow._auth_web_runtime = runtime
    flow._auth_web_runtime_page_url = "https://auth.openai.com/create-account"

    flow.session.post(
        "https://auth.openai.com/api/accounts/authorize/continue",
        headers={"Referer": "https://auth.openai.com/create-account"},
        json={"username": "account@example.test"},
    )
    flow.close()

    assert runtime.navigations == [
        {
            "page_url": "https://auth.openai.com/create-account",
            "page_title": "Create Account",
            "route_id": "CREATE_ACCOUNT",
        },
        {
            "page_url": "https://auth.openai.com/create-account/password",
            "page_title": "Create Account Password",
            "route_id": "CREATE_ACCOUNT_PASSWORD",
        },
    ]


def test_auth_flow_document_navigation_uses_browser_navigation_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = AuthFlow(Config())
    raw_session = _RawSession()
    flow.session.raw_session = raw_session
    started: list[dict] = []
    monkeypatch.setattr(
        flow,
        "_start_auth_web_runtime",
        lambda **kwargs: started.append(kwargs),
    )

    response = flow._load_auth_web_document(
        "https://auth.openai.com/create-account/password",
        referer="https://auth.openai.com/create-account",
        trace_step="test_document_navigation",
    )

    assert response.status_code == 200
    assert len(raw_session.calls) == 1
    method, url, kwargs = raw_session.calls[0]
    assert method == "GET"
    assert url == "https://auth.openai.com/create-account/password"
    assert kwargs["headers"]["Sec-Fetch-Dest"] == "document"
    assert kwargs["headers"]["Sec-Fetch-Mode"] == "navigate"
    assert kwargs["headers"]["Sec-Fetch-Site"] == "same-origin"
    assert kwargs["headers"]["Sec-Fetch-User"] == "?1"
    assert kwargs["allow_redirects"] is True
    assert started == [
        {
            "html_text": "{}",
            "page_url": "https://auth.openai.com/create-account/password",
        }
    ]


def test_telemetry_transport_times_out_before_node_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RawSession()
    runtime = AuthWebRuntime.__new__(AuthWebRuntime)
    runtime.session = session
    runtime.assets = SimpleNamespace(
        bootstrap={
            "statsigClientInitData": {
                "identity": {
                    "locale": "en-US",
                    "userAgent": "Mozilla/5.0",
                }
            }
        }
    )
    runtime._page_url = "https://auth.openai.com/create-account/password"
    runtime._business_responses = {}
    runtime._business_errors = {}
    runtime._telemetry_transport_counts = Counter()
    sent: list[dict] = []
    runtime._send = sent.append
    monkeypatch.setenv("AUTH_WEB_TELEMETRY_HTTP_TIMEOUT_SECONDS", "12")

    runtime._handle_transport_request(
        {
            "transportId": "transport-rum",
            "method": "POST",
            "url": "https://auth.openai.com/awe/api/v2/rum?source=browser",
            "headers": {"content-type": "text/plain"},
            "bodyBase64": "",
            "timeoutMs": 60_000,
            "allowRedirects": True,
        }
    )

    assert session.calls[0][2]["timeout"] == 12
    assert sent[0]["type"] == "transport_response"
    assert sent[0]["transportId"] == "transport-rum"


@pytest.mark.parametrize(
    ("page_type", "page_url", "expected"),
    [
        (
            "email_otp_verification",
            "",
            (
                "https://auth.openai.com/email-verification",
                "Email Verification",
                "EMAIL_VERIFICATION",
            ),
        ),
        (
            "about_you",
            "https://auth.openai.com/about-you",
            ("https://auth.openai.com/about-you", "About You", "ABOUT_YOU"),
        ),
        ("external_url", "https://chatgpt.com/callback", None),
    ],
)
def test_resolve_auth_web_page_context(page_type, page_url, expected) -> None:
    assert _resolve_auth_web_page_context(page_type=page_type, page_url=page_url) == expected


_CAPTURE_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "har-js" / "reg-20260707"
_STATSIG_BUNDLE = _CAPTURE_ROOT / "0363_84a0a4615f_statsig-I35B3fDz.js"
_APP_CORE_BUNDLE = _CAPTURE_ROOT / "0364_39c9c4fd85_app-core-ChBiFVd3.js"
_DATADOG_BUNDLE = _CAPTURE_ROOT / "0372_26906080d3_datadog-BTgRrIvw.js"


def _rum_events(calls: list[tuple[str, str, dict]]) -> list[dict]:
    events: list[dict] = []
    for _method, url, kwargs in calls:
        if "/awe/api/v2/rum" not in url:
            continue
        headers = {str(name).lower(): str(value) for name, value in kwargs["headers"].items()}
        body = kwargs.get("data") or b""
        if headers.get("content-encoding") == "gzip":
            body = gzip.decompress(body)
        for line in body.decode("utf-8").splitlines():
            events.append(json.loads(line))
    return events


def _statsig_events(calls: list[tuple[str, str, dict]]) -> list[dict]:
    events: list[dict] = []
    for _method, url, kwargs in calls:
        if "/ces/v1/rgstr" not in url:
            continue
        headers = {str(name).lower(): str(value) for name, value in kwargs["headers"].items()}
        body = kwargs.get("data") or b""
        if isinstance(body, str):
            body = body.encode()
        if headers.get("content-encoding") == "gzip":
            body = gzip.decompress(body)
        if not body:
            continue
        payload = json.loads(body.decode("utf-8"))
        events.extend(payload.get("events") or [])
    return events


@pytest.mark.skipif(
    not all(path.exists() for path in (_STATSIG_BUNDLE, _APP_CORE_BUNDLE, _DATADOG_BUNDLE)),
    reason="captured Auth Web SDK bundles are not present",
)
def test_real_sdk_injects_trace_generates_rum_and_closes_node() -> None:
    config, statsig_key, statsig_api, statsig_log_event_url = _parse_app_core_config(
        _APP_CORE_BUNDLE.read_text(encoding="utf-8")
    )
    bootstrap = _bootstrap()
    session = _RawSession()
    session.cookies = [
        SimpleNamespace(
            name="oai-did",
            value="device-test",
            domain="auth.openai.com",
        )
    ]
    assets = AuthWebRuntimeAssets(
        bootstrap_json=json.dumps(bootstrap, separators=(",", ":")),
        bootstrap=bootstrap,
        entry_url="",
        statsig_url="",
        app_core_url="",
        datadog_url="",
        statsig_path=_STATSIG_BUNDLE,
        datadog_path=_DATADOG_BUNDLE,
        datadog_config=config,
        statsig_client_key=statsig_key,
        statsig_api_url=statsig_api,
        statsig_log_event_url=statsig_log_event_url,
        page_title="Email Verification",
        route_id="EMAIL_VERIFICATION",
        page_url="https://auth.openai.com/email-verification",
    )
    runtime = AuthWebRuntime(session, assets, create_sentinel_runtime_context("US"))
    process = runtime._process
    assert process is not None

    try:
        assert (
            runtime.navigate(
                page_url="https://auth.openai.com/create-account/password",
                page_title="Create Account Password",
                route_id="CREATE_ACCOUNT_PASSWORD",
            )
            is True
        )
        register_response = runtime.request(
            "POST",
            "https://auth.openai.com/api/accounts/user/register",
            headers={
                "Content-Type": "application/json",
                "x-access-flow-invocation-id": "register-invocation-test",
            },
            json={"username": "new@example.test", "password": "candidate-password"},
            timeout=5,
            allow_redirects=False,
        )
        assert (
            runtime.navigate(
                page_url="https://auth.openai.com/email-verification",
                page_title="Email Verification",
                route_id="EMAIL_VERIFICATION",
            )
            is True
        )
        runtime.record_stage(
            "submit otp",
            phase="otp",
            page_url=assets.page_url,
        )
        response = runtime.request(
            "POST",
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers={"Content-Type": "application/json"},
            json={"code": "123456"},
            timeout=5,
            allow_redirects=False,
        )
        assert (
            runtime.navigate(
                page_url="https://auth.openai.com/about-you",
                page_title="About You",
                route_id="ABOUT_YOU",
            )
            is True
        )
        create_response = runtime.request(
            "POST",
            "https://auth.openai.com/api/accounts/create_account",
            headers={
                "Content-Type": "application/json",
                "x-access-flow-invocation-id": "create-invocation-test",
            },
            json={"name": "Test User", "birthdate": "1990-01-01"},
            timeout=5,
            allow_redirects=False,
        )
        runtime.record_sentinel_timing("request_start")
        runtime.record_sentinel_timing("ready")
        runtime.flush()
        auth_call = next(call for call in session.calls if call[1].endswith("/validate"))
        auth_headers = {name.lower() for name in auth_call[2]["headers"]}
        events = _rum_events(session.calls)
        statsig_events = _statsig_events(session.calls)
        statsig_event_names = {event.get("eventName") for event in statsig_events}

        assert response is not None and response.status_code == 200
        assert register_response is not None and register_response.status_code == 200
        assert create_response is not None and create_response.status_code == 200
        assert runtime.runtime_info["datadogSessionReady"] is True
        assert runtime.runtime_info["statsigSessionReady"] is True
        assert runtime.runtime_info["intlInitialized"] is True
        assert runtime.page_url == "https://auth.openai.com/about-you"
        assert auth_call[2]["allow_redirects"] is False
        assert {
            "traceparent",
            "tracestate",
            "x-datadog-origin",
            "x-datadog-parent-id",
            "x-datadog-sampling-priority",
            "x-datadog-trace-id",
        }.issubset(auth_headers)
        assert (
            auth_call[2]["headers"]["Referer"]
            == "https://auth.openai.com/email-verification"
        )
        assert "action" in {event.get("type") for event in events}
        assert any(
            event.get("view", {}).get("name") == "About You"
            and event.get("context", {}).get("routeId") == "ABOUT_YOU"
            for event in events
        )
        observed_routes = {
            event.get("context", {}).get("routeId")
            for event in events
            if event.get("type") == "view"
        }
        assert {
            "CREATE_ACCOUNT_PASSWORD",
            "EMAIL_VERIFICATION",
            "ABOUT_YOU",
        }.issubset(observed_routes)
        assert any(
            event.get("type") == "vital" and event.get("vital", {}).get("name") == "initialize_intl"
            for event in events
        )
        assert any(
            event.get("type") == "resource"
            and event.get("resource", {})
            .get("url", "")
            .endswith("/api/accounts/email-otp/validate")
            for event in events
        )
        command = " ".join(str(part) for part in process.args)
        statsig_urls = [url for _method, url, _kwargs in session.calls if "rgstr" in url]
        assert any(url.startswith("https://chatgpt.com/ces/v1/rgstr") for url in statsig_urls)
        assert not any(url.startswith("https://ab.chatgpt.com/v1/rgstr") for url in statsig_urls)
        assert any("https://ab.chatgpt.com/v1/initialize" in call[1] for call in session.calls)
        assert {
            "bootstrap_parse_duration_ms",
            "statsig_initialize_duration_ms",
            "client_entry_duration_ms",
            "login_web_register_user",
            "login_web_validate_otp",
            "login_web_onboarding_user_info_complete",
            "login_web_sentinel_sdk_request_start_ms",
            "login_web_sentinel_sdk_ready_ms",
            "Login Web: Page View: Email Verification",
            "Login Web: Page View: About You",
            "__protobuf_structured_event__",
        }.issubset(statsig_event_names)
        assert "auto_capture::page_view" not in statsig_event_names
        assert "auto_capture::session_start" not in statsig_event_names
        structured_types = {
            event.get("metadata", {}).get("eventParams", {}).get("@type", "").rsplit(".", 1)[-1]
            for event in statsig_events
            if event.get("eventName") == "__protobuf_structured_event__"
        }
        assert {
            "ChatgptUserIdentified",
            "AccessFlowPageLoad",
            "AccessFlowUserAction",
            "AccessFlowApiInvocation",
        }.issubset(structured_types)
        assert "auth_web_runtime_runner.js" in command
        assert all(name not in command.lower() for name in ("camoufox", "playwright", "chrome"))
    finally:
        runtime.close()

    assert runtime.is_ready is False
    assert process.poll() == 0
