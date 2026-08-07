from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep, time
from urllib.parse import parse_qs, urlsplit

import httpx

from refactor_app.plugins.contracts import OtpMessage

_CONTEXT_CODE_RE = re.compile(
    r"(?:code(?:\s+is)?|verification|one[-\s]*time|verify|验证码|登录代码|臨時|临时)"
    r"[^0-9]{0,80}(\d{6})\b",
    re.IGNORECASE,
)
_OPENAI_CODE_RE = re.compile(r"(?:chatgpt|openai)[^0-9]{0,100}(\d{6})\b", re.IGNORECASE)
_ANY_SIX_DIGITS_RE = re.compile(r"\b(\d{6})\b")
_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_GRAPH_TOKEN_URLS = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
)


class SourceMailboxOtpError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceMailboxOtpConfig:
    email: str
    mailbox_url: str = ""
    graph_client_id: str = ""
    graph_refresh_token: str = ""
    graph_access_token: str = ""
    poll_interval_s: float = 3.0
    request_timeout_s: float = 20.0
    clock_skew_s: float = 30.0


class SourceMailboxOtpProvider:
    """Reads OTPs from the mailbox descriptor embedded in an imported account record."""

    def __init__(
        self,
        config: SourceMailboxOtpConfig,
        *,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = sleep,
        monotonic_fn: Callable[[], float] = monotonic,
        wall_time_fn: Callable[[], float] = time,
    ) -> None:
        self._config = config
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._wall_time = wall_time_fn
        self._validate_config()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=max(1.0, float(config.request_timeout_s)),
            follow_redirects=True,
            trust_env=False,
        )
        self._graph_access_token = str(config.graph_access_token or "").strip()
        self._returned_otp_messages: set[tuple[float, str]] = set()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def ensure_email(self, *, email: str) -> dict:
        self._assert_email(email)
        return {"success": True, "email": self._config.email}

    def wait_for_otp_by_email(
        self,
        *,
        email: str,
        timeout_s: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
        code_source: str = "content",
    ) -> OtpMessage:
        del code_source
        self._assert_email(email)
        timeout = max(1, int(timeout_s or 180))
        deadline = self._monotonic() + timeout
        minimum_message_ts = float(issued_after or self._wall_time()) - max(
            0.0,
            float(self._config.clock_skew_s),
        )
        poll_limit = max(1, int(max_polls)) if max_polls is not None else 0
        polls = 0
        last_error = ""

        while self._monotonic() < deadline:
            polls += 1
            try:
                message = (
                    self._read_url_mailbox()
                    if self._config.mailbox_url
                    else self._read_graph_mailbox()
                )
                received_at = _message_timestamp(message.get("received_at"))
                if received_at is None:
                    last_error = "mailbox message missing received_at"
                elif received_at < minimum_message_ts:
                    last_error = (
                        "mailbox message is older than current login OTP request: "
                        f"message_ts={received_at:.0f} min_ts={minimum_message_ts:.0f}"
                    )
                else:
                    explicit_code = str(message.get("code") or "").strip()
                    if len(explicit_code) == 6 and explicit_code.isdigit():
                        message_key = (received_at, explicit_code)
                        if message_key in self._returned_otp_messages:
                            last_error = "mailbox OTP message was already returned"
                        else:
                            self._returned_otp_messages.add(message_key)
                            return OtpMessage(
                                code=explicit_code,
                                raw={
                                    "source": str(
                                        message.get("source") or "source_mailbox"
                                    ),
                                    "received_at": str(message.get("received_at") or ""),
                                    "from": str(message.get("from") or ""),
                                    "subject": str(message.get("subject") or ""),
                                },
                            )
                    subject = str(message.get("subject") or "")
                    body = str(message.get("body") or "")
                    sender = str(message.get("from") or "")
                    code = _extract_openai_otp(subject=subject, body=body, sender=sender)
                    if code:
                        message_key = (received_at, code)
                        if message_key in self._returned_otp_messages:
                            last_error = "mailbox OTP message was already returned"
                        else:
                            self._returned_otp_messages.add(message_key)
                            return OtpMessage(
                                code=code,
                                raw={
                                    "source": str(
                                        message.get("source") or "source_mailbox"
                                    ),
                                    "received_at": str(message.get("received_at") or ""),
                                    "from": sender,
                                    "subject": subject,
                                },
                            )
                    elif not last_error:
                        last_error = "current mailbox message has no OpenAI six-digit OTP"
            except (httpx.TimeoutException, httpx.RequestError, SourceMailboxOtpError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            if poll_limit and polls >= poll_limit:
                break
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            self._sleep(min(max(0.05, self._config.poll_interval_s), remaining))

        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(
            f"source mailbox OTP timeout {timeout}s email={self._config.email}{suffix}"
        )

    def _validate_config(self) -> None:
        if not self._config.email.strip():
            raise SourceMailboxOtpError("source mailbox email is required")
        if self._config.mailbox_url:
            parsed = urlsplit(self._config.mailbox_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise SourceMailboxOtpError("source mailbox URL must be an absolute HTTP URL")
            url_email = str((parse_qs(parsed.query).get("email") or [""])[0]).strip()
            if url_email and url_email.casefold() != self._config.email.casefold():
                raise SourceMailboxOtpError("source mailbox URL email does not match account email")
            return
        if not self._config.graph_client_id or not self._config.graph_refresh_token:
            raise SourceMailboxOtpError(
                "source mailbox requires mailbox_url or Microsoft Graph client_id/refresh_token"
            )

    def _assert_email(self, email: str) -> None:
        if str(email or "").strip().casefold() != self._config.email.strip().casefold():
            raise SourceMailboxOtpError(
                f"source mailbox email mismatch: expected={self._config.email} actual={email}"
            )

    def _read_url_mailbox(self) -> dict[str, str]:
        try:
            response = self._client.get(self._config.mailbox_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise SourceMailboxOtpError(
                f"source mailbox HTTP {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            raise SourceMailboxOtpError("source mailbox response is not JSON") from exc
        if not isinstance(payload, dict):
            raise SourceMailboxOtpError("source mailbox response must be an object")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status = str(data.get("status") or payload.get("status") or "").strip().lower()
        if status and status not in {"success", "ok"}:
            message = str(data.get("message") or payload.get("message") or status)
            raise SourceMailboxOtpError(f"source mailbox returned {message[:300]}")
        return {
            "source": "mailapi_url",
            "code": str(
                data.get("code")
                or data.get("verification_code")
                or data.get("verificationCode")
                or ""
            ),
            "received_at": str(
                data.get("received_at")
                or data.get("receivedAt")
                or data.get("date")
                or ""
            ),
            "from": str(data.get("from") or data.get("sender") or ""),
            "subject": str(data.get("subject") or ""),
            "body": str(
                data.get("body")
                or data.get("content")
                or data.get("html")
                or data.get("bodyPreview")
                or ""
            ),
        }

    def _read_graph_mailbox(self) -> dict[str, str]:
        payload = self._graph_get(
            "/me/mailFolders/inbox/messages",
            params={
                "$top": "20",
                "$orderby": "receivedDateTime desc",
                "$select": "id,receivedDateTime,from,sender,subject,bodyPreview,body",
            },
        )
        fallback: dict[str, str] | None = None
        for item in payload.get("value") or []:
            if not isinstance(item, dict):
                continue
            body_payload = item.get("body") if isinstance(item.get("body"), dict) else {}
            body = str(body_payload.get("content") or item.get("bodyPreview") or "")
            if str(body_payload.get("contentType") or "").lower() == "html":
                body = _strip_html(body)
            sender = _graph_email(item.get("from")) or _graph_email(item.get("sender"))
            subject = str(item.get("subject") or "")
            searchable = f"{sender}\n{subject}\n{body[:1000]}".lower()
            if "openai" not in searchable and "chatgpt" not in searchable:
                continue
            message = {
                "source": "microsoft_graph",
                "received_at": str(item.get("receivedDateTime") or ""),
                "from": sender,
                "subject": subject,
                "body": body,
            }
            if _extract_openai_otp(subject=subject, body=body, sender=sender):
                return message
            if fallback is None:
                fallback = message
        return fallback or {
            "source": "microsoft_graph",
            "received_at": "",
            "from": "",
            "subject": "",
            "body": "",
        }

    def _graph_get(self, path: str, *, params: dict[str, str]) -> dict:
        self._ensure_graph_access_token()
        response = self._client.get(
            f"{_GRAPH_BASE_URL}{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {self._graph_access_token}",
                "Accept": "application/json",
                "Prefer": 'outlook.body-content-type="text"',
            },
        )
        if response.status_code == 401:
            self._ensure_graph_access_token(force_refresh=True)
            response = self._client.get(
                f"{_GRAPH_BASE_URL}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._graph_access_token}",
                    "Accept": "application/json",
                    "Prefer": 'outlook.body-content-type="text"',
                },
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise SourceMailboxOtpError(
                f"Microsoft Graph HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except ValueError as exc:
            raise SourceMailboxOtpError("Microsoft Graph response is not JSON") from exc
        if not isinstance(payload, dict):
            raise SourceMailboxOtpError("Microsoft Graph response must be an object")
        return payload

    def _ensure_graph_access_token(self, *, force_refresh: bool = False) -> None:
        if self._graph_access_token and not force_refresh:
            return
        errors: list[str] = []
        for token_url in _GRAPH_TOKEN_URLS:
            try:
                response = self._client.post(
                    token_url,
                    data={
                        "client_id": self._config.graph_client_id,
                        "grant_type": "refresh_token",
                        "refresh_token": self._config.graph_refresh_token,
                        "scope": _GRAPH_SCOPE,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                payload = response.json()
                access_token = str(payload.get("access_token") or "").strip()
                if not access_token:
                    errors.append(f"{urlsplit(token_url).path}: missing access_token")
                    continue
                self._graph_access_token = access_token
                return
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{urlsplit(token_url).path}: {type(exc).__name__}: {exc}")
        raise SourceMailboxOtpError(
            "Microsoft Graph refresh token exchange failed: " + " | ".join(errors)
        )


def _message_timestamp(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _strip_html(value: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?</\1>", " ", value or "")
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p\s*>", "\n", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", cleaned))


def _graph_email(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    email_address = value.get("emailAddress")
    if not isinstance(email_address, dict):
        return ""
    return str(email_address.get("address") or email_address.get("name") or "").strip()


def _extract_openai_otp(*, subject: str, body: str, sender: str) -> str:
    searchable_body = _strip_html(body)
    haystack = f"{subject}\n{searchable_body}"
    for pattern in (_CONTEXT_CODE_RE, _OPENAI_CODE_RE):
        for match in pattern.finditer(haystack):
            code = match.group(1)
            if not _reject_code(code, haystack, match.start(1)):
                return code
    if _is_openai_sender(sender):
        for match in _ANY_SIX_DIGITS_RE.finditer(searchable_body):
            code = match.group(1)
            if not _reject_code(code, searchable_body, match.start(1)):
                return code
    return ""


def _is_openai_sender(value: str) -> bool:
    address = str(value or "").split()[-1].strip("<>").lower()
    return address.endswith("@openai.com") or address.endswith(".openai.com")


def _reject_code(code: str, context: str, index: int) -> bool:
    if len(code) != 6 or not code.isdigit() or code.startswith("202"):
        return True
    if index > 0 and context[index - 1] == "#":
        return True
    before = context[max(0, index - 30) : index]
    return bool(
        re.search(
            r"(?:color|background|bgcolor|fill|stroke)\s*[:=]\s*[\"']?#?\s*$",
            before,
            re.IGNORECASE,
        )
    )
