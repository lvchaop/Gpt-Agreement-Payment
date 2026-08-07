from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from http.cookies import SimpleCookie

from refactor_app.plugins.mail_external_api.plugin import prepare_domain_mailbox

from .auth_flow import AuthFlow, AuthResult
from .codex_rt import ExternalMailOtpAdapter, OtpProvider
from .config import Config


@dataclass(frozen=True)
class SessionLoginResult:
    ok: bool
    auth_result: AuthResult
    cookie_header: str
    auth_cookie_header: str
    snapshot: dict


@dataclass(frozen=True)
class SessionOtpPrepareResult:
    ok: bool
    snapshot: dict


@dataclass(frozen=True)
class SessionOtpSubmitResult:
    ok: bool
    snapshot: dict


def acquire_chatgpt_session(
    *,
    email: str,
    password: str,
    proxy: str = "",
    mail_provider: OtpProvider,
    trace_dump_path: str = "",
    skip_oauth_token_exchange: bool = True,
    totp_code_provider: Callable[[], str] | None = None,
) -> SessionLoginResult:
    config = Config()
    config.proxy = proxy or None
    config.auth_env_flags = {
        "OAUTH_CODEX_RT_BEFORE_CALLBACK": "0",
        "OAUTH_CODEX_RT_EXCHANGE": "0",
        "OAUTH_SECONDARY_AUTHORIZE_EXCHANGE": "0",
        "OAUTH_REFRESH_ONLY": "0",
    }
    if skip_oauth_token_exchange:
        config.auth_env_flags["SKIP_OAUTH_TOKEN_EXCHANGE"] = "1"
    if trace_dump_path:
        config.auth_trace_dump_enabled = True
        config.auth_trace_dump_path = trace_dump_path

    mailbox_email = email.strip()
    openai_email = mailbox_email
    prepare_domain_mailbox(mail_provider, email=mailbox_email)
    flow = AuthFlow(config)
    try:
        adapter = ExternalMailOtpAdapter(
            mail_provider,
            ensure_before_wait=False,
            mailbox_email=mailbox_email,
        )
        result = flow.run_protocol_login(
            email=openai_email,
            password=password,
            mail_provider=adapter,
            existing_only=True,
            totp_code_provider=totp_code_provider,
        )
        result.cookie_header = flow._build_chatgpt_cookie_header()
        auth_cookie_header = _cookie_header_from_session(flow, "openai.com")
        if not auth_cookie_header and trace_dump_path:
            auth_cookie_header = _cookie_header_from_trace_dump(trace_dump_path)
        ok = bool(result.session_token and result.access_token)
        return SessionLoginResult(
            ok=ok,
            auth_result=result,
            cookie_header=result.cookie_header,
            auth_cookie_header=auth_cookie_header,
            snapshot=flow.export_protocol_snapshot(mail_events=adapter.events),
        )
    finally:
        flow.close()


def prepare_chatgpt_session_otp(
    *,
    email: str,
    password: str,
    proxy: str = "",
    mail_provider: OtpProvider,
    trace_dump_path: str = "",
) -> SessionOtpPrepareResult:
    config = Config()
    config.proxy = proxy or None
    config.auth_env_flags = {
        "OAUTH_CODEX_RT_BEFORE_CALLBACK": "0",
        "OAUTH_CODEX_RT_EXCHANGE": "0",
        "OAUTH_SECONDARY_AUTHORIZE_EXCHANGE": "0",
        "OAUTH_REFRESH_ONLY": "0",
        "SKIP_OAUTH_TOKEN_EXCHANGE": "1",
    }
    if trace_dump_path:
        config.auth_trace_dump_enabled = True
        config.auth_trace_dump_path = trace_dump_path

    mailbox_email = email.strip()
    openai_email = mailbox_email
    prepare_domain_mailbox(mail_provider, email=mailbox_email)
    flow = AuthFlow(config)
    try:
        adapter = ExternalMailOtpAdapter(
            mail_provider,
            ensure_before_wait=False,
            mailbox_email=mailbox_email,
        )
        snapshot = flow.run_protocol_login_prepare_otp(
            adapter,
            openai_email,
            password,
            existing_only=True,
        )
        snapshot["email"] = openai_email
        snapshot["mailbox_email"] = mailbox_email
        snapshot["mail_events"] = adapter.events
        return SessionOtpPrepareResult(
            ok=str(snapshot.get("phase") or "") in {"otp_collected", "otp_pending"},
            snapshot=snapshot,
        )
    finally:
        flow.close()


def submit_prepared_chatgpt_session_otp(
    *,
    snapshot: dict,
    proxy: str = "",
    mail_provider: OtpProvider,
    before_validate=None,
    before_skip=None,
) -> SessionOtpSubmitResult:
    config = Config()
    config.proxy = proxy or str(snapshot.get("proxy") or "") or None
    config.auth_env_flags = {
        "OAUTH_CODEX_RT_BEFORE_CALLBACK": "0",
        "OAUTH_CODEX_RT_EXCHANGE": "0",
        "OAUTH_SECONDARY_AUTHORIZE_EXCHANGE": "0",
        "OAUTH_REFRESH_ONLY": "0",
        "SKIP_OAUTH_TOKEN_EXCHANGE": "1",
    }
    flow = AuthFlow(config)
    try:
        mailbox_email = str(snapshot.get("mailbox_email") or snapshot.get("email") or "").strip()
        adapter = ExternalMailOtpAdapter(
            mail_provider,
            ensure_before_wait=False,
            mailbox_email=mailbox_email,
        )
        updated = flow.run_protocol_login_submit_prepared_otp(
            dict(snapshot),
            before_validate=before_validate,
            before_skip=before_skip,
            mail_provider=adapter,
        )
        updated["email"] = str(snapshot.get("email") or updated.get("email") or "").strip()
        updated["mailbox_email"] = mailbox_email
        updated["mail_events"] = adapter.events
        return SessionOtpSubmitResult(
            ok=str(updated.get("phase") or "") in {"otp_validated", "otp_missing"},
            snapshot=updated,
        )
    finally:
        flow.close()


def _cookie_header_from_session(flow: AuthFlow, domain_keyword: str) -> str:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        cookies = list(flow.session.cookies)
    except Exception:
        cookies = []
    for cookie in cookies:
        name = str(getattr(cookie, "name", "") or "").strip()
        value = str(getattr(cookie, "value", "") or "")
        domain = str(getattr(cookie, "domain", "") or "").lower()
        if not name or not value or domain_keyword not in domain or name in seen:
            continue
        seen.add(name)
        pairs.append((name, value))
    return "; ".join(f"{name}={value}" for name, value in pairs)


def _cookie_header_from_trace_dump(trace_dump_path: str) -> str:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        with open(trace_dump_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                response = record.get("response") if isinstance(record, dict) else {}
                if not isinstance(response, dict):
                    continue
                for raw in response.get("set_cookie_list") or []:
                    _append_openai_cookie_from_set_cookie(pairs, seen, str(raw or ""))
    except Exception:
        return ""
    return "; ".join(f"{name}={value}" for name, value in pairs)


def _append_openai_cookie_from_set_cookie(
    pairs: list[tuple[str, str]],
    seen: set[str],
    raw_set_cookie: str,
) -> None:
    if not raw_set_cookie:
        return
    raw_lc = raw_set_cookie.lower()
    if "domain=openai.com" not in raw_lc and "domain=auth.openai.com" not in raw_lc:
        return
    if "max-age=0" in raw_lc or "expires=thu, 01 jan 1970" in raw_lc:
        return
    parsed = SimpleCookie()
    try:
        parsed.load(raw_set_cookie)
    except Exception:
        return
    for name, morsel in parsed.items():
        value = morsel.value
        if not name or not value or name in seen:
            continue
        seen.add(name)
        pairs.append((name, value))
