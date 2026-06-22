from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from curl_cffi import requests as curl_requests

from refactor_app.plugins.contracts import OAuthTokenSet, TokenClaims

DEFAULT_AUTH_BASE_URL = "https://auth.openai.com"
DEFAULT_CHATGPT_BASE_URL = "https://chatgpt.com"
CHATGPT_AUTH_CLAIM = "https://api.openai.com/auth"
DEFAULT_CODEX_HEARTBEAT_MODEL = "gpt-5.5"
CODEX_RESPONSES_PATH = "/backend-api/codex/responses"
CODEX_INSTRUCTIONS_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "openai_codex_instructions.txt"
)


class OpenAIChatGPTClientError(RuntimeError):
    pass


class WorkspaceMismatchError(OpenAIChatGPTClientError):
    def __init__(self, *, expected: str, actual: str) -> None:
        super().__init__(f"workspace mismatch: expected={expected} actual={actual}")
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class OpenAIChatGPTClientConfig:
    auth_base_url: str = DEFAULT_AUTH_BASE_URL
    chatgpt_base_url: str = DEFAULT_CHATGPT_BASE_URL
    timeout_s: float = 30.0
    probe_path_template: str = ""

    def validate(self) -> None:
        if not self.auth_base_url:
            raise OpenAIChatGPTClientError("auth_base_url is required")
        if not self.chatgpt_base_url:
            raise OpenAIChatGPTClientError("chatgpt_base_url is required")
        if self.timeout_s <= 0:
            raise OpenAIChatGPTClientError("timeout_s must be positive")


class OpenAIChatGPTClient:
    def __init__(
        self,
        config: OpenAIChatGPTClientConfig,
        *,
        auth_http_client: httpx.Client | None = None,
        chatgpt_http_client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._chatgpt_http_client_injected = chatgpt_http_client is not None
        self._auth_client = auth_http_client or httpx.Client(
            base_url=config.auth_base_url,
            timeout=config.timeout_s,
        )
        self._chatgpt_client = chatgpt_http_client or httpx.Client(
            base_url=config.chatgpt_base_url,
            timeout=config.timeout_s,
        )
        self._curl_sessions: dict[str, curl_requests.Session] = {}

    def refresh_workspace_token(
        self,
        *,
        refresh_token: str,
        external_workspace_id: str,
        client_id: str,
    ) -> OAuthTokenSet:
        if not refresh_token:
            raise OpenAIChatGPTClientError("refresh_token is required")
        if not external_workspace_id:
            raise OpenAIChatGPTClientError("external_workspace_id is required")
        if not client_id:
            raise OpenAIChatGPTClientError("client_id is required")

        response = self._auth_client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.is_error:
            raise OpenAIChatGPTClientError(
                f"oauth refresh failed: http_status={response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise OpenAIChatGPTClientError("oauth refresh response must be a JSON object")

        access_token = str(payload.get("access_token") or "")
        id_token = str(payload.get("id_token") or "")
        next_refresh_token = str(payload.get("refresh_token") or refresh_token)
        if not access_token:
            raise OpenAIChatGPTClientError("oauth refresh response missing access_token")

        claims = decode_access_token_claims(access_token)
        if claims.token_chatgpt_account_id != external_workspace_id:
            raise WorkspaceMismatchError(
                expected=external_workspace_id,
                actual=claims.token_chatgpt_account_id,
            )

        return OAuthTokenSet(
            access_token=access_token,
            id_token=id_token,
            refresh_token=next_refresh_token,
            expires_at=_expires_at(payload),
            claims=claims,
        )

    def decode_access_token(self, access_token: str) -> TokenClaims:
        return decode_access_token_claims(access_token)

    def invite_member(
        self,
        *,
        access_token: str,
        team_id: str,
        email: str,
        cookie_header: str = "",
        seat_type: str = "default",
    ) -> dict:
        response = self._chatgpt_post(
            f"/backend-api/accounts/{team_id}/invites",
            headers=_team_headers(
                access_token=access_token,
                team_id=team_id,
                referer="https://chatgpt.com/admin",
                cookie_header=cookie_header,
            ),
            json={
                "email_addresses": [email],
                "role": "standard-user",
                "seat_type": seat_type,
                "resend_emails": True,
            },
        )
        return _response_payload(response)

    def accept_invite(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        device_id: str = "",
    ) -> dict:
        response = self._chatgpt_post(
            f"/backend-api/accounts/{team_id}/invites/accept",
            headers=_accept_headers(access_token=access_token, device_id=device_id),
            data="",
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def probe_membership(self, *, access_token: str, team_id: str) -> dict:
        if not self._config.probe_path_template:
            raise OpenAIChatGPTClientError("probe_path_template is not configured")
        path = self._config.probe_path_template.format(team_id=team_id)
        response = self._chatgpt_get(
            path,
            headers=_team_headers(access_token=access_token, team_id=team_id),
        )
        return _response_payload(response)

    def heartbeat_codex_credential(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict:
        claims = decode_access_token_claims(access_token)
        if claims.token_chatgpt_account_id != team_id:
            raise WorkspaceMismatchError(expected=team_id, actual=claims.token_chatgpt_account_id)
        response = self._chatgpt_post(
            CODEX_RESPONSES_PATH,
            headers=_codex_responses_headers(access_token=access_token, team_id=team_id),
            json={
                "model": str(model or DEFAULT_CODEX_HEARTBEAT_MODEL),
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hi"}],
                    }
                ],
                "stream": True,
                "store": False,
                "instructions": _openai_codex_instructions(),
            },
            proxy_url=proxy_url,
            stream=True,
        )
        _assert_codex_stream_completed(response)
        return {"status": "ok", "token_chatgpt_account_id": claims.token_chatgpt_account_id}

    def _chatgpt_post(
        self,
        path: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        data: str | bytes | None = None,
        proxy_url: str = "",
        stream: bool = False,
    ):
        if proxy_url == "" and self._chatgpt_http_client_injected:
            return self._chatgpt_client.post(path, headers=headers, json=json, content=data)
        session = self._curl_session(proxy_url)
        return session.post(
            f"{self._config.chatgpt_base_url}{path}",
            headers=headers,
            json=json,
            data=data,
            timeout=self._config.timeout_s,
            stream=stream,
        )

    def _chatgpt_get(
        self,
        path: str,
        *,
        headers: dict[str, str],
        proxy_url: str = "",
    ):
        if proxy_url == "" and self._chatgpt_http_client_injected:
            return self._chatgpt_client.get(path, headers=headers)
        proxies = _curl_proxies(proxy_url)
        with curl_requests.Session(impersonate="chrome136", proxies=proxies) as session:
            return session.get(
                f"{self._config.chatgpt_base_url}{path}",
                headers=headers,
                timeout=self._config.timeout_s,
            )

    def _curl_session(self, proxy_url: str) -> curl_requests.Session:
        key = str(proxy_url or "")
        existing = self._curl_sessions.get(key)
        if existing is not None:
            return existing
        session = curl_requests.Session(impersonate="chrome136", proxies=_curl_proxies(proxy_url))
        self._curl_sessions[key] = session
        return session


def decode_access_token_claims(access_token: str) -> TokenClaims:
    parts = access_token.split(".")
    if len(parts) < 2:
        raise OpenAIChatGPTClientError("access_token is not a JWT")
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise OpenAIChatGPTClientError("access_token JWT payload decode failed") from exc
    if not isinstance(payload, dict):
        raise OpenAIChatGPTClientError("access_token JWT payload must be an object")

    auth_claim = payload.get(CHATGPT_AUTH_CLAIM) or {}
    if not isinstance(auth_claim, dict):
        raise OpenAIChatGPTClientError("access_token auth claim must be an object")

    return TokenClaims(
        token_chatgpt_account_id=str(auth_claim.get("chatgpt_account_id") or ""),
        account_id=str(
            auth_claim.get("chatgpt_user_id")
            or auth_claim.get("user_id")
            or payload.get("sub")
            or ""
        ),
        chatgpt_account_user_id=str(auth_claim.get("chatgpt_account_user_id") or ""),
        raw=payload,
    )


def _team_headers(
    *,
    access_token: str,
    team_id: str,
    referer: str = "https://chatgpt.com/",
    cookie_header: str = "",
) -> dict[str, str]:
    if not access_token:
        raise OpenAIChatGPTClientError("access_token is required")
    if not team_id:
        raise OpenAIChatGPTClientError("team_id is required")
    headers = {
        "authorization": f"Bearer {access_token}",
        "chatgpt-account-id": team_id,
        "content-type": "application/json",
        "accept": "*/*",
        "origin": "https://chatgpt.com",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if cookie_header:
        headers["cookie"] = cookie_header
        device_id = _cookie_value(cookie_header, "oai-did")
        if device_id:
            headers["oai-device-id"] = device_id
    return headers


def _accept_headers(*, access_token: str, device_id: str = "") -> dict[str, str]:
    if not access_token:
        raise OpenAIChatGPTClientError("access_token is required")
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "accept": "*/*",
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if device_id:
        headers["oai-device-id"] = device_id
    return headers


def _codex_responses_headers(*, access_token: str, team_id: str) -> dict[str, str]:
    if not access_token:
        raise OpenAIChatGPTClientError("access_token is required")
    if not team_id:
        raise OpenAIChatGPTClientError("team_id is required")
    return {
        "authorization": f"Bearer {access_token}",
        "chatgpt-account-id": team_id,
        "content-type": "application/json",
        "accept": "text/event-stream",
        "host": "chatgpt.com",
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }


def _assert_codex_stream_completed(response) -> None:
    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if not (200 <= status_code < 300):
            body = str(getattr(response, "text", "") or "")
            raise OpenAIChatGPTClientError(
                f"codex heartbeat failed: http_status={status_code} body_snippet={body[:500]}"
            )
        for raw in response.iter_lines():
            if not raw:
                continue
            line = (
                raw.decode(errors="replace").strip()
                if isinstance(raw, bytes)
                else str(raw).strip()
            )
            if not line.startswith("data:"):
                continue
            data_s = line.split(":", 1)[1].strip()
            if data_s == "[DONE]":
                raise OpenAIChatGPTClientError("codex stream ended before response.completed")
            try:
                data = json.loads(data_s)
            except json.JSONDecodeError:
                continue
            event_type = str(data.get("type") or "")
            if event_type in ("response.completed", "response.done"):
                return
            if event_type == "response.failed":
                response_body = (
                    data.get("response") if isinstance(data.get("response"), dict) else {}
                )
                error = (
                    response_body.get("error")
                    if isinstance(response_body.get("error"), dict)
                    else {}
                )
                message = str(error.get("message") or "OpenAI response failed")
                raise OpenAIChatGPTClientError(message[:500])
            if event_type == "error":
                error = data.get("error") if isinstance(data.get("error"), dict) else {}
                message = str(error.get("message") or "Unknown error")
                raise OpenAIChatGPTClientError(message[:500])
        raise OpenAIChatGPTClientError("codex stream ended before response.completed")
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _openai_codex_instructions() -> str:
    try:
        return CODEX_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except Exception:
        return "You are a helpful coding assistant."


def _curl_proxies(proxy_url: str) -> dict[str, str] | None:
    proxy = str(proxy_url or "").strip()
    if not proxy:
        return None
    proxy = proxy.replace("socks5://", "socks5h://")
    return {"http": proxy, "https": proxy}


def _response_payload(response) -> dict:
    text = response.text
    try:
        body = response.json() if text else {}
    except json.JSONDecodeError:
        body = {"body": text}
    if not isinstance(body, dict):
        body = {"body": body}
    body.setdefault("http_status", response.status_code)
    body.setdefault("raw_body", text[:4000])
    is_error = bool(getattr(response, "is_error", False))
    if not hasattr(response, "is_error"):
        is_error = int(response.status_code or 0) >= 400
    if is_error:
        snippet = str(body)[:800]
        raise OpenAIChatGPTClientError(
            "chatgpt backend request failed: "
            f"http_status={response.status_code} body_snippet={snippet}"
        )
    return body


def _cookie_value(cookie_header: str, name: str) -> str:
    prefix = f"{name}="
    for item in cookie_header.split(";"):
        part = item.strip()
        if part.startswith(prefix):
            return part[len(prefix) :].strip()
    return ""


def _expires_at(payload: dict[str, Any]) -> datetime | None:
    expires_in = payload.get("expires_in")
    if expires_in is None or expires_in == "":
        return None
    try:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError) as exc:
        raise OpenAIChatGPTClientError("oauth expires_in must be integer seconds") from exc


def _b64url_decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
