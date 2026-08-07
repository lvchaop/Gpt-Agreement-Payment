from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from time import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import (
    BackfillSessionWorkflow,
    ensure_account_proxy_url,
)
from refactor_app.infrastructure.db.models import (
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.mail_external_api.plugin import (
    ExternalMailApiPlugin,
    prepare_domain_mailbox,
)
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClientError,
    decode_access_token_claims,
)
from refactor_app.plugins.source_mailbox_otp import (
    SourceMailboxOtpConfig,
    SourceMailboxOtpProvider,
)

ACCOUNT_EMAIL_CHANGE_MODE_MAPPED = "mapped_csv"
ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM = "source_jsonl_auto_claim"
_EMAIL_ALREADY_LINKED_MESSAGE = "Email already linked to another account"


class AccountEmailChangeError(RuntimeError):
    pass


class AccountEmailChangeCsvError(ValueError):
    pass


class AccountEmailChangeSourceError(ValueError):
    pass


@dataclass(frozen=True)
class AccountEmailChangePair:
    row_number: int
    old_mail: str
    new_mail: str


@dataclass(frozen=True)
class AccountEmailChangeSource:
    row_number: int
    source_db_id: str
    email: str
    phone_number: str
    openai_user_id: str
    chatgpt_account_id: str
    access_token: str
    session_token: str
    cookie_header: str
    password: str
    device_id: str
    csrf_token: str
    mailbox_url: str
    mailbox_client_id: str
    mailbox_refresh_token: str
    mailbox_access_token: str
    created_at: datetime | None
    last_used_at: datetime | None


@dataclass(frozen=True)
class AccountEmailChangeInput:
    user_account_id: str
    old_mail: str
    new_mail: str = ""
    otp_timeout_s: int = 180
    mode: str = ACCOUNT_EMAIL_CHANGE_MODE_MAPPED
    mail_provider: str = "outlook"
    project_key: str = ""
    caller_id: str = "refactor-app-protocol-registration"
    email_domain: str = ""
    source_mailbox_url: str = ""
    source_mailbox_client_id: str = ""
    source_mailbox_refresh_token: str = ""
    source_mailbox_access_token: str = ""


def parse_account_email_change_csv(csv_text: str) -> list[AccountEmailChangePair]:
    source = str(csv_text or "").lstrip("\ufeff")
    if not source.strip():
        raise AccountEmailChangeCsvError("CSV is empty")

    reader = csv.DictReader(StringIO(source))
    field_names = list(reader.fieldnames or [])
    canonical = {str(name or "").strip().lower(): name for name in field_names}
    missing = [name for name in ("old_mail", "new_mail") if name not in canonical]
    if missing:
        raise AccountEmailChangeCsvError(f"CSV missing required columns: {', '.join(missing)}")

    pairs: list[AccountEmailChangePair] = []
    errors: list[str] = []
    old_seen: dict[str, int] = {}
    new_seen: dict[str, int] = {}
    old_key = canonical["old_mail"]
    new_key = canonical["new_mail"]
    for row_number, row in enumerate(reader, start=2):
        old_mail = str(row.get(old_key) or "").strip()
        new_mail = str(row.get(new_key) or "").strip()
        if not old_mail and not new_mail:
            continue
        if not old_mail or not new_mail:
            errors.append(f"row {row_number}: old_mail and new_mail are both required")
            continue
        old_normalized = old_mail.casefold()
        new_normalized = new_mail.casefold()
        if old_normalized == new_normalized:
            errors.append(f"row {row_number}: old_mail and new_mail must differ")
            continue
        if old_normalized in old_seen:
            errors.append(
                f"row {row_number}: duplicate old_mail from row {old_seen[old_normalized]}"
            )
            continue
        if new_normalized in new_seen:
            errors.append(
                f"row {row_number}: duplicate new_mail from row {new_seen[new_normalized]}"
            )
            continue
        old_seen[old_normalized] = row_number
        new_seen[new_normalized] = row_number
        pairs.append(
            AccountEmailChangePair(
                row_number=row_number,
                old_mail=old_mail,
                new_mail=new_mail,
            )
        )

    overlap = sorted(set(old_seen) & set(new_seen))
    if overlap:
        errors.append("old_mail and new_mail sets overlap: " + ", ".join(overlap[:10]))
    if errors:
        raise AccountEmailChangeCsvError("; ".join(errors[:20]))
    if not pairs:
        raise AccountEmailChangeCsvError("CSV has no account email pairs")
    return pairs


def parse_account_email_change_source_jsonl(
    source_text: str,
    *,
    now: datetime | None = None,
) -> list[AccountEmailChangeSource]:
    source = str(source_text or "").lstrip("\ufeff")
    if not source.strip():
        raise AccountEmailChangeSourceError("account source file is empty")

    del now
    records: list[AccountEmailChangeSource] = []
    errors: list[str] = []
    seen_emails: dict[str, int] = {}
    seen_user_ids: dict[str, int] = {}
    seen_account_ids: dict[str, int] = {}
    for row_number, line in enumerate(source.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {row_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"line {row_number}: account record must be a JSON object")
            continue

        platform = str(payload.get("platform") or "").strip()
        email = str(payload.get("email") or "").strip()
        access_token = str(payload.get("access_token") or "").strip()
        openai_user_id = str(payload.get("chatgpt_user_id") or "").strip()
        chatgpt_account_id = str(payload.get("chatgpt_account_id") or "").strip()
        required = {
            "email": email,
            "access_token": access_token,
            "chatgpt_user_id": openai_user_id,
            "chatgpt_account_id": chatgpt_account_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            errors.append(f"line {row_number}: missing {', '.join(missing)}")
            continue
        if platform != "chatgpt":
            errors.append(f"line {row_number}: unsupported platform {platform!r}")
            continue

        try:
            claims = decode_access_token_claims(access_token)
        except Exception as exc:
            errors.append(f"line {row_number}: invalid access_token: {type(exc).__name__}: {exc}")
            continue
        raw_claims = claims.raw if isinstance(claims.raw, dict) else {}
        profile = raw_claims.get("https://api.openai.com/profile") or {}
        profile_email = str(profile.get("email") or "") if isinstance(profile, dict) else ""
        token_client_id = str(raw_claims.get("client_id") or "")
        source_client_id = str(payload.get("client_id") or "").strip()
        identity_errors: list[str] = []
        if claims.account_id != openai_user_id:
            identity_errors.append("chatgpt_user_id does not match access_token")
        if claims.token_chatgpt_account_id != chatgpt_account_id:
            identity_errors.append("chatgpt_account_id does not match access_token")
        if profile_email.casefold() != email.casefold():
            identity_errors.append("email does not match access_token profile")
        if source_client_id and token_client_id and source_client_id != token_client_id:
            identity_errors.append("client_id does not match access_token")
        for field_name in ("login_identity", "account_claims_email"):
            field_value = str(payload.get(field_name) or "").strip()
            if field_value and field_value.casefold() != email.casefold():
                identity_errors.append(f"{field_name} does not match email")
        if identity_errors:
            errors.append(f"line {row_number}: {', '.join(identity_errors)}")
            continue

        mailbox = payload.get("mailbox")
        if not isinstance(mailbox, dict):
            mailbox = {}
        mailbox_url = str(payload.get("mailbox_url") or mailbox.get("mailapi_url") or "").strip()
        mailbox_client_id = str(mailbox.get("client_id") or "").strip()
        mailbox_refresh_token = str(mailbox.get("refresh_token") or "").strip()
        mailbox_access_token = str(mailbox.get("access_token") or "").strip()
        if not mailbox_url and not (mailbox_client_id and mailbox_refresh_token):
            errors.append(
                f"line {row_number}: missing mailbox_url or Microsoft Graph client_id/refresh_token"
            )
            continue

        email_key = email.casefold()
        duplicate = _duplicate_source_error(
            row_number=row_number,
            email_key=email_key,
            openai_user_id=openai_user_id,
            chatgpt_account_id=chatgpt_account_id,
            seen_emails=seen_emails,
            seen_user_ids=seen_user_ids,
            seen_account_ids=seen_account_ids,
        )
        if duplicate:
            errors.append(duplicate)
            continue
        seen_emails[email_key] = row_number
        seen_user_ids[openai_user_id] = row_number
        seen_account_ids[chatgpt_account_id] = row_number
        records.append(
            AccountEmailChangeSource(
                row_number=row_number,
                source_db_id=str(payload.get("db_id") or "").strip(),
                email=email,
                phone_number=str(payload.get("phone") or "").strip(),
                openai_user_id=openai_user_id,
                chatgpt_account_id=chatgpt_account_id,
                access_token=access_token,
                session_token=str(payload.get("session_token") or "").strip(),
                cookie_header=str(payload.get("cookie_header") or "").strip(),
                password=str(payload.get("password") or ""),
                device_id=str(payload.get("device_id") or "").strip(),
                csrf_token=str(payload.get("csrf_token") or "").strip(),
                mailbox_url=mailbox_url,
                mailbox_client_id=mailbox_client_id,
                mailbox_refresh_token=mailbox_refresh_token,
                mailbox_access_token=mailbox_access_token,
                created_at=_timestamp_value(payload.get("created_at")),
                last_used_at=_timestamp_value(payload.get("last_used")),
            )
        )

    if errors:
        raise AccountEmailChangeSourceError("; ".join(errors[:20]))
    if not records:
        raise AccountEmailChangeSourceError("account source file has no records")
    return records


def _duplicate_source_error(
    *,
    row_number: int,
    email_key: str,
    openai_user_id: str,
    chatgpt_account_id: str,
    seen_emails: dict[str, int],
    seen_user_ids: dict[str, int],
    seen_account_ids: dict[str, int],
) -> str:
    if email_key in seen_emails:
        return f"line {row_number}: duplicate email from line {seen_emails[email_key]}"
    if openai_user_id in seen_user_ids:
        return (
            f"line {row_number}: duplicate chatgpt_user_id from line "
            f"{seen_user_ids[openai_user_id]}"
        )
    if chatgpt_account_id in seen_account_ids:
        return (
            f"line {row_number}: duplicate chatgpt_account_id from line "
            f"{seen_account_ids[chatgpt_account_id]}"
        )
    return ""


def _timestamp_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
        parsed = datetime.fromtimestamp(timestamp, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return parsed


class AccountEmailChangeWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
        openai_provider: OpenAIChatGPTProvider,
        backfill_session: Callable[..., str] | None = None,
        totp_code_resolver: Callable[[str], str] | None = None,
        proxy_resolver: Callable[..., str] | None = None,
        source_mail_provider_factory: Callable[[AccountEmailChangeInput], SourceMailboxOtpProvider]
        | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._openai_provider = openai_provider
        self._backfill_session = backfill_session
        self._totp_code_resolver = totp_code_resolver
        self._proxy_resolver = proxy_resolver or ensure_account_proxy_url
        self._source_mail_provider_factory = source_mail_provider_factory or _source_mail_provider

    def run(
        self,
        input_: AccountEmailChangeInput,
        *,
        work_id: str = "",
        run_id: str = "",
    ) -> dict:
        if input_.mode == ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM:
            return self._run_auto_claim(input_, work_id=work_id, run_id=run_id)
        if input_.mode != ACCOUNT_EMAIL_CHANGE_MODE_MAPPED:
            raise AccountEmailChangeError(f"unsupported email change mode: {input_.mode}")

        old_mail = input_.old_mail.strip()
        new_mail = input_.new_mail.strip()
        if not input_.user_account_id:
            raise AccountEmailChangeError("user_account_id is required")
        if not old_mail or not new_mail:
            raise AccountEmailChangeError("old_mail and new_mail are required")
        if old_mail.casefold() == new_mail.casefold():
            raise AccountEmailChangeError("old_mail and new_mail must differ")

        self._assert_account_matches(input_.user_account_id, old_mail)
        self._write_event(
            run_id,
            "account_email_change.started",
            "account email change started",
            {
                "user_account_id": input_.user_account_id,
                "old_mail": old_mail,
                "new_mail": new_mail,
            },
        )
        self._run_session_backfill(user_account_id=input_.user_account_id, run_id=run_id)
        self._mark_login_succeeded(input_.user_account_id)
        proxy_url = self._proxy_resolver(
            self._session_factory,
            input_.user_account_id,
            bind_reason="account_email_change",
        )
        account = self._load_account(input_.user_account_id)
        cookie_header = _web_session_cookie_header(account)
        if not cookie_header:
            raise AccountEmailChangeError("account web session cookie is empty after login")

        session_payload = self._openai_provider.fetch_web_session_payload(
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
        access_token = _session_access_token(session_payload)
        if not access_token:
            raise AccountEmailChangeError("web session response missing accessToken")
        before_claims = self._openai_provider.decode_access_token(access_token)
        before_user_id = str(before_claims.account_id or "").strip()
        if account.openai_user_id and before_user_id != account.openai_user_id:
            raise AccountEmailChangeError(
                "web session identity mismatch before email change: "
                f"expected={account.openai_user_id} actual={before_user_id}"
            )

        eligibility = self._openai_provider.check_change_email_eligibility(
            access_token=access_token,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
        if eligibility.get("eligible") is not True:
            raise AccountEmailChangeError(
                "account is not eligible for email change: "
                f"{json.dumps(eligibility, ensure_ascii=False)[:1000]}"
            )

        prepare_domain_mailbox(self._mail_provider, email=new_mail)
        issued_after = time()
        begin_result = self._openai_provider.begin_change_email(
            access_token=access_token,
            cookie_header=cookie_header,
            email=new_mail,
            proxy_url=proxy_url,
        )
        _require_change_email_success(begin_result, stage="begin")
        self._write_event(
            run_id,
            "account_email_change.otp_sent",
            "email change OTP requested",
            {
                "user_account_id": input_.user_account_id,
                "new_mail": new_mail,
                "http_status": begin_result.get("http_status"),
            },
        )
        otp = self._mail_provider.wait_for_otp_by_email(
            email=new_mail,
            timeout_s=max(1, int(input_.otp_timeout_s or 180)),
            issued_after=issued_after,
            code_source="all",
        )
        code = str(otp.code or "").strip()
        if len(code) != 6 or not code.isdigit():
            raise AccountEmailChangeError("new email OTP must be 6 digits")

        verify_result = self._openai_provider.verify_change_email(
            access_token=access_token,
            cookie_header=cookie_header,
            email=new_mail,
            code=code,
            proxy_url=proxy_url,
        )
        _require_change_email_success(verify_result, stage="verify")
        self._write_changed_email(
            user_account_id=input_.user_account_id,
            old_mail=old_mail,
            new_mail=new_mail,
            openai_user_id=before_user_id,
        )

        post_session_status = "succeeded"
        post_session_error = ""
        post_session_email = ""
        try:
            post_payload = self._openai_provider.fetch_web_session_payload(
                cookie_header=cookie_header,
                proxy_url=proxy_url,
            )
            post_access_token = _session_access_token(post_payload)
            if not post_access_token:
                raise AccountEmailChangeError("post-change session response missing accessToken")
            after_claims = self._openai_provider.decode_access_token(post_access_token)
            after_user_id = str(after_claims.account_id or "").strip()
            if before_user_id and after_user_id != before_user_id:
                self._mark_post_session_error(
                    input_.user_account_id,
                    "post_change_identity_mismatch",
                )
                raise AccountEmailChangeError(
                    "web session identity mismatch after email change: "
                    f"expected={before_user_id} actual={after_user_id}"
                )
            post_session_email = _session_email(post_payload)
        except AccountEmailChangeError:
            raise
        except Exception as exc:
            post_session_status = "failed"
            post_session_error = f"{type(exc).__name__}: {exc}"[:1000]
            self._write_event(
                run_id,
                "account_email_change.post_session_failed",
                "email changed but post-change session refresh failed",
                {
                    "user_account_id": input_.user_account_id,
                    "new_mail": new_mail,
                    "error": post_session_error,
                },
                level="WARN",
            )

        output = {
            "user_account_id": input_.user_account_id,
            "old_mail": old_mail,
            "new_mail": new_mail,
            "openai_user_id": before_user_id,
            "eligibility": eligibility,
            "begin_result": begin_result,
            "verify_result": verify_result,
            "post_session_status": post_session_status,
            "post_session_error": post_session_error,
            "post_session_email": post_session_email,
        }
        self._write_event(
            run_id,
            "account_email_change.succeeded",
            "account email change succeeded",
            {
                "user_account_id": input_.user_account_id,
                "old_mail": old_mail,
                "new_mail": new_mail,
                "post_session_status": post_session_status,
                "post_session_email": post_session_email,
            },
        )
        return output

    def _run_auto_claim(
        self,
        input_: AccountEmailChangeInput,
        *,
        work_id: str,
        run_id: str,
    ) -> dict:
        old_mail = input_.old_mail.strip()
        if not input_.user_account_id:
            raise AccountEmailChangeError("user_account_id is required")
        if not old_mail:
            raise AccountEmailChangeError("old_mail is required")
        if not work_id:
            raise AccountEmailChangeError("work_id is required for automatic mailbox claim")

        self._assert_account_matches(input_.user_account_id, old_mail)
        self._write_event(
            run_id,
            "account_email_change.started",
            "account email change started",
            {
                "user_account_id": input_.user_account_id,
                "old_mail": old_mail,
                "mode": input_.mode,
            },
        )
        self._write_event(
            run_id,
            "account_email_change.source_session_started",
            "source account session refresh started before email change",
            {
                "user_account_id": input_.user_account_id,
                "old_mail": old_mail,
            },
        )
        self._run_source_session_backfill(input_=input_, run_id=run_id)
        self._mark_login_succeeded(input_.user_account_id)
        self._write_event(
            run_id,
            "account_email_change.source_session_succeeded",
            "source account session refreshed before email change",
            {
                "user_account_id": input_.user_account_id,
                "old_mail": old_mail,
            },
        )
        proxy_url = self._proxy_resolver(
            self._session_factory,
            input_.user_account_id,
            bind_reason="account_email_change",
        )
        account = self._load_account(input_.user_account_id)
        cookie_header = _web_session_cookie_header(account)
        if not cookie_header:
            raise AccountEmailChangeError("source account web session cookie is empty")
        session_payload = self._openai_provider.fetch_web_session_payload(
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
        access_token = _session_access_token(session_payload)
        if not access_token:
            raise AccountEmailChangeError("source web session response missing accessToken")
        claims = self._openai_provider.decode_access_token(access_token)
        before_user_id = str(claims.account_id or "").strip()
        if not account.openai_user_id or before_user_id != account.openai_user_id:
            raise AccountEmailChangeError(
                "source web session identity mismatch: "
                f"expected={account.openai_user_id} actual={before_user_id}"
            )
        self._assert_personal_space_matches(
            user_account_id=input_.user_account_id,
            token_chatgpt_account_id=str(claims.token_chatgpt_account_id or "").strip(),
        )
        eligibility = self._openai_provider.check_change_email_eligibility(
            access_token=access_token,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
        if eligibility.get("eligible") is not True:
            raise AccountEmailChangeError(
                "account is not eligible for email change: "
                f"{json.dumps(eligibility, ensure_ascii=False)[:1000]}"
            )

        rejected_mail_count = 0
        while True:
            claim: ClaimedMailAccount | None = None
            remote_changed = False
            try:
                claim = self._mail_provider.claim_random(
                    caller_id=input_.caller_id,
                    task_id=work_id,
                    provider=input_.mail_provider,
                    project_key="",
                    email_domain=input_.email_domain,
                )
                new_mail = str(claim.email or "").strip()
                if not new_mail:
                    raise AccountEmailChangeError("claimed mailbox email is empty")
                if new_mail.casefold() == old_mail.casefold():
                    raise AccountEmailChangeError("claimed mailbox equals source email")
                try:
                    self._assert_new_email_available(
                        user_account_id=input_.user_account_id,
                        new_mail=new_mail,
                    )
                except AccountEmailChangeError as exc:
                    if "claimed email already exists locally:" not in str(exc):
                        raise
                    rejected_mail_count += 1
                    self._complete_unusable_claim(
                        claim=claim,
                        work_id=work_id,
                        run_id=run_id,
                        old_mail=old_mail,
                        reason="local_email_already_used",
                        rejected_mail_count=rejected_mail_count,
                    )
                    claim = None
                    continue

                claim_data = _safe_claim_dict(claim)
                self._merge_work_output(
                    work_id,
                    {
                        "old_mail": old_mail,
                        "new_mail": new_mail,
                        "mail_claim": claim_data,
                        "rejected_mail_count": rejected_mail_count,
                    },
                )
                self._write_event(
                    run_id,
                    "account_email_change.mail_claimed",
                    "new mailbox claimed for email change",
                    {
                        "user_account_id": input_.user_account_id,
                        "old_mail": old_mail,
                        "new_mail": new_mail,
                        "mail_account_id": claim.account_id,
                        "attempt": rejected_mail_count + 1,
                    },
                )

                prepare_domain_mailbox(self._mail_provider, email=new_mail)
                issued_after = time()
                try:
                    begin_result = self._openai_provider.begin_change_email(
                        access_token=access_token,
                        cookie_header=cookie_header,
                        email=new_mail,
                        proxy_url=proxy_url,
                    )
                except OpenAIChatGPTClientError as exc:
                    if not _is_email_already_linked_error(exc):
                        raise
                    rejected_mail_count += 1
                    self._complete_unusable_claim(
                        claim=claim,
                        work_id=work_id,
                        run_id=run_id,
                        old_mail=old_mail,
                        reason="openai_email_already_linked",
                        rejected_mail_count=rejected_mail_count,
                    )
                    claim = None
                    continue
                _require_change_email_success(begin_result, stage="begin")
                self._write_event(
                    run_id,
                    "account_email_change.otp_sent",
                    "email change OTP requested",
                    {
                        "user_account_id": input_.user_account_id,
                        "new_mail": new_mail,
                        "http_status": begin_result.get("http_status"),
                    },
                )
                otp = self._mail_provider.wait_for_otp_by_email(
                    email=new_mail,
                    timeout_s=max(1, int(input_.otp_timeout_s or 180)),
                    issued_after=issued_after,
                    code_source="all",
                )
                code = str(otp.code or "").strip()
                if len(code) != 6 or not code.isdigit():
                    raise AccountEmailChangeError("new email OTP must be 6 digits")

                verify_result = self._openai_provider.verify_change_email(
                    access_token=access_token,
                    cookie_header=cookie_header,
                    email=new_mail,
                    code=code,
                    proxy_url=proxy_url,
                )
                _require_change_email_success(verify_result, stage="verify")
                remote_changed = True
                self._merge_work_output(
                    work_id,
                    {
                        "old_mail": old_mail,
                        "new_mail": new_mail,
                        "mail_claim": claim_data,
                        "remote_changed": True,
                    },
                )

                complete_result = self._mail_provider.claim_complete(
                    claim,
                    result="success",
                    detail=new_mail,
                )
                self._require_claim_used(complete_result)
                self._merge_work_output(
                    work_id,
                    {
                        "old_mail": old_mail,
                        "new_mail": new_mail,
                        "mail_claim": claim_data,
                        "remote_changed": True,
                        "mail_claim_completed": True,
                    },
                )
                self._write_changed_email(
                    user_account_id=input_.user_account_id,
                    old_mail=old_mail,
                    new_mail=new_mail,
                    openai_user_id=before_user_id,
                )
                output = {
                    "user_account_id": input_.user_account_id,
                    "old_mail": old_mail,
                    "new_mail": new_mail,
                    "openai_user_id": before_user_id,
                    "eligibility": eligibility,
                    "begin_result": begin_result,
                    "verify_result": verify_result,
                    "remote_changed": True,
                    "mail_claim_completed": True,
                    "mail_claim": claim_data,
                    "rejected_mail_count": rejected_mail_count,
                    "post_session_status": "not_requested",
                    "source_session_refreshed": True,
                }
                self._write_event(
                    run_id,
                    "account_email_change.succeeded",
                    "account email change succeeded",
                    {
                        "user_account_id": input_.user_account_id,
                        "old_mail": old_mail,
                        "new_mail": new_mail,
                        "mode": input_.mode,
                        "rejected_mail_count": rejected_mail_count,
                    },
                )
                return output
            except Exception:
                if claim is not None and not remote_changed:
                    self._release_claim(claim=claim, work_id=work_id, run_id=run_id)
                raise

    def _assert_personal_space_matches(
        self,
        *,
        user_account_id: str,
        token_chatgpt_account_id: str,
    ) -> None:
        if not token_chatgpt_account_id:
            raise AccountEmailChangeError("source access token missing chatgpt_account_id")
        with self._session_factory() as session:
            personal_space = session.scalars(
                select(SpaceModel).where(
                    SpaceModel.owner_user_account_id == user_account_id,
                    SpaceModel.space_type == "personal",
                    SpaceModel.credential_type == "personal_account",
                )
            ).first()
            if personal_space is None:
                raise AccountEmailChangeError("source account personal space is missing")
            if personal_space.external_space_id != token_chatgpt_account_id:
                raise AccountEmailChangeError(
                    "source access token personal space mismatch: "
                    f"expected={personal_space.external_space_id} "
                    f"actual={token_chatgpt_account_id}"
                )

    def _assert_new_email_available(self, *, user_account_id: str, new_mail: str) -> None:
        with self._session_factory() as session:
            existing = session.scalars(
                select(UserAccountModel).where(
                    UserAccountModel.id != user_account_id,
                    UserAccountModel.email.ilike(new_mail),
                )
            ).first()
            if existing is not None:
                raise AccountEmailChangeError(
                    f"claimed email already exists locally: {new_mail} account={existing.id}"
                )

    def _release_claim(
        self,
        *,
        claim: ClaimedMailAccount,
        work_id: str,
        run_id: str,
    ) -> None:
        try:
            result = self._mail_provider.claim_release(
                claim,
                reason=f"email_change_failed:{claim.email}",
            )
            released = result.get("success") is True
            self._merge_work_output(
                work_id,
                {
                    "mail_claim": _safe_claim_dict(claim),
                    "mail_claim_released": released,
                },
            )
            if not released:
                raise AccountEmailChangeError(
                    f"mail claim release failed: {json.dumps(result, ensure_ascii=False)[:1000]}"
                )
        except Exception as exc:
            self._write_event(
                run_id,
                "account_email_change.mail_release_failed",
                "failed to release mailbox after email change failure",
                {
                    "work_id": work_id,
                    "email": claim.email,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                level="WARN",
            )

    def _complete_unusable_claim(
        self,
        *,
        claim: ClaimedMailAccount,
        work_id: str,
        run_id: str,
        old_mail: str,
        reason: str,
        rejected_mail_count: int,
    ) -> None:
        result = self._mail_provider.claim_complete(
            claim,
            result="success",
            detail=reason,
        )
        self._require_claim_used(result)
        self._merge_work_output(
            work_id,
            {
                "old_mail": old_mail,
                "new_mail": "",
                "last_rejected_mail": claim.email,
                "last_rejected_mail_reason": reason,
                "rejected_mail_count": rejected_mail_count,
                "mail_claim": _safe_claim_dict(claim),
                "mail_claim_completed": True,
            },
        )
        self._write_event(
            run_id,
            "account_email_change.mail_marked_used",
            "unusable mailbox marked used before retry",
            {
                "work_id": work_id,
                "old_mail": old_mail,
                "new_mail": claim.email,
                "mail_account_id": claim.account_id,
                "reason": reason,
                "rejected_mail_count": rejected_mail_count,
            },
        )

    @staticmethod
    def _require_claim_used(result: dict) -> None:
        if result.get("success") is not True:
            raise AccountEmailChangeError(
                f"mail claim completion failed: {json.dumps(result, ensure_ascii=False)[:1000]}"
            )
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        pool_status = str(data.get("pool_status") or result.get("pool_status") or "").strip()
        if pool_status and pool_status != "used":
            raise AccountEmailChangeError(
                f"mail claim was not marked used: pool_status={pool_status}"
            )

    def _merge_work_output(self, work_id: str, patch: dict[str, Any]) -> None:
        if not work_id:
            return
        with self._session_factory() as session:
            work = session.get(WorkItemModel, work_id)
            if work is None:
                return
            current = dict(work.output_json or {})
            current.update(patch)
            work.output_json = current
            work.updated_at = datetime.now(UTC)
            session.commit()

    def _run_session_backfill(self, *, user_account_id: str, run_id: str) -> str:
        if self._backfill_session is not None:
            return self._backfill_session(user_account_id=user_account_id, run_id=run_id)
        return BackfillSessionWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
            totp_code_resolver=self._totp_code_resolver,
        ).run(user_account_id=user_account_id, run_id=run_id)

    def _run_source_session_backfill(
        self,
        *,
        input_: AccountEmailChangeInput,
        run_id: str,
    ) -> str:
        if self._backfill_session is not None:
            return self._backfill_session(
                user_account_id=input_.user_account_id,
                run_id=run_id,
            )
        provider = self._source_mail_provider_factory(input_)
        try:
            return BackfillSessionWorkflow(
                session_factory=self._session_factory,
                mail_provider=provider,
                totp_code_resolver=self._totp_code_resolver,
            ).run(user_account_id=input_.user_account_id, run_id=run_id)
        finally:
            provider.close()

    def _assert_account_matches(self, user_account_id: str, old_mail: str) -> None:
        account = self._load_account(user_account_id)
        if account.email.casefold() != old_mail.casefold():
            raise AccountEmailChangeError(
                f"account email mismatch: expected={old_mail} actual={account.email}"
            )

    def _load_account(self, user_account_id: str) -> UserAccountModel:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountEmailChangeError(f"user account not found: {user_account_id}")
            session.expunge(account)
            return account

    def _mark_login_succeeded(self, user_account_id: str) -> None:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountEmailChangeError("user account disappeared after login")
            account.account_status = "active"
            account.updated_at = datetime.now(UTC)
            session.commit()

    def _write_changed_email(
        self,
        *,
        user_account_id: str,
        old_mail: str,
        new_mail: str,
        openai_user_id: str,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise AccountEmailChangeError("user account disappeared after email change")
            if account.email.casefold() != old_mail.casefold():
                raise AccountEmailChangeError(
                    "account email changed concurrently: "
                    f"expected={old_mail} actual={account.email}"
                )
            existing = session.scalars(
                select(UserAccountModel).where(
                    UserAccountModel.id != user_account_id,
                    UserAccountModel.email.ilike(new_mail),
                )
            ).first()
            if existing is not None:
                raise AccountEmailChangeError(
                    f"new email already exists locally: {new_mail} account={existing.id}"
                )
            account.email = new_mail
            account.account_status = "active"
            account.updated_at = now
            if openai_user_id and not account.openai_user_id:
                account.openai_user_id = openai_user_id
            personal_spaces = session.scalars(
                select(SpaceModel).where(
                    SpaceModel.owner_user_account_id == user_account_id,
                    SpaceModel.space_type == "personal",
                )
            ).all()
            for space in personal_spaces:
                space.name = new_mail
                space.updated_at = now
            session.commit()

    def _mark_post_session_error(self, user_account_id: str, message: str) -> None:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                return
            account.session_status = "error"
            account.last_login_error_code = "change_email_post_session_error"
            account.last_login_error_message = message[:1000]
            account.updated_at = datetime.now(UTC)
            session.commit()

    def _write_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict,
        *,
        level: str = "INFO",
    ) -> None:
        if not run_id:
            return
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                data_json=data_json,
                level=level,
            )
            session.commit()


def _web_session_cookie_header(account: UserAccountModel) -> str:
    cookie_header = str(account.cookie_header or "").strip()
    session_token = str(account.session_token or "").strip()
    if not session_token or "__Secure-next-auth.session-token=" in cookie_header:
        return cookie_header
    if not cookie_header:
        return f"__Secure-next-auth.session-token={session_token}"
    return f"__Secure-next-auth.session-token={session_token}; {cookie_header}"


def _session_access_token(payload: dict) -> str:
    for source in (payload, payload.get("user")):
        if not isinstance(source, dict):
            continue
        for key in ("accessToken", "access_token"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _session_email(payload: dict) -> str:
    user = payload.get("user")
    if not isinstance(user, dict):
        return ""
    return str(user.get("email") or "").strip()


def _require_change_email_success(payload: dict, *, stage: str) -> None:
    if payload.get("success") is True:
        return
    raise AccountEmailChangeError(
        f"email change {stage} failed: {json.dumps(payload, ensure_ascii=False)[:1000]}"
    )


def _safe_claim_dict(claim: ClaimedMailAccount) -> dict[str, Any]:
    return {
        "account_id": claim.account_id,
        "email": claim.email,
        "email_domain": claim.email_domain,
        "claim_token": claim.claim_token,
        "caller_id": claim.caller_id,
        "task_id": claim.task_id,
    }


def _source_mail_provider(input_: AccountEmailChangeInput) -> SourceMailboxOtpProvider:
    return SourceMailboxOtpProvider(
        SourceMailboxOtpConfig(
            email=input_.old_mail,
            mailbox_url=input_.source_mailbox_url,
            graph_client_id=input_.source_mailbox_client_id,
            graph_refresh_token=input_.source_mailbox_refresh_token,
            graph_access_token=input_.source_mailbox_access_token,
        )
    )


def _is_email_already_linked_error(exc: Exception) -> bool:
    message = str(exc)
    return "http_status=403" in message and _EMAIL_ALREADY_LINKED_MESSAGE in message
