from __future__ import annotations

from sqlalchemy import delete

from refactor_app.application.workflows.mail import (
    AllocateMailLeaseWorkflow,
    MarkMailLeaseFailedWorkflow,
    MarkMailLeaseUsedWorkflow,
    PollMailOtpWorkflow,
    ReleaseMailLeaseWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import ExternalMailLeaseModel
from refactor_app.plugins.contracts import HealthcheckResult, MailLease, OtpMessage


class FakeMailProvider:
    name = "fake_mail"

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["mailbox.allocate"]

    def allocate_mailbox(self, *, purpose: str = "") -> MailLease:
        return MailLease(
            provider="external_mail_api",
            external_lease_id=f"lease-{purpose}",
            email=f"{purpose}@example.test",
        )

    def poll_otp(self, *, external_lease_id: str, timeout_s: int) -> OtpMessage | None:
        return OtpMessage(code=f"otp-{external_lease_id}")

    def mark_used(self, *, external_lease_id: str) -> None:
        return None

    def mark_failed(
        self,
        *,
        external_lease_id: str,
        failure_code: str = "",
        failure_message: str = "",
    ) -> None:
        return None

    def release(self, *, external_lease_id: str, reason: str = "") -> None:
        return None


def test_allocate_mail_lease_workflow_writes_external_mail_lease() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    workflow = AllocateMailLeaseWorkflow(
        session_factory=session_factory,
        mail_provider=FakeMailProvider(),
    )

    lease_id = workflow.run(purpose="register")

    with session_factory() as session:
        lease = session.get(ExternalMailLeaseModel, lease_id)
        assert lease is not None
        assert lease.provider == "external_mail_api"
        assert lease.external_lease_id == "lease-register"
        assert lease.email == "register@example.test"
        assert lease.lease_status == "allocated"

        session.execute(delete(ExternalMailLeaseModel).where(ExternalMailLeaseModel.id == lease_id))
        session.commit()


def test_mail_lease_lifecycle_workflows_update_status() -> None:
    settings = Settings()
    session_factory = make_session_factory(make_engine(settings))
    provider = FakeMailProvider()
    lease_id = AllocateMailLeaseWorkflow(
        session_factory=session_factory,
        mail_provider=provider,
    ).run(purpose="lifecycle")

    otp = PollMailOtpWorkflow(session_factory=session_factory, mail_provider=provider).run(
        mail_lease_id=lease_id,
        timeout_s=1,
    )
    MarkMailLeaseUsedWorkflow(session_factory=session_factory, mail_provider=provider).run(
        mail_lease_id=lease_id
    )

    with session_factory() as session:
        lease = session.get(ExternalMailLeaseModel, lease_id)
        assert lease is not None
        assert otp == "otp-lease-lifecycle"
        assert lease.lease_status == "used"
        assert lease.used_at is not None
        session.execute(delete(ExternalMailLeaseModel).where(ExternalMailLeaseModel.id == lease_id))
        session.commit()

    failed_id = AllocateMailLeaseWorkflow(
        session_factory=session_factory,
        mail_provider=provider,
    ).run(purpose="failed")
    MarkMailLeaseFailedWorkflow(session_factory=session_factory, mail_provider=provider).run(
        mail_lease_id=failed_id,
        failure_code="otp_timeout",
        failure_message="no otp",
    )

    with session_factory() as session:
        lease = session.get(ExternalMailLeaseModel, failed_id)
        assert lease is not None
        assert lease.lease_status == "failed"
        assert lease.failure_code == "otp_timeout"
        session.execute(
            delete(ExternalMailLeaseModel).where(ExternalMailLeaseModel.id == failed_id)
        )
        session.commit()

    released_id = AllocateMailLeaseWorkflow(
        session_factory=session_factory,
        mail_provider=provider,
    ).run(purpose="released")
    ReleaseMailLeaseWorkflow(session_factory=session_factory, mail_provider=provider).run(
        mail_lease_id=released_id,
        reason="cleanup",
    )

    with session_factory() as session:
        lease = session.get(ExternalMailLeaseModel, released_id)
        assert lease is not None
        assert lease.lease_status == "released"
        assert lease.released_at is not None
        session.execute(
            delete(ExternalMailLeaseModel).where(ExternalMailLeaseModel.id == released_id)
        )
        session.commit()
