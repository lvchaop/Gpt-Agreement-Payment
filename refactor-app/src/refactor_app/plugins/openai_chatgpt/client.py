from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from curl_cffi import requests as curl_requests
from curl_cffi.const import CurlOpt
from curl_cffi.requests.exceptions import Timeout as CurlTimeout

from refactor_app.plugins.contracts import OAuthTokenSet, TokenClaims

DEFAULT_AUTH_BASE_URL = "https://auth.openai.com"
DEFAULT_CHATGPT_BASE_URL = "https://chatgpt.com"
CHATGPT_AUTH_CLAIM = "https://api.openai.com/auth"
DEFAULT_CODEX_HEARTBEAT_MODEL = "gpt-5.5"
CODEX_RESPONSES_PATH = "/backend-api/codex/responses"
WHAM_USAGE_PATH = "/backend-api/wham/usage"
WHAM_AUTH_CREDENTIALS_PATH = "/backend-api/wham/auth-credentials"
CHANGE_EMAIL_ELIGIBILITY_PATH = "/backend-api/accounts/change_email/eligibility"
CHANGE_EMAIL_BEGIN_PATH = "/backend-api/accounts/change_email/begin"
CHANGE_EMAIL_VERIFY_PATH = "/backend-api/accounts/change_email/verify"
SUBSCRIPTIONS_UPDATE_PATH = "/backend-api/subscriptions/update"
WHAM_CODEX_LOCAL_ACCESS_SCOPE = "chatgpt.workspace.feature.allow-codex-local-access.access"
CODEX_INSTRUCTIONS_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "openai_codex_instructions.txt"
)


class OpenAIChatGPTClientError(RuntimeError):
    pass


class OpenAIChatGPTTimeoutError(OpenAIChatGPTClientError):
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
        self._curl_sessions: dict[tuple[str, tuple[str, ...]], curl_requests.Session] = {}

    def close(self) -> None:
        for session in self._curl_sessions.values():
            try:
                session.close()
            except Exception:
                pass
        self._curl_sessions.clear()
        closed: set[int] = set()
        for client in (self._auth_client, self._chatgpt_client):
            if id(client) in closed:
                continue
            closed.add(id(client))
            client.close()

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
        proxy_url: str = "",
        proxy_resolve: tuple[str, ...] = (),
    ) -> dict:
        payload = self.invite_members(
            access_token=access_token,
            team_id=team_id,
            emails=[email],
            cookie_header=cookie_header,
            seat_type=seat_type,
            proxy_url=proxy_url,
            proxy_resolve=proxy_resolve,
        )
        normalized_email = email.strip().lower()
        errors = _invite_items_by_email(payload.get("errored_emails"))
        if normalized_email in errors:
            raise OpenAIChatGPTClientError(
                "chatgpt invite failed: "
                f"email={email} error={errors[normalized_email].get('error') or 'unknown error'}"
            )
        invites = _invite_items_by_email(payload.get("account_invites"))
        if normalized_email not in invites:
            raise OpenAIChatGPTClientError(
                f"chatgpt invite response missing account_invite: email={email}"
            )
        return payload

    def invite_members(
        self,
        *,
        access_token: str,
        team_id: str,
        emails: list[str],
        cookie_header: str = "",
        seat_type: str = "default",
        proxy_url: str = "",
        proxy_resolve: tuple[str, ...] = (),
    ) -> dict:
        normalized_emails = list(dict.fromkeys(email.strip() for email in emails if email.strip()))
        if not normalized_emails:
            raise OpenAIChatGPTClientError("at least one invite email is required")
        response = self._chatgpt_post(
            f"/backend-api/accounts/{team_id}/invites",
            headers=_team_headers(
                access_token=access_token,
                team_id=team_id,
                referer="https://chatgpt.com/admin",
                cookie_header=cookie_header,
            ),
            json={
                "email_addresses": normalized_emails,
                "role": "standard-user",
                "seat_type": seat_type,
                "resend_emails": True,
            },
            proxy_url=proxy_url,
            proxy_resolve=proxy_resolve,
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

    def remove_account_user(
        self,
        *,
        access_token: str,
        account_id: str,
        user_id: str,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise OpenAIChatGPTClientError("user_id is required")
        response = self._chatgpt_delete(
            f"/backend-api/accounts/{account_id}/users/{quote(normalized_user_id, safe='')}",
            headers=_team_headers(
                access_token=access_token,
                team_id=account_id,
                cookie_header=cookie_header,
                referer="https://chatgpt.com/admin",
            ),
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
        _assert_codex_heartbeat_http_ok(response)
        return {"status": "ok", "token_chatgpt_account_id": claims.token_chatgpt_account_id}

    def probe_codex_responses_usage(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict:
        claims: TokenClaims | None = None
        if "." in access_token:
            claims = decode_access_token_claims(access_token)
            if team_id and claims.token_chatgpt_account_id != team_id:
                raise WorkspaceMismatchError(
                    expected=team_id, actual=claims.token_chatgpt_account_id
                )
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
        headers = {str(key).lower(): str(value) for key, value in dict(response.headers).items()}
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 200 or status_code >= 300:
            return {
                "status": "failed",
                "token_chatgpt_account_id": claims.token_chatgpt_account_id
                if claims is not None
                else team_id,
                "headers": headers,
                "http_status": status_code,
                "error_code": f"http_{status_code}",
                "payment_required": status_code == 402,
                "unauthorized": status_code == 401,
            }
        _assert_codex_heartbeat_http_ok(response)
        return {
            "status": "ok",
            "token_chatgpt_account_id": claims.token_chatgpt_account_id
            if claims is not None
            else team_id,
            "headers": headers,
        }

    def fetch_wham_usage(
        self,
        *,
        access_token: str,
        chatgpt_account_id: str = "",
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        response = self._chatgpt_get(
            WHAM_USAGE_PATH,
            headers=_wham_headers(
                access_token=access_token,
                chatgpt_account_id=chatgpt_account_id,
                cookie_header=cookie_header,
            ),
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def fetch_subscription(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        response = self._chatgpt_get(
            f"/backend-api/subscriptions?account_id={account_id}",
            headers=_team_headers(
                access_token=access_token,
                team_id=account_id,
                cookie_header=cookie_header,
            ),
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def update_subscription_seats(
        self,
        *,
        access_token: str,
        account_id: str,
        updated_seats: int,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        if updated_seats < 1:
            raise OpenAIChatGPTClientError("updated_seats must be positive")
        response = self._chatgpt_post(
            SUBSCRIPTIONS_UPDATE_PATH,
            headers=_team_headers(
                access_token=access_token,
                team_id=account_id,
                cookie_header=cookie_header,
            ),
            json={
                "account_id": account_id,
                "updated_seats": updated_seats,
            },
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def list_account_users(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        page_size: int = 100,
        proxy_url: str = "",
    ) -> list[dict]:
        return self._list_account_items(
            path=f"/backend-api/accounts/{account_id}/users",
            item_keys=("items", "users", "data"),
            access_token=access_token,
            account_id=account_id,
            cookie_header=cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )

    def list_account_invites(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        page_size: int = 100,
        proxy_url: str = "",
    ) -> list[dict]:
        return self._list_account_items(
            path=f"/backend-api/accounts/{account_id}/invites",
            item_keys=("items", "invites", "data"),
            access_token=access_token,
            account_id=account_id,
            cookie_header=cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )

    def create_wham_auth_credential(
        self,
        *,
        access_token: str = "",
        chatgpt_account_id: str,
        name: str,
        ttl_seconds: int = 7_776_000,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        if not chatgpt_account_id:
            raise OpenAIChatGPTClientError("chatgpt_account_id is required")
        credential_name = str(name or "").strip()
        if not credential_name:
            raise OpenAIChatGPTClientError("name is required")
        ttl = int(ttl_seconds or 0)
        if ttl <= 0:
            raise OpenAIChatGPTClientError("ttl_seconds must be positive")
        if access_token:
            _require_workspace_session_access_token(
                access_token=access_token,
                chatgpt_account_id=chatgpt_account_id,
            )
        headers = _wham_headers(
            access_token=access_token,
            chatgpt_account_id=chatgpt_account_id,
            cookie_header="" if access_token else cookie_header,
            device_id=_cookie_value(cookie_header, "oai-did"),
            referer="https://chatgpt.com/admin/access-tokens?modal=create",
            target_path=WHAM_AUTH_CREDENTIALS_PATH,
        )
        if access_token or self._chatgpt_http_client_injected:
            exchanged_access_token = ""
            if cookie_header and not access_token:
                exchanged_access_token = self.exchange_workspace_session_access_token(
                    chatgpt_account_id=chatgpt_account_id,
                    cookie_header=cookie_header,
                    proxy_url=proxy_url,
                )
                if not exchanged_access_token:
                    raise OpenAIChatGPTClientError("workspace_session_access_token_missing")
                headers = _wham_headers(
                    access_token=exchanged_access_token,
                    chatgpt_account_id=chatgpt_account_id,
                    cookie_header="",
                    device_id=_cookie_value(cookie_header, "oai-did"),
                    referer="https://chatgpt.com/admin/access-tokens?modal=create",
                    target_path=WHAM_AUTH_CREDENTIALS_PATH,
                )
            response = self._chatgpt_post(
                WHAM_AUTH_CREDENTIALS_PATH,
                headers=headers,
                json={
                    "name": credential_name,
                    "scopes": [WHAM_CODEX_LOCAL_ACCESS_SCOPE],
                    "ttl": ttl,
                },
                proxy_url=proxy_url,
            )
            return _response_payload(response)

        session = self._curl_session(proxy_url)
        web_session_cookie_header = _minimal_web_session_cookie_header(cookie_header)
        _seed_cookie_header(session, web_session_cookie_header)
        exchanged_access_token = self._exchange_workspace_web_session(
            session=session,
            chatgpt_account_id=chatgpt_account_id,
            cookie_header=web_session_cookie_header,
        )
        if not exchanged_access_token:
            raise OpenAIChatGPTClientError("workspace_session_access_token_missing")
        _require_workspace_session_access_token(
            access_token=exchanged_access_token,
            chatgpt_account_id=chatgpt_account_id,
        )
        headers = _wham_headers(
            access_token=exchanged_access_token,
            chatgpt_account_id=chatgpt_account_id,
            cookie_header="",
            device_id=_cookie_value(cookie_header, "oai-did"),
            referer="https://chatgpt.com/admin/access-tokens?modal=create",
            target_path=WHAM_AUTH_CREDENTIALS_PATH,
        )
        response = session.post(
            f"{self._config.chatgpt_base_url}{WHAM_AUTH_CREDENTIALS_PATH}",
            headers=headers,
            json={
                "name": credential_name,
                "scopes": [WHAM_CODEX_LOCAL_ACCESS_SCOPE],
                "ttl": ttl,
            },
            timeout=self._config.timeout_s,
        )
        return _response_payload(response)

    def fetch_web_session_payload(
        self,
        *,
        cookie_header: str,
        proxy_url: str = "",
    ) -> dict:
        web_session_cookie_header = _minimal_web_session_cookie_header(cookie_header)
        if not web_session_cookie_header:
            raise OpenAIChatGPTClientError("cookie_header is required")
        response = self._chatgpt_get(
            "/api/auth/session",
            headers=_wham_headers(
                cookie_header=web_session_cookie_header,
                referer="https://chatgpt.com/",
            ),
            proxy_url=proxy_url,
        )
        payload = _response_payload(response)
        if not _session_access_token_from_payload(payload):
            raise OpenAIChatGPTClientError("web_session_access_token_missing")
        return payload

    def check_change_email_eligibility(
        self,
        *,
        access_token: str,
        cookie_header: str,
        proxy_url: str = "",
    ) -> dict:
        response = self._chatgpt_get(
            CHANGE_EMAIL_ELIGIBILITY_PATH,
            headers=_account_change_email_headers(
                access_token=access_token,
                cookie_header=cookie_header,
            ),
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def begin_change_email(
        self,
        *,
        access_token: str,
        cookie_header: str,
        email: str,
        remove_social_subscriptions: bool = False,
        proxy_url: str = "",
    ) -> dict:
        normalized_email = str(email or "").strip()
        if not normalized_email:
            raise OpenAIChatGPTClientError("email is required")
        body: dict[str, Any] = {"email": normalized_email}
        if remove_social_subscriptions:
            body["remove_social_subs"] = True
        response = self._chatgpt_post(
            CHANGE_EMAIL_BEGIN_PATH,
            headers=_account_change_email_headers(
                access_token=access_token,
                cookie_header=cookie_header,
            ),
            json=body,
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def verify_change_email(
        self,
        *,
        access_token: str,
        cookie_header: str,
        email: str,
        code: str,
        remove_social_subscriptions: bool = False,
        proxy_url: str = "",
    ) -> dict:
        normalized_email = str(email or "").strip()
        normalized_code = str(code or "").strip()
        if not normalized_email:
            raise OpenAIChatGPTClientError("email is required")
        if len(normalized_code) != 6 or not normalized_code.isdigit():
            raise OpenAIChatGPTClientError("code must be 6 digits")
        body: dict[str, Any] = {"email": normalized_email, "code": normalized_code}
        if remove_social_subscriptions:
            body["remove_social_subs"] = True
        response = self._chatgpt_post(
            CHANGE_EMAIL_VERIFY_PATH,
            headers=_account_change_email_headers(
                access_token=access_token,
                cookie_header=cookie_header,
            ),
            json=body,
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def exchange_workspace_session_access_token(
        self,
        *,
        chatgpt_account_id: str,
        cookie_header: str,
        proxy_url: str = "",
    ) -> str:
        payload = self.exchange_workspace_session_payload(
            chatgpt_account_id=chatgpt_account_id,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
        return _session_access_token_from_payload(payload)

    def exchange_workspace_session_payload(
        self,
        *,
        chatgpt_account_id: str,
        cookie_header: str,
        proxy_url: str = "",
    ) -> dict:
        if not chatgpt_account_id:
            raise OpenAIChatGPTClientError("chatgpt_account_id is required")
        web_session_cookie_header = _minimal_web_session_cookie_header(cookie_header)
        if not web_session_cookie_header:
            raise OpenAIChatGPTClientError("cookie_header is required")
        payload = self._exchange_workspace_web_session_payload_httpx(
            chatgpt_account_id=chatgpt_account_id,
            cookie_header=web_session_cookie_header,
            proxy_url=proxy_url,
        )
        access_token = _session_access_token_from_payload(payload)
        if not access_token:
            raise OpenAIChatGPTClientError("workspace_session_access_token_missing")
        _require_workspace_session_access_token(
            access_token=access_token,
            chatgpt_account_id=chatgpt_account_id,
        )
        return payload

    def _warm_chatgpt_web_session(self, *, session, cookie_header: str) -> None:
        headers = _wham_headers(
            access_token="",
            cookie_header=cookie_header,
            allow_session_cookies=not cookie_header,
            referer="https://chatgpt.com/",
        )
        for path in (
            "/api/auth/providers",
            "/api/auth/csrf",
            "/api/auth/session",
        ):
            response = session.get(
                f"{self._config.chatgpt_base_url}{path}",
                headers=headers,
                timeout=self._config.timeout_s,
            )
            if int(response.status_code or 0) >= 400:
                body = str(getattr(response, "text", "") or "")
                raise OpenAIChatGPTClientError(
                    "chatgpt web session warmup failed: "
                    f"path={path} http_status={response.status_code} body_snippet={body[:500]}"
                )

    def _exchange_workspace_web_session_httpx(
        self,
        *,
        chatgpt_account_id: str,
        cookie_header: str,
        proxy_url: str,
    ) -> str:
        return _session_access_token_from_payload(
            self._exchange_workspace_web_session_payload_httpx(
                chatgpt_account_id=chatgpt_account_id,
                cookie_header=cookie_header,
                proxy_url=proxy_url,
            )
        )

    def _exchange_workspace_web_session_payload_httpx(
        self,
        *,
        chatgpt_account_id: str,
        cookie_header: str,
        proxy_url: str,
    ) -> dict:
        path = _exchange_workspace_session_path(chatgpt_account_id)
        response = self._chatgpt_get(
            path,
            headers=_wham_headers(
                access_token="",
                cookie_header=cookie_header,
                allow_session_cookies=not cookie_header,
                referer="https://chatgpt.com/",
            ),
            proxy_url=proxy_url,
        )
        return _response_payload(response)

    def _exchange_workspace_web_session(
        self,
        *,
        session,
        chatgpt_account_id: str,
        cookie_header: str,
    ) -> str:
        path = _exchange_workspace_session_path(chatgpt_account_id)
        response = session.get(
            f"{self._config.chatgpt_base_url}{path}",
            headers=_wham_headers(
                access_token="",
                cookie_header=cookie_header,
                allow_session_cookies=not cookie_header,
                referer="https://chatgpt.com/",
            ),
            timeout=self._config.timeout_s,
        )
        return _session_access_token_from_payload(_response_payload(response))

    def _list_account_items(
        self,
        *,
        path: str,
        item_keys: tuple[str, ...],
        access_token: str,
        account_id: str,
        cookie_header: str,
        page_size: int,
        proxy_url: str,
    ) -> list[dict]:
        safe_page_size = max(1, min(int(page_size or 100), 200))
        items: list[dict] = []
        for offset in range(0, 100000, safe_page_size):
            response = self._chatgpt_get(
                f"{path}?offset={offset}&limit={safe_page_size}&query=",
                headers=_team_headers(
                    access_token=access_token,
                    team_id=account_id,
                    cookie_header=cookie_header,
                ),
                proxy_url=proxy_url,
            )
            payload = _response_payload(response)
            batch = _list_items(payload, item_keys)
            items.extend(batch)
            total = _response_total(payload)
            if not batch or len(batch) < safe_page_size:
                break
            if total is not None and len(items) >= total:
                break
        return items

    def _chatgpt_post(
        self,
        path: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        data: str | bytes | None = None,
        proxy_url: str = "",
        proxy_resolve: tuple[str, ...] = (),
        stream: bool = False,
    ):
        try:
            if proxy_url == "" and self._chatgpt_http_client_injected:
                return self._chatgpt_client.post(path, headers=headers, json=json, content=data)
            session = self._curl_session(proxy_url, proxy_resolve=proxy_resolve)
            return session.post(
                f"{self._config.chatgpt_base_url}{path}",
                headers=headers,
                json=json,
                data=data,
                timeout=self._config.timeout_s,
                stream=stream,
            )
        except (httpx.TimeoutException, CurlTimeout) as exc:
            raise OpenAIChatGPTTimeoutError(
                f"chatgpt backend request timed out after {self._config.timeout_s:g}s: path={path}"
            ) from exc

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
        with curl_requests.Session(impersonate="chrome120", proxies=proxies) as session:
            return session.get(
                f"{self._config.chatgpt_base_url}{path}",
                headers=headers,
                timeout=self._config.timeout_s,
            )

    def _chatgpt_delete(
        self,
        path: str,
        *,
        headers: dict[str, str],
        proxy_url: str = "",
    ):
        try:
            if proxy_url == "" and self._chatgpt_http_client_injected:
                return self._chatgpt_client.delete(path, headers=headers)
            session = self._curl_session(proxy_url)
            return session.delete(
                f"{self._config.chatgpt_base_url}{path}",
                headers=headers,
                timeout=self._config.timeout_s,
            )
        except (httpx.TimeoutException, CurlTimeout) as exc:
            raise OpenAIChatGPTTimeoutError(
                f"chatgpt backend request timed out after {self._config.timeout_s:g}s: path={path}"
            ) from exc

    def _curl_session(
        self,
        proxy_url: str,
        *,
        proxy_resolve: tuple[str, ...] = (),
    ) -> curl_requests.Session:
        resolve_entries = tuple(str(item) for item in proxy_resolve if str(item))
        key = (str(proxy_url or ""), resolve_entries)
        existing = self._curl_sessions.get(key)
        if existing is not None:
            return existing
        curl_options = {CurlOpt.RESOLVE: list(resolve_entries)} if resolve_entries else None
        session = curl_requests.Session(
            impersonate="chrome120",
            proxies=_curl_proxies(proxy_url),
            curl_options=curl_options,
        )
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


def _account_change_email_headers(
    *,
    access_token: str,
    cookie_header: str,
) -> dict[str, str]:
    if not access_token:
        raise OpenAIChatGPTClientError("access_token is required")
    if not cookie_header:
        raise OpenAIChatGPTClientError("cookie_header is required")
    return _wham_headers(
        access_token=access_token,
        cookie_header=_minimal_web_session_cookie_header(cookie_header),
        referer="https://chatgpt.com/",
    )


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
    headers = {
        "authorization": f"Bearer {access_token}",
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
    if team_id:
        headers["chatgpt-account-id"] = team_id
    return headers


def _wham_headers(
    *,
    access_token: str = "",
    chatgpt_account_id: str = "",
    cookie_header: str = "",
    device_id: str = "",
    referer: str = "https://chatgpt.com/",
    target_path: str = "",
    allow_session_cookies: bool = False,
) -> dict[str, str]:
    if not access_token and not cookie_header and not allow_session_cookies:
        raise OpenAIChatGPTClientError("access_token or cookie_header is required")
    headers = {
        "content-type": "application/json",
        "accept": "*/*",
        "host": "chatgpt.com",
        "origin": "https://chatgpt.com",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if access_token:
        headers["authorization"] = f"Bearer {access_token}"
    if chatgpt_account_id:
        headers["chatgpt-account-id"] = chatgpt_account_id
    if cookie_header:
        headers["cookie"] = cookie_header
        if not device_id:
            device_id = _cookie_value(cookie_header, "oai-did")
    if device_id:
        headers["oai-device-id"] = device_id
    if target_path:
        headers["x-openai-target-path"] = target_path
        headers["x-openai-target-route"] = target_path
    return headers


def _assert_codex_heartbeat_http_ok(response) -> None:
    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if not (200 <= status_code < 300):
            body = str(getattr(response, "text", "") or "")
            raise OpenAIChatGPTClientError(
                f"codex heartbeat failed: http_status={status_code} body_snippet={body[:500]}"
            )
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


def _seed_cookie_header(session, cookie_header: str) -> None:
    if not cookie_header:
        return
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
    except Exception:
        cookie = SimpleCookie()
    required_cookie_names = {
        "__Secure-next-auth.session-token",
        "__Host-next-auth.csrf-token",
        "oai-did",
    }
    for name, morsel in cookie.items():
        if name not in required_cookie_names:
            continue
        value = morsel.value
        if not name or value is None:
            continue
        try:
            session.cookies.set(name, value, domain=".chatgpt.com", path="/")
        except Exception:
            try:
                session.cookies.set(name, value)
            except Exception:
                pass


def _minimal_web_session_cookie_header(cookie_header: str) -> str:
    if not cookie_header:
        return ""
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
    except Exception:
        return cookie_header
    session_cookie_names = sorted(
        name
        for name in cookie
        if name == "__Secure-next-auth.session-token"
        or name.startswith("__Secure-next-auth.session-token.")
    )
    names = [
        *session_cookie_names,
        "__Host-next-auth.csrf-token",
        "oai-did",
    ]
    parts = []
    for name in names:
        morsel = cookie.get(name)
        if morsel is not None and morsel.value:
            parts.append(f"{name}={morsel.value}")
    return "; ".join(parts) or cookie_header


def _require_workspace_session_access_token(
    *,
    access_token: str,
    chatgpt_account_id: str,
) -> TokenClaims:
    claims = decode_access_token_claims(access_token)
    if claims.token_chatgpt_account_id != chatgpt_account_id:
        raise WorkspaceMismatchError(
            expected=chatgpt_account_id,
            actual=claims.token_chatgpt_account_id,
        )
    return claims


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


def _invite_items_by_email(value: object) -> dict[str, dict]:
    if not isinstance(value, list):
        return {}
    result: dict[str, dict] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        email = (
            str(item.get("email_address") or item.get("email") or item.get("emailAddress") or "")
            .strip()
            .lower()
        )
        if email:
            result[email] = item
    return result


def _exchange_workspace_session_path(chatgpt_account_id: str) -> str:
    query = urlencode(
        {
            "exchange_workspace_token": "true",
            "workspace_id": chatgpt_account_id,
            "reason": "setCurrentAccount",
        }
    )
    return f"/api/auth/session?{query}"


def _session_access_token_from_payload(payload: dict) -> str:
    for key in ("accessToken", "access_token"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("accessToken", "access_token"):
            value = user.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _list_items(payload: dict, keys: tuple[str, ...]) -> list[dict]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _response_total(payload: dict) -> int | None:
    for key in ("total", "total_count", "totalCount", "count"):
        value = payload.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


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
