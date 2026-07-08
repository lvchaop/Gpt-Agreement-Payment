"""Microsoft Graph mailbox access for Outlook account-list OTP lookup."""
from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from email_account_pool import EmailAccount, account_from_row
from imap_otp_provider import OtpMatch, extract_otp


logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_MAIL_READ_SCOPES = ("Mail.Read", "Mail.ReadWrite")
GRAPH_TOKEN_ENDPOINTS = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
)


def _has_mail_read_permission(scope: str) -> bool:
    scope_str = str(scope or "")
    return any(mail_scope in scope_str for mail_scope in GRAPH_MAIL_READ_SCOPES)


def _snippet(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:limit]


def _strip_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?</\1>", " ", value or "")
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", value))


def _parse_graph_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _email_address(value: dict | None) -> str:
    email_addr = ((value or {}).get("emailAddress") or {})
    address = str(email_addr.get("address") or "").strip()
    name = str(email_addr.get("name") or "").strip()
    if name and address:
        return f"{name} <{address}>"
    return address or name


class GraphOtpProvider:
    def __init__(self, account: EmailAccount | dict, mark_seen: bool = False):
        self.account = account if isinstance(account, EmailAccount) else account_from_row(account)
        self.mark_seen = mark_seen
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _ensure_access_token(self, *, force_refresh: bool = False) -> None:
        if self.account.access_token and not force_refresh:
            return
        if not self.account.refresh_token:
            raise RuntimeError(f"{self.account.email} 缺 Microsoft Graph refresh_token/access_token")
        if not self.account.account_id:
            raise RuntimeError(
                f"{self.account.email} 有 refresh_token 但缺 client_id/id；"
                "格式用 email----password----client_id----refresh_token"
            )

        errors: list[str] = []
        payload = {
            "client_id": self.account.account_id,
            "grant_type": "refresh_token",
            "refresh_token": self.account.refresh_token,
            "scope": GRAPH_SCOPE,
        }
        body = urllib.parse.urlencode(payload).encode()
        for endpoint in GRAPH_TOKEN_ENDPOINTS:
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with self._opener.open(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                access_token = str(data.get("access_token") or "").strip()
                if not access_token:
                    errors.append(f"{endpoint}: token response missing access_token")
                    continue
                scope = str(data.get("scope") or "")
                if not _has_mail_read_permission(scope):
                    errors.append(
                        f"{endpoint}: token scope missing Mail.Read/Mail.ReadWrite scope={scope}"
                    )
                    continue
                self.account.access_token = access_token
                new_refresh = str(data.get("refresh_token") or "").strip()
                if new_refresh:
                    self.account.refresh_token = new_refresh
                logger.info(
                    "Microsoft Graph refresh token exchange ok email=%s endpoint=%s expires_in=%s scope=%s",
                    self.account.email,
                    endpoint,
                    data.get("expires_in", ""),
                    data.get("scope", ""),
                )
                return
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                try:
                    err = json.loads(raw)
                    msg = f"{err.get('error', e.code)}: {err.get('error_description', raw)}"
                except Exception:
                    msg = raw
                errors.append(f"{endpoint}: HTTP {e.code} {msg[:500]}")
            except Exception as e:
                errors.append(f"{endpoint}: {e}")
        raise RuntimeError(
            f"{self.account.email} Graph refresh_token 换 access_token 失败: "
            + " | ".join(errors)
        )

    def _graph_get(self, path: str, params: dict[str, str]) -> dict:
        self._ensure_access_token()
        query = urllib.parse.urlencode(params)
        url = f"{GRAPH_BASE}{path}?{query}" if query else f"{GRAPH_BASE}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.account.access_token}",
                "Accept": "application/json",
                "Prefer": 'outlook.body-content-type="text"',
            },
            method="GET",
        )
        try:
            with self._opener.open(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and self.account.refresh_token:
                self._ensure_access_token(force_refresh=True)
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.account.access_token}",
                        "Accept": "application/json",
                        "Prefer": 'outlook.body-content-type="text"',
                    },
                    method="GET",
                )
                with self._opener.open(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Graph GET {path} → HTTP {e.code}: {raw[:500]}") from e

    def _recent_openai_messages(self, limit: int = 20) -> list[dict]:
        data = self._graph_get(
            "/me/mailFolders/inbox/messages",
            {
                "$top": str(max(1, limit)),
                "$orderby": "receivedDateTime desc",
                "$select": "id,receivedDateTime,from,sender,subject,bodyPreview,body",
            },
        )
        out: list[dict] = []
        for item in data.get("value") or []:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject") or "")
            from_value = _email_address(item.get("from")) or _email_address(item.get("sender"))
            body_obj = item.get("body") if isinstance(item.get("body"), dict) else {}
            body = str(body_obj.get("content") or item.get("bodyPreview") or "")
            if str(body_obj.get("contentType") or "").lower() == "html":
                body = _strip_html(body)
            searchable = f"{from_value}\n{subject}\n{body[:1000]}".lower()
            if "openai" not in searchable and "chatgpt" not in searchable:
                continue
            received = str(item.get("receivedDateTime") or "")
            out.append({
                "uid": str(item.get("id") or ""),
                "datetime": received,
                "_datetime": _parse_graph_datetime(received),
                "from": from_value,
                "subject": subject,
                "body": body,
            })
        return out

    def list_messages(self, limit: int = 10) -> list[dict]:
        messages = self._recent_openai_messages(limit=limit)
        return [
            {
                "uid": item.get("uid", ""),
                "date": item.get("datetime", ""),
                "from": item.get("from", ""),
                "subject": item.get("subject", ""),
                "snippet": _snippet(item.get("body", "")),
            }
            for item in messages[:limit]
        ]

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 180,
        issued_after: Optional[float] = None,
        poll_interval_s: float = 5.0,
    ) -> str:
        return self.wait_for_otp_match(
            email_addr,
            timeout=timeout,
            issued_after=issued_after,
            poll_interval_s=poll_interval_s,
        ).otp

    def wait_for_otp_match(
        self,
        email_addr: str,
        timeout: int = 180,
        issued_after: Optional[float] = None,
        poll_interval_s: float = 5.0,
    ) -> OtpMatch:
        deadline = time.time() + timeout
        issued_after = issued_after or time.time()
        last_error = ""
        while time.time() < deadline:
            try:
                messages = self._recent_openai_messages(limit=20)
                for item in messages:
                    dt = item.get("_datetime")
                    if dt:
                        msg_ts = dt.timestamp()
                        if msg_ts < issued_after - 30:
                            continue
                    otp = extract_otp(
                        item.get("subject", ""),
                        item.get("body", ""),
                        item.get("from", ""),
                    )
                    if otp:
                        return OtpMatch(
                            otp=otp,
                            uid=item.get("uid", ""),
                            date=item.get("datetime", ""),
                            from_=item.get("from", ""),
                            subject=item.get("subject", ""),
                            source="graph",
                        )
            except Exception as e:
                last_error = str(e)
                raise
            time.sleep(max(1.0, poll_interval_s))
        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(f"Graph 等 OTP 超时 {timeout}s email={email_addr}{suffix}")
