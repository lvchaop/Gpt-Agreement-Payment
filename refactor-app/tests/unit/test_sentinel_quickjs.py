from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests.cookies import RequestsCookieJar

from refactor_app.config.browser_fingerprint import browser_fingerprint_for
from refactor_app.plugins.openai_auth_protocol import sentinel, sentinel_quickjs
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow
from refactor_app.plugins.openai_auth_protocol.config import Config

FULL_SDK = (
    b"var SentinelSDK="
    + b"getRequirementsToken getEnforcementToken"
    + b"x" * sentinel_quickjs.MIN_SENTINEL_SDK_BYTES
)


@dataclass
class _Response:
    content: bytes
    status_code: int = 200
    text: str = ""


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.urls: list[str] = []
        self.requests: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.urls.append(url)
        self.requests.append(kwargs)
        return self.response


def _use_temp_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(sentinel_quickjs.tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / "openai-sentinel-demo" / sentinel_quickjs.SENTINEL_VERSION / "sdk.js"


def _decode_requirements_config(token: str) -> list[object]:
    assert token.startswith("gAAAAAC")
    assert token.endswith("~S")
    encoded = token[len("gAAAAAC") : -len("~S")]
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def test_sdk_url_targets_versioned_bundle() -> None:
    assert sentinel_quickjs.SENTINEL_SDK_URL == (
        "https://sentinel.openai.com/sentinel/20260219f9f6/sdk.js"
    )


def test_node_binary_uses_nvm_when_worker_path_has_no_node(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    node = tmp_path / "versions" / "node" / "v24.8.0" / "bin" / "node"
    node.parent.mkdir(parents=True)
    node.write_text("#!/bin/sh\n")
    node.chmod(0o755)
    monkeypatch.delenv("OPENAI_SENTINEL_NODE_PATH", raising=False)
    monkeypatch.delenv("NODE_EXECUTABLE", raising=False)
    monkeypatch.setenv("NVM_DIR", str(tmp_path))
    monkeypatch.setattr(sentinel_quickjs.shutil, "which", lambda _name: None)

    assert sentinel_quickjs._resolve_node_binary() == str(node)


def test_loader_cache_is_replaced_with_full_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = _use_temp_cache(monkeypatch, tmp_path)
    sdk_file.parent.mkdir(parents=True)
    sdk_file.write_bytes(b"window.__sentinel_token_pending = [];")
    session = _Session(_Response(content=FULL_SDK))
    context = sentinel_quickjs.create_sentinel_runtime_context("JP")

    result = sentinel_quickjs._ensure_sdk_file(session, 30_000, context)

    assert result == sdk_file
    assert result.read_bytes() == FULL_SDK
    assert session.urls == [sentinel_quickjs.SENTINEL_SDK_URL]
    assert session.requests[0]["headers"]["accept-language"] == (
        "ja-JP,ja;q=0.9,en;q=0.5"
    )


def test_complete_sdk_cache_is_reused_without_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = _use_temp_cache(monkeypatch, tmp_path)
    sdk_file.parent.mkdir(parents=True)
    sdk_file.write_bytes(FULL_SDK)
    session = _Session(_Response(content=b"unused"))
    context = sentinel_quickjs.create_sentinel_runtime_context("US")

    result = sentinel_quickjs._ensure_sdk_file(session, 30_000, context)

    assert result == sdk_file
    assert session.urls == []


def test_downloaded_loader_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = _use_temp_cache(monkeypatch, tmp_path)
    session = _Session(_Response(content=b"window.SentinelSDK = window.SentinelSDK || {};"))
    context = sentinel_quickjs.create_sentinel_runtime_context("US")

    with pytest.raises(RuntimeError, match="incomplete"):
        sentinel_quickjs._ensure_sdk_file(session, 30_000, context)

    assert not sdk_file.exists()


def test_runtime_context_is_stable_and_country_aware() -> None:
    session = SimpleNamespace()

    first = sentinel_quickjs.bind_sentinel_runtime_context(session, country_code="JP")
    second = sentinel_quickjs.bind_sentinel_runtime_context(session, country_code="US")

    assert second is first
    assert first.country_code == "JP"
    assert first.browser_profile["navigator_language"] == "ja-JP"
    assert first.browser_profile["timezone_iana"] == "Asia/Tokyo"
    assert first.react_resources_key.removeprefix("__reactResources$") == (
        first.react_container_key.removeprefix("__reactContainer$")
    )
    restored = sentinel_quickjs.SentinelRuntimeContext.from_dict(first.to_dict())
    assert restored == first


def test_runtime_context_uses_supplied_complete_browser_fingerprint() -> None:
    fingerprint = browser_fingerprint_for("chrome145", os_profile="windows")
    context = sentinel_quickjs.create_sentinel_runtime_context(
        "US",
        browser_fingerprint=fingerprint,
    )
    profile = context.browser_profile

    assert profile["user_agent"] == fingerprint.user_agent
    assert profile["navigator_platform"] == "Win32"
    assert profile["user_agent_data_platform"] == "Windows"
    assert profile["sec_ch_ua"] == fingerprint.sec_ch_ua
    assert profile["sec_ch_ua_platform"] == '"Windows"'
    assert profile["chrome_major"] == "145"
    assert profile["sec_ch_ua_arch"] == '"x86"'


def test_runtime_context_requires_verified_proxy_country() -> None:
    with pytest.raises(ValueError, match="ISO alpha-2"):
        sentinel_quickjs.create_sentinel_runtime_context("")
    with pytest.raises(ValueError, match="no IANA timezone"):
        sentinel_quickjs.create_sentinel_runtime_context("ZZ")
    with pytest.raises(ValueError, match="verified proxy egress country"):
        sentinel_quickjs.get_sentinel_runtime_context(SimpleNamespace())


def test_runtime_context_rejects_incomplete_proxy_locale_snapshot() -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("US")
    payload = context.to_dict()
    payload["browser_profile"].pop("timezone_iana")

    with pytest.raises(ValueError, match="runtime context is incomplete"):
        sentinel_quickjs.SentinelRuntimeContext.from_dict(payload)


def test_requirements_token_uses_stable_runtime_context() -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("US")

    first = _decode_requirements_config(sentinel_quickjs._generate_requirements_token(context))
    second = _decode_requirements_config(sentinel_quickjs._generate_requirements_token(context))

    assert first[0] == 2969
    assert first[4] == sentinel_quickjs.DEFAULT_UA
    assert first[7:9] == ["en-US", "en-US"]
    assert first[14] == second[14] == context.sentinel_sid
    assert first[16] == second[16] == 12


def test_synthetic_requirements_token_uses_bound_proxy_locale() -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("JP")
    generator = sentinel.SentinelTokenGenerator(
        device_id="device-id",
        runtime_context=context,
    )

    token = generator.generate_requirements_token()
    config = json.loads(base64.b64decode(token.removeprefix("gAAAAAC")).decode("utf-8"))

    assert "GMT+0900" in config[1]
    assert config[7:9] == ["ja-JP", "ja-JP"]


def test_real_sdk_flow_passes_page_cookie_and_context_to_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session = SimpleNamespace(cookies=RequestsCookieJar())
    session.cookies.set("auth-session", "session-value", domain="auth.openai.com", path="/")
    context = sentinel_quickjs.bind_sentinel_runtime_context(session, country_code="JP")
    sdk_file = tmp_path / "sdk.js"
    sdk_file.write_bytes(FULL_SDK)
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(sentinel_quickjs, "_ensure_sdk_file", lambda *_: sdk_file)

    def fake_fetch(_session: object, **kwargs: object) -> dict[str, object]:
        captured.append({"challenge": kwargs})
        return {"token": "challenge-token", "proofofwork": {"required": False}}

    def fake_runner(**kwargs: object) -> str:
        captured.append({"runner": kwargs})
        return json.dumps(
            {
                "p": "real-sdk-proof",
                "t": "turnstile-token",
                "so": "session-observer-token",
                "c": "challenge-token",
                "id": "device-id",
                "flow": "oauth_create_account",
            }
        )

    monkeypatch.setattr(sentinel_quickjs, "_fetch_sentinel_challenge", fake_fetch)
    monkeypatch.setattr(sentinel_quickjs, "_run_sentinel_runner", fake_runner)

    token, so_token = sentinel_quickjs.get_sentinel_tokens_via_quickjs(
        session,
        device_id="device-id",
        flow="oauth_create_account",
    )

    assert json.loads(token)["p"] == "real-sdk-proof"
    assert json.loads(so_token)["so"] == "session-observer-token"
    challenge = captured[0]["challenge"]
    runner = captured[1]["runner"]
    assert isinstance(challenge, dict)
    assert isinstance(runner, dict)
    assert challenge["context"] is context
    assert _decode_requirements_config(str(challenge["request_p"]))[14] == context.sentinel_sid
    assert runner["context"] is context
    assert runner["page_url"] == "https://auth.openai.com/about-you"
    assert "auth-session=session-value" in str(runner["cookie"])
    assert "oai-did=device-id" in str(runner["cookie"])
    assert session.cookies.get("oai-did", domain="sentinel.openai.com") == "device-id"


def test_checkout_flow_passes_explicit_page_url_and_chatgpt_cookies_to_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session = SimpleNamespace(cookies=RequestsCookieJar())
    session.cookies.set("auth-session", "auth-value", domain="auth.openai.com", path="/")
    session.cookies.set("chat-session", "chat-value", domain="chatgpt.com", path="/")
    sentinel_quickjs.bind_sentinel_runtime_context(session, country_code="US")
    sdk_file = tmp_path / "sdk.js"
    sdk_file.write_bytes(FULL_SDK)
    captured: dict[str, object] = {}

    monkeypatch.setattr(sentinel_quickjs, "_ensure_sdk_file", lambda *_: sdk_file)
    monkeypatch.setattr(
        sentinel_quickjs,
        "_fetch_sentinel_challenge",
        lambda *_args, **_kwargs: {
            "token": "challenge-token",
            "proofofwork": {"required": False},
        },
    )

    def fake_runner(**kwargs: object) -> str:
        captured.update(kwargs)
        return json.dumps(
            {
                "p": "real-sdk-proof",
                "t": "",
                "c": "challenge-token",
                "id": "device-id",
                "flow": "checkout_session_approval",
            }
        )

    monkeypatch.setattr(sentinel_quickjs, "_run_sentinel_runner", fake_runner)
    checkout_url = "https://chatgpt.com/checkout/openai/cs_live_example"

    sentinel_quickjs.get_sentinel_tokens_via_quickjs(
        session,
        device_id="device-id",
        flow="checkout_session_approval",
        page_url=checkout_url,
    )

    assert captured["page_url"] == checkout_url
    assert "chat-session=chat-value" in str(captured["cookie"])
    assert "auth-session=auth-value" not in str(captured["cookie"])
    assert "oai-did=device-id" in str(captured["cookie"])


def test_checkout_flow_requires_explicit_page_url() -> None:
    with pytest.raises(ValueError, match="page_url is required"):
        sentinel_quickjs.get_sentinel_tokens_via_quickjs(
            SimpleNamespace(cookies=RequestsCookieJar()),
            device_id="device-id",
            flow="checkout_session_approval",
        )
    with pytest.raises(ValueError, match="page_url is required"):
        sentinel.get_sentinel_tokens(
            SimpleNamespace(),
            "device-id",
            flow="checkout_session_approval",
        )


def test_public_sentinel_api_forwards_checkout_page_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_quickjs(*_args: object, **kwargs: object) -> tuple[str, str]:
        captured.update(kwargs)
        return "sentinel-token", ""

    monkeypatch.setattr(sentinel_quickjs, "get_sentinel_tokens_via_quickjs", fake_quickjs)
    checkout_url = "https://chatgpt.com/checkout/openai/cs_live_example"

    assert sentinel.get_sentinel_tokens(
        SimpleNamespace(),
        "device-id",
        flow="checkout_session_approval",
        page_url=checkout_url,
    ) == ("sentinel-token", "")
    assert captured["page_url"] == checkout_url


def test_lifecycle_runner_executes_init_before_token_in_one_sdk_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = tmp_path / "sdk.js"
    sdk_file.write_text(
        """
var SentinelSDK = (() => {
  let iframe = null;
  let sequence = 0;
  const waiters = new Map();
  window.addEventListener("message", (event) => {
    const message = event.data || {};
    if (message.type !== "response") return;
    const waiter = waiters.get(message.requestId);
    if (!waiter) return;
    waiters.delete(message.requestId);
    if (message.error) waiter.reject(new Error(message.error));
    else waiter.resolve(message.result);
  });
  function request(type, flow, proof) {
    if (!iframe) {
      iframe = document.createElement("iframe");
      document.body.appendChild(iframe);
    }
    const requestId = `fake-${++sequence}`;
    return new Promise((resolve, reject) => {
      waiters.set(requestId, { resolve, reject });
      iframe.contentWindow.postMessage({ type, flow, requestId, p: proof }, "https://sentinel.openai.com");
    });
  }
  return {
    async init(flow) {
      await request("init", flow, "proof-init");
    },
    async token(flow) {
      const result = await request("token", flow, "proof-token");
      return JSON.stringify({
        p: "enforcement-proof",
        t: "",
        c: result.cachedChatReq.token,
        id: "device-id",
        flow,
      });
    },
    __codexBindProof() {},
    async __codexTurnstileToken() { return ""; },
    async __codexSessionObserverToken() { return ""; },
  };
})();
// getRequirementsToken getEnforcementToken
""",
        encoding="utf-8",
    )
    session = SimpleNamespace(cookies=RequestsCookieJar())
    context = sentinel_quickjs.bind_sentinel_runtime_context(session, country_code="JP")
    observed_proofs: list[str] = []

    def fake_fetch(_session: object, **kwargs: object) -> dict[str, object]:
        proof = str(kwargs["request_p"])
        observed_proofs.append(proof)
        return {
            "token": f"challenge-{proof}",
            "proofofwork": {"required": False},
        }

    monkeypatch.setattr(sentinel_quickjs, "_fetch_sentinel_challenge", fake_fetch)

    token = sentinel_quickjs._run_sentinel_lifecycle_runner(
        session=session,
        sdk_file=sdk_file,
        device_id="device-id",
        flow="username_password_create",
        page_url="https://auth.openai.com/create-account/password",
        cookie="oai-did=device-id",
        context=context,
        timeout_ms=5_000,
    )

    assert observed_proofs == ["proof-init", "proof-token"]
    assert json.loads(token) == {
        "p": "enforcement-proof",
        "t": "",
        "c": "challenge-proof-token",
        "id": "device-id",
        "flow": "username_password_create",
    }


def test_runner_command_contains_complete_browser_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("JP")
    sdk_file = tmp_path / "sdk.js"
    sdk_file.write_bytes(FULL_SDK)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "p": "proof",
                    "t": "turnstile",
                    "c": "challenge-token",
                    "id": "device-id",
                    "flow": "authorize_continue",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(sentinel_quickjs.subprocess, "run", fake_run)
    token = sentinel_quickjs._run_sentinel_runner(
        challenge={"token": "challenge-token"},
        sdk_file=sdk_file,
        device_id="device-id",
        flow="authorize_continue",
        page_url="https://auth.openai.com/email-verification",
        cookie="oai-did=device-id; auth-session=value",
        context=context,
        timeout_ms=45_000,
        request_p="requirements-proof",
    )

    command = captured["command"]
    kwargs = captured["kwargs"]
    assert isinstance(command, list)
    assert isinstance(kwargs, dict)
    values = {command[index]: command[index + 1] for index in range(2, len(command), 2)}
    assert values["--page-url"] == "https://auth.openai.com/email-verification"
    assert values["--cookie"] == "oai-did=device-id; auth-session=value"
    assert values["--sentinel-sid"] == context.sentinel_sid
    assert values["--react-listening-key"] == context.react_listening_key
    assert values["--react-container-key"] == context.react_container_key
    assert values["--react-resources-key"] == context.react_resources_key
    assert values["--request-p"] == "requirements-proof"
    assert values["--time-zone"] == "Asia/Tokyo"
    assert values["--language"] == "ja-JP"
    assert values["--width"] == "1800"
    assert values["--height"] == "1169"
    assert values["--chrome-major"] == str(sentinel_quickjs.BROWSER_FINGERPRINT.major_version)
    assert kwargs["env"]["TZ"] == "Asia/Tokyo"
    assert json.loads(token)["p"] == "proof"


def test_runner_rejects_missing_required_session_observer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("US")
    sdk_file = tmp_path / "sdk.js"
    sdk_file.write_bytes(FULL_SDK)

    monkeypatch.setattr(
        sentinel_quickjs.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "p": "proof",
                    "t": "turnstile",
                    "c": "challenge-token",
                    "id": "device-id",
                    "flow": "authorize_continue",
                }
            ),
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="missing required Session Observer"):
        sentinel_quickjs._run_sentinel_runner(
            challenge={
                "token": "challenge-token",
                "so": {"required": True, "snapshot_dx": "snapshot"},
            },
            sdk_file=sdk_file,
            device_id="device-id",
            flow="authorize_continue",
            page_url="https://auth.openai.com/email-verification",
            cookie="oai-did=device-id",
            context=context,
            timeout_ms=45_000,
        )


def test_auth_flow_snapshot_preserves_sentinel_runtime_context() -> None:
    config = Config()
    config.proxy_meta = {"register": {"country_code": "JP"}}
    original = AuthFlow(config)
    original._last_auth_session_logging_id = "session-logging-id"
    original._last_auth_oauth_init_url = "https://auth.openai.com/email-verification"
    original._auth_web_runtime_page_url = "https://auth.openai.com/email-verification"
    snapshot = original.export_protocol_snapshot()
    restored = AuthFlow(config)

    restored.restore_protocol_snapshot(snapshot)

    assert restored._sentinel_runtime_context == original._sentinel_runtime_context
    assert restored._sentinel_runtime_context.browser_profile["timezone_iana"] == "Asia/Tokyo"
    assert restored._last_auth_session_logging_id == "session-logging-id"
    assert restored._last_auth_oauth_init_url == "https://auth.openai.com/email-verification"
    assert restored._auth_web_runtime_page_url == "https://auth.openai.com/email-verification"
    original.close()
    restored.close()


def test_real_sdk_failure_does_not_enter_synthetic_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_SENTINEL_DISABLE_QUICKJS", raising=False)
    monkeypatch.delenv("OPENAI_SENTINEL_ALLOW_SYNTHETIC_FALLBACK", raising=False)
    monkeypatch.setattr(
        sentinel_quickjs,
        "get_sentinel_tokens_via_quickjs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("runner failed")),
    )
    monkeypatch.setattr(
        sentinel,
        "build_sentinel_tokens",
        lambda *_args, **_kwargs: pytest.fail("synthetic path must not run"),
    )

    with pytest.raises(RuntimeError, match="Sentinel real SDK failed: runner failed"):
        sentinel.get_sentinel_tokens(SimpleNamespace(), "device-id")
