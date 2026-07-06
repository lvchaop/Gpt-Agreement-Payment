#!/usr/bin/env python3
"""Use an existing HeroSMS email activation to run protocol login and fetch RT."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CTF_REG = ROOT / "CTF-reg"
DEFAULT_OUT = ROOT / "output" / "hero_email_protocol_rt.json"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

if str(CTF_REG) not in sys.path:
    sys.path.insert(0, str(CTF_REG))

from auth_flow import AuthFlow  # noqa: E402
from config import Config  # noqa: E402


def _resolve_path(path: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved.resolve()


def _api_key(args: argparse.Namespace) -> str:
    token = (args.api_key or "").strip()
    if token:
        return token
    return (os.environ.get(args.api_key_env) or "").strip()


def _request_hero_email(
    *,
    base_url: str,
    api_key: str,
    email_id: str,
    user_agent: str,
    timeout_s: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/emails/{urllib.parse.quote(str(email_id), safe='')}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Authorization": f"ApiKey {api_key}",
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Hero email poll failed status={exc.code}: {raw[:500]}") from exc
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Hero email poll returned {type(parsed).__name__}")
    return parsed


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _visible_text_from_html(value: str) -> str:
    text = re.sub(r"<(script|style).*?</\1>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\\r|\\n|\r|\n", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_otp(payload: dict[str, Any]) -> str:
    data = _payload_data(payload)
    for key in ("value", "code", "verification_code", "verificationCode"):
        value = str(data.get(key) or payload.get(key) or "").strip()
        if re.fullmatch(r"\d{4,8}", value):
            return value
    message = str(data.get("message") or payload.get("message") or "")
    visible = _visible_text_from_html(message)
    for pattern in (
        r"(?:验证码|驗證碼|verification code|temporary code|code)[^\d]{0,120}(\d{4,8})",
        r"(\d{4,8})[^\d]{0,80}(?:验证码|驗證碼|verification code|temporary code|code)",
    ):
        match = re.search(pattern, visible, flags=re.I)
        if match:
            return match.group(1)
    candidates = re.findall(r"(?<!\d)(\d{6})(?!\d)", visible)
    return candidates[0] if len(candidates) == 1 else ""


class HeroEmailOtpProvider:
    def __init__(
        self,
        *,
        email: str,
        email_id: str,
        api_key: str,
        base_url: str,
        user_agent: str,
        request_timeout_s: float,
        poll_interval_s: float,
        otp_timeout: int,
    ) -> None:
        self.email = email.strip().lower()
        self.email_id = str(email_id).strip()
        self.api_key = api_key
        self.base_url = base_url
        self.user_agent = user_agent
        self.request_timeout_s = request_timeout_s
        self.poll_interval_s = max(0.5, poll_interval_s)
        self.otp_timeout = otp_timeout

    def create_mailbox(self) -> str:
        return self.email

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> str:
        normalized = (email_addr or "").strip().lower()
        if normalized != self.email:
            raise RuntimeError(f"HeroEmailOtpProvider email mismatch: {normalized} != {self.email}")
        deadline = time.time() + max(1, int(timeout or self.otp_timeout or 180))
        polls = 0
        last_status = ""
        while time.time() < deadline:
            polls += 1
            payload = _request_hero_email(
                base_url=self.base_url,
                api_key=self.api_key,
                email_id=self.email_id,
                user_agent=self.user_agent,
                timeout_s=self.request_timeout_s,
            )
            data = _payload_data(payload)
            last_status = str(data.get("status") or payload.get("status") or "")
            code = _extract_otp(payload)
            if code:
                print(f"[hero-email] otp received email={self.email} id={self.email_id} polls={polls}")
                return code
            if max_polls is not None and polls >= max_polls:
                break
            time.sleep(min(self.poll_interval_s, max(0.1, deadline - time.time())))
        raise TimeoutError(
            f"Hero email OTP timeout email={self.email} id={self.email_id} last_status={last_status}"
        )

    def mark_used(self, email_addr: str) -> None:
        return None

    def mark_failed(self, email_addr: str, reason: str = "") -> None:
        return None

    def mark_unused(self, email_addr: str) -> None:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--email-id", required=True)
    parser.add_argument("--password", default="", help="Only needed if OpenAI routes to login_password")
    parser.add_argument("--config", default="", help="Optional CTF config JSON for proxy/settings")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--existing-only", action="store_true", help="Fail if the email is not an existing account")
    parser.add_argument("--api-key-env", default="HERO_SMS_API_KEY")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--base-url", default="https://hero-sms.com/api/v1")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--request-timeout-s", type=float, default=30.0)
    parser.add_argument("--poll-interval-s", type=float, default=3.0)
    parser.add_argument("--otp-timeout", type=int, default=180)
    args = parser.parse_args()

    api_key = _api_key(args)
    if not api_key:
        raise SystemExit(f"missing API key: set {args.api_key_env} or pass --api-key")

    cfg = Config.from_file(args.config) if args.config else Config()
    provider = HeroEmailOtpProvider(
        email=args.email,
        email_id=args.email_id,
        api_key=api_key,
        base_url=args.base_url,
        user_agent=args.user_agent,
        request_timeout_s=args.request_timeout_s,
        poll_interval_s=args.poll_interval_s,
        otp_timeout=args.otp_timeout,
    )

    os.environ.setdefault("OTP_TIMEOUT", str(args.otp_timeout))
    os.environ.setdefault("OAUTH_REFRESH_ONLY", "1")
    os.environ.setdefault("OAUTH_CODEX_RT_BEFORE_CALLBACK", "1")
    os.environ.setdefault("OAUTH_CODEX_RT_EXCHANGE", "1")

    flow = AuthFlow(cfg)
    result = flow.run_protocol_login(
        provider,
        args.email,
        password=args.password,
        existing_only=bool(args.existing_only),
    )
    out = _resolve_path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(
        {
            "email": result.email,
            "has_refresh_token": bool(result.refresh_token),
            "has_access_token": bool(result.access_token),
            "has_session_token": bool(result.session_token),
            "saved_to": str(out),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
