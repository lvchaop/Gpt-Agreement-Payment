from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from time import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import (
    BackfillSessionWorkflow,
    ensure_account_proxy_url,
)
from refactor_app.infrastructure.db.models import SpaceModel, UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin


class AccountEmailChangeError(RuntimeError):
    pass


class AccountEmailChangeCsvError(ValueError):
    pass


@dataclass(frozen=True)
class AccountEmailChangePair:
    row_number: int
    old_mail: str
    new_mail: str


@dataclass(frozen=True)
class AccountEmailChangeInput:
    user_account_id: str
    old_mail: str
    new_mail: str
    otp_timeout_s: int = 180


def parse_account_email_change_csv(csv_text: str) -> list[AccountEmailChangePair]:
    source = str(csv_text or "").lstrip("\ufeff")
    if not source.strip():
        raise AccountEmailChangeCsvError("CSV is empty")

    reader = csv.DictReader(StringIO(source))
    field_names = list(reader.fieldnames or [])
    canonical = {str(name or "").strip().lower(): name for name in field_names}
    missing = [name for name in ("old_mail", "new_mail") if name not in canonical]
    if missing:
        raise AccountEmailChangeCsvError(
            f"CSV missing required columns: {', '.join(missing)}"
        )

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
        errors.append(
            "old_mail and new_mail sets overlap: " + ", ".join(overlap[:10])
        )
    if errors:
        raise AccountEmailChangeCsvError("; ".join(errors[:20]))
    if not pairs:
        raise AccountEmailChangeCsvError("CSV has no account email pairs")
    return pairs


class AccountEmailChangeWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
        openai_provider: OpenAIChatGPTProvider,
        backfill_session: Callable[..., str] | None = None,
        proxy_resolver: Callable[..., str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._openai_provider = openai_provider
        self._backfill_session = backfill_session
        self._proxy_resolver = proxy_resolver or ensure_account_proxy_url

    def run(self, input_: AccountEmailChangeInput, *, run_id: str = "") -> dict:
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

        issued_after = time()
        begin_result = self._openai_provider.begin_change_email(
            access_token=access_token,
            cookie_header=cookie_header,
            email=new_mail,
            proxy_url=proxy_url,
        )
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

    def _run_session_backfill(self, *, user_account_id: str, run_id: str) -> str:
        if self._backfill_session is not None:
            return self._backfill_session(user_account_id=user_account_id, run_id=run_id)
        return BackfillSessionWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
        ).run(user_account_id=user_account_id, run_id=run_id)

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
