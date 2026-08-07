from __future__ import annotations

from refactor_app.plugins.contracts import HealthcheckResult, MailLease, OtpMessage
from refactor_app.plugins.mail_external_api.client import (
    ClaimedMailAccount,
    ExternalMailApiClient,
    ExternalMailApiClientConfig,
)


class ExternalMailApiPlugin:
    name = "mail_external_api"

    def __init__(self, client: ExternalMailApiClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: ExternalMailApiClientConfig) -> ExternalMailApiPlugin:
        return cls(ExternalMailApiClient(config))

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "external_mail_api"})

    def capabilities(self) -> list[str]:
        return [
            "mailbox.allocate",
            "mailbox.poll_otp",
            "mailbox.ensure_email",
            "mailbox.ensure_domain_email",
            "mailbox.wait_for_otp_by_email",
            "mailbox.mark_used",
            "mailbox.mark_failed",
            "mailbox.release",
            "pool.claim_random",
            "pool.claim_release",
            "pool.claim_complete",
        ]

    def allocate_mailbox(self, *, purpose: str = "") -> MailLease:
        return self._client.allocate_mailbox(purpose=purpose)

    def poll_otp(self, *, external_lease_id: str, timeout_s: int) -> OtpMessage | None:
        return self._client.poll_otp(external_lease_id=external_lease_id, timeout_s=timeout_s)

    def ensure_email(self, *, email: str) -> dict:
        return self._client.ensure_email(email=email)

    def ensure_domain_email(self, *, email: str) -> dict:
        return self._client.ensure_domain_email(email=email)

    def wait_for_otp_by_email(
        self,
        *,
        email: str,
        timeout_s: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
        code_source: str = "content",
    ) -> OtpMessage:
        return self._client.wait_for_otp_by_email(
            email=email,
            timeout_s=timeout_s,
            issued_after=issued_after,
            max_polls=max_polls,
            code_source=code_source,
        )

    def mark_used(self, *, external_lease_id: str) -> None:
        self._client.mark_used(external_lease_id=external_lease_id)

    def mark_failed(
        self,
        *,
        external_lease_id: str,
        failure_code: str = "",
        failure_message: str = "",
    ) -> None:
        self._client.mark_failed(
            external_lease_id=external_lease_id,
            failure_code=failure_code,
            failure_message=failure_message,
        )

    def release(self, *, external_lease_id: str, reason: str = "") -> None:
        self._client.release(external_lease_id=external_lease_id, reason=reason)

    def claim_random(
        self,
        *,
        caller_id: str,
        task_id: str,
        provider: str = "",
        project_key: str = "",
        email_domain: str = "",
    ) -> ClaimedMailAccount:
        return self._client.claim_random(
            caller_id=caller_id,
            task_id=task_id,
            provider=provider,
            project_key=project_key,
            email_domain=email_domain,
        )

    def pool_stats(self) -> dict:
        return self._client.pool_stats()

    def claim_release(self, claim: ClaimedMailAccount, *, reason: str = "") -> dict:
        return self._client.claim_release(claim, reason=reason)

    def claim_complete(self, claim: ClaimedMailAccount, *, result: str, detail: str = "") -> dict:
        return self._client.claim_complete(claim, result=result, detail=detail)


def prepare_domain_mailbox(provider: object, *, email: str) -> None:
    ensure = getattr(provider, "ensure_domain_email", None)
    if callable(ensure):
        ensure(email=email)
