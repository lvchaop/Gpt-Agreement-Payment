from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.repositories import (
    DownstreamChannelRepository,
    ExternalMailLeaseRepository,
    JobEventRepository,
    JobRepository,
    JobRunRepository,
    JobStepRepository,
    ProxyInventoryRepository,
    DownstreamChannelCredentialTypeBalanceRepository,
    SpaceAccountCooldownRepository,
    SpaceCredentialRepository,
    SpaceCredentialUsageStateRepository,
    SpaceMembershipRepository,
    SpacePushAttemptRepository,
    SpacePushBindingRepository,
    SpaceRecycleRuleRepository,
    SpaceRepository,
    SpaceUsageCheckRepository,
    UserAccountProxyBindingRepository,
    UserAccountRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.user_accounts: UserAccountRepository | None = None
        self.spaces: SpaceRepository | None = None
        self.space_credentials: SpaceCredentialRepository | None = None
        self.space_memberships: SpaceMembershipRepository | None = None
        self.downstream_channel_type_balances: (
            DownstreamChannelCredentialTypeBalanceRepository | None
        ) = None
        self.space_push_bindings: SpacePushBindingRepository | None = None
        self.space_push_attempts: SpacePushAttemptRepository | None = None
        self.space_credential_usage_states: SpaceCredentialUsageStateRepository | None = None
        self.space_usage_checks: SpaceUsageCheckRepository | None = None
        self.space_recycle_rules: SpaceRecycleRuleRepository | None = None
        self.space_account_cooldowns: SpaceAccountCooldownRepository | None = None
        self.downstream_channels: DownstreamChannelRepository | None = None
        self.proxy_inventory: ProxyInventoryRepository | None = None
        self.user_account_proxy_bindings: UserAccountProxyBindingRepository | None = None
        self.external_mail_leases: ExternalMailLeaseRepository | None = None
        self.jobs: JobRepository | None = None
        self.job_runs: JobRunRepository | None = None
        self.job_steps: JobStepRepository | None = None
        self.job_events: JobEventRepository | None = None

    def __enter__(self) -> UnitOfWork:
        self.session = self._session_factory()
        self.user_accounts = UserAccountRepository(self.session)
        self.spaces = SpaceRepository(self.session)
        self.space_credentials = SpaceCredentialRepository(self.session)
        self.space_memberships = SpaceMembershipRepository(self.session)
        self.downstream_channel_type_balances = DownstreamChannelCredentialTypeBalanceRepository(
            self.session
        )
        self.space_push_bindings = SpacePushBindingRepository(self.session)
        self.space_push_attempts = SpacePushAttemptRepository(self.session)
        self.space_credential_usage_states = SpaceCredentialUsageStateRepository(self.session)
        self.space_usage_checks = SpaceUsageCheckRepository(self.session)
        self.space_recycle_rules = SpaceRecycleRuleRepository(self.session)
        self.space_account_cooldowns = SpaceAccountCooldownRepository(self.session)
        self.downstream_channels = DownstreamChannelRepository(self.session)
        self.proxy_inventory = ProxyInventoryRepository(self.session)
        self.user_account_proxy_bindings = UserAccountProxyBindingRepository(self.session)
        self.external_mail_leases = ExternalMailLeaseRepository(self.session)
        self.jobs = JobRepository(self.session)
        self.job_runs = JobRunRepository(self.session)
        self.job_steps = JobStepRepository(self.session)
        self.job_events = JobEventRepository(self.session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.session is None:
            return
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
