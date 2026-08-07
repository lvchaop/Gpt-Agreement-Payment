from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests.cookies import RequestsCookieJar

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

    def get(self, url: str, **_: object) -> _Response:
        self.urls.append(url)
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

    result = sentinel_quickjs._ensure_sdk_file(session, 30_000)

    assert result == sdk_file
    assert result.read_bytes() == FULL_SDK
    assert session.urls == [sentinel_quickjs.SENTINEL_SDK_URL]


def test_complete_sdk_cache_is_reused_without_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = _use_temp_cache(monkeypatch, tmp_path)
    sdk_file.parent.mkdir(parents=True)
    sdk_file.write_bytes(FULL_SDK)
    session = _Session(_Response(content=b"unused"))

    result = sentinel_quickjs._ensure_sdk_file(session, 30_000)

    assert result == sdk_file
    assert session.urls == []


def test_downloaded_loader_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sdk_file = _use_temp_cache(monkeypatch, tmp_path)
    session = _Session(_Response(content=b"window.SentinelSDK = window.SentinelSDK || {};"))

    with pytest.raises(RuntimeError, match="incomplete"):
        sentinel_quickjs._ensure_sdk_file(session, 30_000)

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


def test_requirements_token_uses_stable_runtime_context() -> None:
    context = sentinel_quickjs.create_sentinel_runtime_context("US")

    first = _decode_requirements_config(sentinel_quickjs._generate_requirements_token(context))
    second = _decode_requirements_config(sentinel_quickjs._generate_requirements_token(context))

    assert first[0] == 2730
    assert first[4] == sentinel_quickjs.DEFAULT_UA
    assert first[7:9] == ["en-US", "en-US"]
    assert first[14] == second[14] == context.sentinel_sid
    assert first[16] == second[16] == 6


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
    assert values["--width"] == "1680"
    assert values["--height"] == "1050"
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
