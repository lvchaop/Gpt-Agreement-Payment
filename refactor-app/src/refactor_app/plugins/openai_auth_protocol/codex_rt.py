from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from refactor_app.plugins.mail_external_api.plugin import prepare_domain_mailbox

from .auth_flow import AuthFlow, AuthResult
from .config import Config


class OtpProvider(Protocol):
    def ensure_email(self, *, email: str) -> dict: ...

    def wait_for_otp_by_email(
        self,
        *,
        email: str,
        timeout_s: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ): ...


@dataclass(frozen=True)
class CodexRtResult:
    ok: bool
    auth_result: AuthResult
    cookie_header: str
    snapshot: dict


class ExternalMailOtpAdapter:
    def __init__(
        self,
        provider: OtpProvider,
        *,
        ensure_before_wait: bool = True,
        mailbox_email: str = "",
    ) -> None:
        self._provider = provider
        self._ensure_before_wait = ensure_before_wait
        self._mailbox_email = mailbox_email.strip()
        self.events: list[dict] = []

    def wait_for_otp(
        self,
        email: str,
        timeout: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> str:
        started = monotonic()
        lookup_email = self._mailbox_email or email
        if self._ensure_before_wait:
            self.events.append(
                {
                    "event": "mail.ensure_email.started",
                    "email": lookup_email,
                    "openai_email": email,
                }
            )
            self._provider.ensure_email(email=lookup_email)
        else:
            self.events.append(
                {
                    "event": "mail.ensure_email.skipped",
                    "email": lookup_email,
                    "openai_email": email,
                    "reason": "existing_account_email",
                }
            )
        self.events.append(
            {
                "event": "mail.wait_for_otp.started",
                "email": lookup_email,
                "openai_email": email,
                "timeout_s": timeout,
                "issued_after": issued_after,
                "max_polls": max_polls,
            }
        )
        try:
            otp = self._provider.wait_for_otp_by_email(
                email=lookup_email,
                timeout_s=timeout,
                issued_after=issued_after,
                max_polls=max_polls,
            )
        except Exception as exc:
            self.events.append(
                {
                    "event": "mail.wait_for_otp.failed",
                    "email": lookup_email,
                    "openai_email": email,
                    "elapsed_s": round(monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                }
            )
            raise
        code = str(otp.code)
        self.events.append(
            {
                "event": "mail.wait_for_otp.succeeded",
                "email": lookup_email,
                "openai_email": email,
                "elapsed_s": round(monotonic() - started, 3),
                "has_code": bool(code),
            }
        )
        return code


def acquire_codex_refresh_token(
    *,
    email: str,
    password: str,
    proxy: str = "",
    mail_provider: OtpProvider,
    trace_dump_path: str = "",
) -> CodexRtResult:
    config = Config()
    config.proxy = proxy or None
    if trace_dump_path:
        config.auth_trace_dump_enabled = True
        config.auth_trace_dump_path = trace_dump_path
    prepare_domain_mailbox(mail_provider, email=email)
    flow = AuthFlow(config)
    try:
        flow.result.email = email.strip().lower()
        flow.result.password = password
        adapter = ExternalMailOtpAdapter(mail_provider, mailbox_email=email)
        ok = flow.oauth_codex_rt_exchange(mail_provider=adapter)
        flow.result.cookie_header = flow._build_chatgpt_cookie_header()
        return CodexRtResult(
            ok=ok,
            auth_result=flow.result,
            cookie_header=flow.result.cookie_header,
            snapshot=flow.export_protocol_snapshot(mail_events=adapter.events),
        )
    finally:
        flow.close()
