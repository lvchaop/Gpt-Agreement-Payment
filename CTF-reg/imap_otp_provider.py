"""IMAP mailbox access for custom Gmail / Outlook account lists."""
from __future__ import annotations

import email
import base64
import html
import imaplib
import json
import logging
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional

from email_account_pool import EmailAccount, account_from_row


logger = logging.getLogger(__name__)

CONTEXT_RE = re.compile(
    r"(?:code(?:\s+is)?|verification|one[-\s]*time|verify|验证码|登录代码|臨時|临时)"
    r"[^0-9]{0,80}(\d{6})\b",
    re.I,
)
CHATGPT_RE = re.compile(r"(?:chatgpt|openai)[^0-9]{0,100}(\d{6})\b", re.I)
ANY_6_RE = re.compile(r"\b(\d{6})\b")
OUTLOOK_PASSWORD_HOST_FALLBACKS = ("imap-mail.outlook.com",)
OUTLOOK_IMAP_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
MS_TOKEN_ENDPOINTS = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
)


@dataclass
class MailSummary:
    uid: str
    date: str
    from_: str
    subject: str
    snippet: str

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "date": self.date,
            "from": self.from_,
            "subject": self.subject,
            "snippet": self.snippet,
        }


@dataclass
class OtpMatch:
    otp: str
    uid: str = ""
    date: str = ""
    from_: str = ""
    subject: str = ""
    source: str = "imap_list"

    def to_kv_payload(self) -> dict:
        return {
            "otp": self.otp,
            "from": self.from_,
            "subject": self.subject,
            "source": self.source,
            "uid": self.uid,
            "mailbox_ts": self.date,
        }


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _message_datetime(msg: Message) -> Optional[datetime]:
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _plain_text_from_msg(msg: Message, limit: int = 12000) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype not in ("text/plain", "text/html"):
                continue
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if ctype == "text/html":
                    text = _html_to_text(text)
                parts.append(text)
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                text = _html_to_text(text)
            parts.append(text)
        except Exception:
            pass
    joined = "\n".join(parts)
    return joined[:limit]


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p\s*>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", s))


def _snippet(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:limit]


def _is_openai_sender(from_value: str) -> bool:
    addr = (from_value or "").split()[-1].strip("<>").lower()
    if addr.endswith("@tm.openai.com") or addr.endswith(".tm.openai.com"):
        return True
    return addr.endswith("@openai.com") or addr.endswith(".openai.com")


def _reject_candidate(code: str, context: str, idx: int = -1) -> bool:
    if not code or len(code) != 6 or not code.isdigit():
        return True
    # Common false positive seen in localized templates: 202605 from 2026-05.
    if code.startswith("202"):
        return True
    if idx > 0 and context[idx - 1] == "#":
        return True
    before = context[max(0, idx - 30):idx] if idx >= 0 else ""
    if re.search(r"(?:color|background|bgcolor|fill|stroke)\s*[:=]\s*[\"']?#?\s*$", before, re.I):
        return True
    return False


def extract_otp(subject: str, body: str, from_value: str = "") -> str:
    haystack = f"{subject}\n{body}"
    patterns = (CONTEXT_RE, CHATGPT_RE)
    for pattern in patterns:
        for m in pattern.finditer(haystack):
            code = m.group(1)
            if not _reject_candidate(code, haystack, m.start(1)):
                return code

    # Only allow fallback for OpenAI senders and reject date-like/template-like
    # values. This is intentionally conservative.
    if _is_openai_sender(from_value):
        for m in ANY_6_RE.finditer(body):
            code = m.group(1)
            if not _reject_candidate(code, body, m.start(1)):
                return code
    return ""


def _login_error_hint(account: EmailAccount, raw_error: str) -> str:
    provider = (account.provider or "").lower()
    base = f"{account.email} IMAP 登录失败: {raw_error}"
    if provider == "gmail":
        return (
            f"{base}; Gmail 通常不能用普通 Google 密码登录 IMAP，"
            "请使用 16 位 App Password，并确认账号允许 IMAP。"
        )
    if provider == "outlook":
        return (
            f"{base}; Outlook.com 需要在网页版设置里开启 IMAP，"
            "但账号密码模式还取决于 Microsoft 是否允许 Basic/Auth。"
            "若必须走账号密码，请优先使用 Microsoft App Password，"
            "并在 account.live.com/activity 里把最近 IMAP 登录标记为本人操作。"
        )
    return (
        f"{base}; 请确认邮箱密码、IMAP 主机、端口和 SSL 设置正确，"
        "自定义邮箱 CSV 可填写 imap_host, imap_port, imap_ssl。"
    )


class ImapOtpProvider:
    def __init__(self, account: EmailAccount | dict, mark_seen: bool = False):
        self.account = account if isinstance(account, EmailAccount) else account_from_row(account)
        self.mark_seen = mark_seen

    def _candidate_hosts(self) -> list[str]:
        hosts = [self.account.imap_host]
        if (self.account.provider or "").lower() == "outlook":
            for host in OUTLOOK_PASSWORD_HOST_FALLBACKS:
                if host and host not in hosts:
                    hosts.append(host)
        return hosts

    def _open_imap(self, host: str) -> imaplib.IMAP4:
        if self.account.imap_ssl:
            return imaplib.IMAP4_SSL(host, self.account.imap_port)
        return imaplib.IMAP4(host, self.account.imap_port)

    def _capabilities(self, imap: imaplib.IMAP4) -> str:
        try:
            typ, data = imap.capability()
            if typ != "OK":
                return typ
            parts: list[str] = []
            for item in data or []:
                if isinstance(item, bytes):
                    parts.append(item.decode(errors="replace"))
                else:
                    parts.append(str(item))
            return " ".join(parts)
        except Exception:
            return ""

    def _password_variants(self) -> list[tuple[str, str]]:
        password = self.account.mail_password
        variants = [("raw", password)]
        compact = re.sub(r"\s+", "", password)
        if compact and compact != password:
            variants.append(("compact", compact))
        return variants

    def _ensure_access_token(self) -> None:
        if self.account.access_token:
            return
        if not self.account.refresh_token:
            return
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
            "scope": OUTLOOK_IMAP_SCOPE,
        }
        body = urllib.parse.urlencode(payload).encode()
        for endpoint in MS_TOKEN_ENDPOINTS:
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                access_token = (data.get("access_token") or "").strip()
                if not access_token:
                    errors.append(f"{endpoint}: token response missing access_token")
                    continue
                self.account.access_token = access_token
                new_refresh = (data.get("refresh_token") or "").strip()
                if new_refresh:
                    self.account.refresh_token = new_refresh
                logger.info(
                    "Microsoft refresh token exchange ok email=%s endpoint=%s expires_in=%s scope=%s",
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
            f"{self.account.email} refresh_token 换 access_token 失败: "
            + " | ".join(errors)
        )

    def _login_with_method(self, imap: imaplib.IMAP4, method: str, password: str) -> None:
        if method == "xoauth2_ir":
            auth = f"user={self.account.email}\x01auth=Bearer {self.account.access_token}\x01\x01".encode()
            payload = base64.b64encode(auth).decode("ascii")
            typ, data = imap._simple_command("AUTHENTICATE", "XOAUTH2", payload)
            if typ != "OK":
                msg = data[-1] if data else typ
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="replace")
                raise imaplib.IMAP4.error(msg)
            imap.state = "AUTH"
            return
        if method == "xoauth2":
            auth = f"user={self.account.email}\x01auth=Bearer {self.account.access_token}\x01\x01".encode()
            imap.authenticate("XOAUTH2", lambda _: auth)
            return
        if method == "plain_user_ir":
            auth = f"{self.account.email}\0{self.account.email}\0{password}".encode()
            payload = base64.b64encode(auth).decode("ascii")
            typ, data = imap._simple_command("AUTHENTICATE", "PLAIN", payload)
            if typ != "OK":
                msg = data[-1] if data else typ
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="replace")
                raise imaplib.IMAP4.error(msg)
            imap.state = "AUTH"
            return
        if method == "plain_ir":
            auth = f"\0{self.account.email}\0{password}".encode()
            payload = base64.b64encode(auth).decode("ascii")
            typ, data = imap._simple_command("AUTHENTICATE", "PLAIN", payload)
            if typ != "OK":
                msg = data[-1] if data else typ
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="replace")
                raise imaplib.IMAP4.error(msg)
            imap.state = "AUTH"
            return
        if method == "plain":
            auth = f"\0{self.account.email}\0{password}".encode()
            imap.authenticate("PLAIN", lambda _: auth)
            return
        if method == "plain_user":
            auth = f"{self.account.email}\0{self.account.email}\0{password}".encode()
            imap.authenticate("PLAIN", lambda _: auth)
            return
        if method == "auth_login":
            def _auth_login(challenge: bytes) -> bytes:
                text = (challenge or b"").decode(errors="replace").lower()
                if "user" in text or "login" in text:
                    return self.account.email.encode()
                return password.encode()

            imap.authenticate("LOGIN", _auth_login)
            return
        imap.login(self.account.email, password)

    def _logout_quietly(self, imap: imaplib.IMAP4 | None) -> None:
        if imap is None:
            return
        try:
            imap.logout()
        except Exception:
            pass

    def _connect(self) -> imaplib.IMAP4:
        if not self.account.imap_host:
            raise RuntimeError(f"{self.account.email} 缺 imap_host")
        if not self.account.mail_password and not self.account.access_token:
            self._ensure_access_token()
        else:
            self._ensure_access_token()
        if not self.account.mail_password and not self.account.access_token:
            raise RuntimeError(
                f"{self.account.email} 缺邮箱密码或 access_token；"
                "格式用 email----password 或 email----password----client_id----refresh_token"
            )
        auth_errors: list[str] = []
        conn_errors: list[str] = []
        last_exc: Exception | None = None
        methods: list[str] = []
        if self.account.access_token:
            methods.extend(("xoauth2_ir", "xoauth2"))
        if self.account.mail_password:
            methods.extend(("login", "plain_ir", "plain_user_ir", "plain", "plain_user", "auth_login"))
        for host in self._candidate_hosts():
            for method in methods:
                password_variants = self._password_variants() if method not in ("xoauth2_ir", "xoauth2") else [("token", "")]
                for password_label, password in password_variants:
                    imap: imaplib.IMAP4 | None = None
                    capabilities = ""
                    try:
                        imap = self._open_imap(host)
                        capabilities = self._capabilities(imap)
                        self._login_with_method(imap, method, password)
                        logger.info(
                            "IMAP login ok email=%s host=%s method=%s password_variant=%s capabilities=%s",
                            self.account.email,
                            host,
                            method,
                            password_label,
                            capabilities,
                        )
                        return imap
                    except imaplib.IMAP4.error as e:
                        last_exc = e
                        auth_errors.append(
                            f"{host}/{method}/{password_label}: {e}; capabilities={capabilities or '-'}"
                        )
                        self._logout_quietly(imap)
                    except (OSError, socket.timeout, ssl.SSLError) as e:
                        last_exc = e
                        conn_errors.append(f"{host}/{method}/{password_label}: {e}")
                        self._logout_quietly(imap)
        if auth_errors:
            raise RuntimeError(_login_error_hint(self.account, " | ".join(auth_errors))) from last_exc
        raise RuntimeError(
            f"{self.account.email} 连接 IMAP 失败: {' | '.join(conn_errors)}; "
            f"请检查 imap_host={self.account.imap_host} port={self.account.imap_port}"
        ) from last_exc

    def list_messages(self, limit: int = 10, mailbox: str = "INBOX") -> list[dict]:
        imap = self._connect()
        try:
            imap.select(mailbox, readonly=not self.mark_seen)
            typ, data = imap.search(None, "ALL")
            if typ != "OK":
                raise RuntimeError(f"IMAP search failed: {typ}")
            ids = (data[0] or b"").split()
            out: list[dict] = []
            for msg_id in reversed(ids[-max(1, limit * 3):]):
                if len(out) >= limit:
                    break
                typ, fetched = imap.fetch(msg_id, "(RFC822)")
                if typ != "OK" or not fetched:
                    continue
                raw = next((item[1] for item in fetched if isinstance(item, tuple)), b"")
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                subject = _decode_header_value(msg.get("Subject", ""))
                from_value = _decode_header_value(msg.get("From", ""))
                body = _plain_text_from_msg(msg)
                dt = _message_datetime(msg)
                out.append(
                    MailSummary(
                        uid=msg_id.decode(errors="replace"),
                        date=dt.isoformat() if dt else (msg.get("Date", "") or ""),
                        from_=from_value,
                        subject=subject,
                        snippet=_snippet(body),
                    ).to_dict()
                )
            return out
        finally:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass

    def _otp_mailboxes(self, imap: imaplib.IMAP4) -> list[str]:
        mailboxes = ["INBOX"]
        common = ("Junk", "Junk Email", "Spam")
        discovered: list[str] = []
        try:
            typ, rows = imap.list()
            if typ == "OK":
                for row in rows or []:
                    text = row.decode(errors="replace") if isinstance(row, bytes) else str(row)
                    quoted = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
                    name = quoted[-1].replace(r'\"', '"') if quoted else text.rsplit(" ", 1)[-1]
                    name = name.strip().strip('"')
                    lower = name.lower()
                    if name and (
                        "junk" in lower
                        or "spam" in lower
                        or "垃圾" in lower
                    ):
                        discovered.append(name)
        except Exception as e:
            logger.info("IMAP list mailbox failed email=%s: %s", self.account.email, e)

        for name in [*discovered, *common]:
            if name and name not in mailboxes:
                mailboxes.append(name)
        return mailboxes

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
                        logger.info(
                            "IMAP OTP found email=%s mailbox=%s uid=%s subject=%r",
                            email_addr,
                            item.get("mailbox", "?"),
                            item.get("uid", ""),
                            item.get("subject", "")[:80],
                        )
                        return OtpMatch(
                            otp=otp,
                            uid=item.get("uid", ""),
                            date=item.get("datetime", ""),
                            from_=item.get("from", ""),
                            subject=item.get("subject", ""),
                        )
            except Exception as e:
                last_error = str(e)
            time.sleep(max(1.0, poll_interval_s))
        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(f"IMAP 等 OTP 超时 {timeout}s email={email_addr}{suffix}")

    def _recent_openai_messages(self, limit: int = 20) -> list[dict]:
        imap = self._connect()
        try:
            mailboxes = self._otp_mailboxes(imap)
            logger.info(
                "IMAP OTP scan email=%s mailboxes=%s",
                self.account.email,
                ",".join(mailboxes),
            )
            out: list[dict] = []
            for mailbox in mailboxes:
                try:
                    typ, _ = imap.select(mailbox, readonly=not self.mark_seen)
                    if typ != "OK":
                        logger.info(
                            "IMAP select mailbox failed email=%s mailbox=%s status=%s",
                            self.account.email,
                            mailbox,
                            typ,
                        )
                        continue
                    # Search broad, then filter in Python. Provider-specific FROM
                    # search syntax can vary with encoded display names.
                    typ, data = imap.search(None, "ALL")
                    if typ != "OK":
                        logger.info(
                            "IMAP search failed email=%s mailbox=%s status=%s",
                            self.account.email,
                            mailbox,
                            typ,
                        )
                        continue
                    ids = (data[0] or b"").split()
                except Exception as e:
                    logger.info(
                        "IMAP scan mailbox failed email=%s mailbox=%s error=%s",
                        self.account.email,
                        mailbox,
                        e,
                    )
                    continue

                for msg_id in reversed(ids[-max(1, limit * 4):]):
                    typ, fetched = imap.fetch(msg_id, "(RFC822)")
                    if typ != "OK" or not fetched:
                        continue
                    raw = next((item[1] for item in fetched if isinstance(item, tuple)), b"")
                    if not raw:
                        continue
                    msg = email.message_from_bytes(raw)
                    subject = _decode_header_value(msg.get("Subject", ""))
                    from_value = _decode_header_value(msg.get("From", ""))
                    body = _plain_text_from_msg(msg)
                    searchable = f"{from_value}\n{subject}\n{body[:1000]}".lower()
                    if "openai" not in searchable and "chatgpt" not in searchable:
                        continue
                    dt = _message_datetime(msg)
                    out.append({
                        "mailbox": mailbox,
                        "uid": msg_id.decode(errors="replace"),
                        "datetime": (dt.isoformat() if dt else ""),
                        "_datetime": dt,
                        "from": from_value,
                        "subject": subject,
                        "body": body,
                    })
            out.sort(
                key=lambda item: item.get("_datetime") or datetime.fromtimestamp(0, timezone.utc),
                reverse=True,
            )
            return out[:limit]
        finally:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass
