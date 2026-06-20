from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.repositories import (
    CodexOAuthCredentialRepository,
    DownstreamCodexPushRecordRepository,
    ExternalMailLeaseRepository,
    JobEventRepository,
    JobRepository,
    JobRunRepository,
    JobStepRepository,
    MembershipRepository,
    ProxyInventoryRepository,
    TeamWorkspaceRepository,
    UserAccountAuthRepository,
    UserAccountProxyBindingRepository,
    UserAccountRepository,
    WorkspaceJoinBatchItemRepository,
    WorkspaceJoinBatchRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.user_accounts: UserAccountRepository | None = None
        self.user_account_auth: UserAccountAuthRepository | None = None
        self.team_workspaces: TeamWorkspaceRepository | None = None
        self.memberships: MembershipRepository | None = None
        self.workspace_join_batches: WorkspaceJoinBatchRepository | None = None
        self.workspace_join_batch_items: WorkspaceJoinBatchItemRepository | None = None
        self.codex_oauth_credentials: CodexOAuthCredentialRepository | None = None
        self.downstream_codex_push_records: DownstreamCodexPushRecordRepository | None = None
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
        self.user_account_auth = UserAccountAuthRepository(self.session)
        self.team_workspaces = TeamWorkspaceRepository(self.session)
        self.memberships = MembershipRepository(self.session)
        self.workspace_join_batches = WorkspaceJoinBatchRepository(self.session)
        self.workspace_join_batch_items = WorkspaceJoinBatchItemRepository(self.session)
        self.codex_oauth_credentials = CodexOAuthCredentialRepository(self.session)
        self.downstream_codex_push_records = DownstreamCodexPushRecordRepository(self.session)
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
