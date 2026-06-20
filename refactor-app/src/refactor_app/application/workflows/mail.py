from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.domain.enums import MailLeaseStatus
from refactor_app.infrastructure.db.models import ExternalMailLeaseModel
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import MailProvider


class MailWorkflowError(RuntimeError):
    pass


class AllocateMailLeaseWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: MailProvider,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, user_account_id: str | None = None, purpose: str = "") -> str:
        lease = self._mail_provider.allocate_mailbox(purpose=purpose)
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.external_mail_leases is None:
                raise MailWorkflowError("external mail lease repository is not initialized")
            model = ExternalMailLeaseModel(
                id=f"external-mail-lease-{uuid4()}",
                user_account_id=user_account_id,
                provider=lease.provider,
                external_lease_id=lease.external_lease_id,
                email=lease.email,
                lease_status=MailLeaseStatus.ALLOCATED.value,
                allocated_at=now,
                created_at=now,
                updated_at=now,
            )
            uow.external_mail_leases.add(model)
            return model.id


class PollMailOtpWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: MailProvider,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, mail_lease_id: str, timeout_s: int) -> str:
        lease = _get_mail_lease(self._session_factory, mail_lease_id)
        otp = self._mail_provider.poll_otp(
            external_lease_id=lease.external_lease_id,
            timeout_s=timeout_s,
        )
        return otp.code if otp is not None else ""


class MarkMailLeaseUsedWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: MailProvider,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, mail_lease_id: str) -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            lease = _get_mail_lease_from_uow(uow, mail_lease_id)
            self._mail_provider.mark_used(external_lease_id=lease.external_lease_id)
            lease.lease_status = MailLeaseStatus.USED.value
            lease.used_at = now
            lease.updated_at = now
            return lease.id


class MarkMailLeaseFailedWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: MailProvider,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, mail_lease_id: str, failure_code: str = "", failure_message: str = "") -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            lease = _get_mail_lease_from_uow(uow, mail_lease_id)
            self._mail_provider.mark_failed(
                external_lease_id=lease.external_lease_id,
                failure_code=failure_code,
                failure_message=failure_message,
            )
            lease.lease_status = MailLeaseStatus.FAILED.value
            lease.failure_code = failure_code
            lease.failure_message = failure_message
            lease.updated_at = now
            return lease.id


class ReleaseMailLeaseWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: MailProvider,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, mail_lease_id: str, reason: str = "") -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            lease = _get_mail_lease_from_uow(uow, mail_lease_id)
            self._mail_provider.release(external_lease_id=lease.external_lease_id, reason=reason)
            lease.lease_status = MailLeaseStatus.RELEASED.value
            lease.released_at = now
            lease.updated_at = now
            return lease.id


def _get_mail_lease(
    session_factory: Callable[[], Session],
    mail_lease_id: str,
) -> ExternalMailLeaseModel:
    with UnitOfWork(session_factory) as uow:
        return _get_mail_lease_from_uow(uow, mail_lease_id)


def _get_mail_lease_from_uow(
    uow: UnitOfWork,
    mail_lease_id: str,
) -> ExternalMailLeaseModel:
    if uow.external_mail_leases is None:
        raise MailWorkflowError("external mail lease repository is not initialized")
    lease = uow.external_mail_leases.get(mail_lease_id)
    if lease is None:
        raise MailWorkflowError(f"external mail lease not found: {mail_lease_id}")
    return lease
