from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow
from refactor_app.plugins.openai_auth_protocol.config import Config

from invite_executor.models import SessionOtpSubmitItem
from invite_executor.proxy_pool import StaticProxyAssignment
from invite_executor.transport import ExistingAsyncInviteTransport, WarmupReport

_AUTH_BASE_URL = "https://auth.openai.com"
_OTP_VALIDATE_PATH = "/api/accounts/email-otp/validate"
_OTP_REFERER = f"{_AUTH_BASE_URL}/email-verification"


class SessionOtpPreparationError(RuntimeError):
    pass


class SessionOtpValidateError(RuntimeError):
    def __init__(self, *, http_status: int, body_head: str) -> None:
        super().__init__(f"OTP validate failed: {http_status} - {body_head}")
        self.http_status = int(http_status)


class SessionOtpValidateTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class PreparedSessionOtp:
    index: int
    item_id: str
    email: str
    proxy_assignment: StaticProxyAssignment
    headers: dict[str, str]
    json_body: dict[str, str]
    cookies: tuple[dict[str, Any], ...]


class AsyncSessionOtpTransport(Protocol):
    async def prewarm(self, prepared: list[PreparedSessionOtp]) -> WarmupReport: ...

    async def send(self, prepared: PreparedSessionOtp) -> dict[str, Any]: ...

    def proxy_endpoint_id(self, prepared: PreparedSessionOtp) -> str: ...

    async def close(self) -> None: ...


def prepare_session_otp(
    *,
    index: int,
    proxy_slot: int,
    item: SessionOtpSubmitItem,
) -> PreparedSessionOtp:
    snapshot = dict(item.snapshot)
    otp_code = str(snapshot.get("otp_code") or "").strip()
    if not otp_code:
        raise SessionOtpPreparationError("snapshot has no OTP code")

    snapshot_email = _snapshot_email(snapshot)
    if snapshot_email and snapshot_email.casefold() != item.email.casefold():
        raise SessionOtpPreparationError("snapshot email does not match request email")

    proxy_url = item.proxy_url.get_secret_value()
    snapshot["proxy"] = proxy_url
    config = Config()
    config.auth_env_flags = {
        "OAUTH_CODEX_RT_BEFORE_CALLBACK": "0",
        "OAUTH_CODEX_RT_EXCHANGE": "0",
        "OAUTH_SECONDARY_AUTHORIZE_EXCHANGE": "0",
        "OAUTH_REFRESH_ONLY": "0",
        "SKIP_OAUTH_TOKEN_EXCHANGE": "1",
    }
    flow = AuthFlow(config)
    sessions = [flow.session]
    try:
        flow.restore_protocol_snapshot(snapshot)
        if flow.session not in sessions:
            sessions.append(flow.session)
        headers = {
            str(key): str(value)
            for key, value in flow._common_headers(_OTP_REFERER).items()
        }
        headers["Content-Type"] = "application/json"
        cookies = tuple(dict(cookie) for cookie in flow._export_cookie_jar())
    except Exception as exc:
        raise SessionOtpPreparationError(
            f"snapshot restore failed: {type(exc).__name__}"
        ) from exc
    finally:
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

    endpoint_id = direct_proxy_endpoint_id(proxy_url)
    return PreparedSessionOtp(
        index=index,
        item_id=item.item_id,
        email=item.email,
        proxy_assignment=StaticProxyAssignment(
            slot=proxy_slot,
            endpoint_id=endpoint_id,
            proxy_url=proxy_url,
        ),
        headers=headers,
        json_body={"code": otp_code},
        cookies=cookies,
    )


class ExistingAsyncSessionOtpTransport(ExistingAsyncInviteTransport):
    def __init__(
        self,
        *,
        request_timeout_s: float,
        max_clients: int,
        prewarm_rounds: int,
        prewarm_attempts: int,
        prewarm_start_interval_s: float,
        prewarm_keepalive_interval_s: float,
        prewarm_timeout_s: float,
    ) -> None:
        super().__init__(
            chatgpt_base_url=_AUTH_BASE_URL,
            request_timeout_s=request_timeout_s,
            max_clients=max_clients,
            max_streams_per_proxy=1,
            prewarm_rounds=prewarm_rounds,
            prewarm_attempts=prewarm_attempts,
            prewarm_start_interval_s=prewarm_start_interval_s,
            prewarm_keepalive_interval_s=prewarm_keepalive_interval_s,
            prewarm_timeout_s=prewarm_timeout_s,
        )

    def _configure_session(
        self,
        prepared: PreparedSessionOtp,
        session: curl_requests.AsyncSession,
    ) -> None:
        _restore_cookie_jar(session, prepared.cookies)

    async def send(self, prepared: PreparedSessionOtp) -> dict[str, Any]:
        try:
            response = await self._session(prepared).post(
                f"{_AUTH_BASE_URL}{_OTP_VALIDATE_PATH}",
                headers=prepared.headers,
                json=prepared.json_body,
                proxy=self._proxy_url(prepared),
                timeout=self._request_timeout_s,
            )
        except CurlTimeout as exc:
            raise SessionOtpValidateTimeoutError(
                f"OTP validate timed out after {self._request_timeout_s:g}s"
            ) from exc

        http_status = int(response.status_code or 0)
        payload = _response_json(response)
        if http_status != 200:
            raise SessionOtpValidateError(
                http_status=http_status,
                body_head=str(response.text or "")[:260],
            )

        continue_url = _normalize_continue_url(_extract_continue_url(payload))
        snapshot_patch = {
            "phase": "otp_validated",
            "cookies": _export_cookie_jar(self._session(prepared)),
            "continue_url": continue_url,
            "page_type": _extract_page_type(payload),
            "otp_code": "",
            "otp_validated_at": time.time(),
            "otp_validate_response": payload,
        }
        return {
            "http_status": http_status,
            "snapshot_patch": snapshot_patch,
        }


def _snapshot_email(snapshot: dict[str, Any]) -> str:
    direct = str(snapshot.get("email") or "").strip()
    if direct:
        return direct
    result = snapshot.get("result")
    if isinstance(result, dict):
        return str(result.get("email") or "").strip()
    return ""


def direct_proxy_endpoint_id(proxy_url: str) -> str:
    return f"direct-{hashlib.sha256(proxy_url.encode('utf-8')).hexdigest()[:16]}"


def _restore_cookie_jar(
    session: curl_requests.AsyncSession,
    cookies: tuple[dict[str, Any], ...],
) -> None:
    for item in cookies:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        value = str(item.get("value") or "")
        domain = str(item.get("domain") or "").strip()
        path = str(item.get("path") or "/").strip() or "/"
        try:
            if domain:
                session.cookies.set(name, value, domain=domain, path=path)
            else:
                session.cookies.set(name, value, path=path)
        except Exception:
            session.cookies.set(name, value)


def _export_cookie_jar(session: curl_requests.AsyncSession) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    try:
        iterable = list(session.cookies.jar)
    except Exception:
        iterable = []
    for cookie in iterable:
        name = str(getattr(cookie, "name", "") or "").strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": str(getattr(cookie, "value", "") or ""),
                "domain": str(getattr(cookie, "domain", "") or ""),
                "path": str(getattr(cookie, "path", "") or "/") or "/",
                "expires": getattr(cookie, "expires", None),
                "secure": bool(getattr(cookie, "secure", False)),
                "discard": bool(getattr(cookie, "discard", False)),
            }
        )
    return cookies


def _response_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        try:
            payload = json.loads(str(response.text or "{}"))
        except Exception:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _extract_page_type(payload: dict[str, Any]) -> str:
    page = payload.get("page")
    if not isinstance(page, dict):
        return ""
    return str(page.get("type") or "").strip()


def _extract_continue_url(payload: dict[str, Any]) -> str:
    continue_url = str(payload.get("continue_url") or "").strip()
    if continue_url:
        return continue_url
    page = payload.get("page")
    if not isinstance(page, dict) or str(page.get("type") or "").strip() != "external_url":
        return ""
    page_payload = page.get("payload")
    if not isinstance(page_payload, dict):
        return ""
    return str(page_payload.get("url") or "").strip()


def _normalize_continue_url(continue_url: str) -> str:
    if continue_url.startswith("/"):
        return urljoin(_AUTH_BASE_URL, continue_url)
    return continue_url
