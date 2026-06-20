from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    Base,
    CodexOAuthCredentialModel,
    DownstreamCodexPushRecordModel,
    ExternalMailLeaseModel,
    JobEventModel,
    JobModel,
    JobRunModel,
    JobStepModel,
    MembershipModel,
    ProxyInventoryModel,
    TeamWorkspaceModel,
    UserAccountAuthModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)

ModelT = TypeVar("ModelT", bound=Base)


class SqlAlchemyRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, model: ModelT) -> None:
        self.session.add(model)

    def get(self, id_: str) -> ModelT | None:
        return self.session.get(self.model, id_)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()


class UserAccountRepository(SqlAlchemyRepository[UserAccountModel]):
    model = UserAccountModel


class UserAccountAuthRepository(SqlAlchemyRepository[UserAccountAuthModel]):
    model = UserAccountAuthModel


class TeamWorkspaceRepository(SqlAlchemyRepository[TeamWorkspaceModel]):
    model = TeamWorkspaceModel

    def upsert_from_values(self, values: dict) -> TeamWorkspaceModel:
        stmt = (
            insert(TeamWorkspaceModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["provider", "external_workspace_id"],
                set_={
                    "name": values["name"],
                    "plan_type": values["plan_type"],
                    "seat_limit": values["seat_limit"],
                    "workspace_status": values["workspace_status"],
                    "updated_at": values["updated_at"],
                },
            )
            .returning(TeamWorkspaceModel)
        )
        return self.session.scalars(stmt).one()


class MembershipRepository(SqlAlchemyRepository[MembershipModel]):
    model = MembershipModel

    def get_by_user_and_workspace(
        self,
        *,
        user_account_id: str,
        team_workspace_id: str,
    ) -> MembershipModel | None:
        stmt = select(MembershipModel).where(
            MembershipModel.user_account_id == user_account_id,
            MembershipModel.team_workspace_id == team_workspace_id,
        )
        return self.session.scalars(stmt).first()


class WorkspaceJoinBatchRepository(SqlAlchemyRepository[WorkspaceJoinBatchModel]):
    model = WorkspaceJoinBatchModel

    def active_for_workspace(self, team_workspace_id: str) -> Sequence[WorkspaceJoinBatchModel]:
        stmt = select(WorkspaceJoinBatchModel).where(
            WorkspaceJoinBatchModel.team_workspace_id == team_workspace_id,
            WorkspaceJoinBatchModel.activation_status == "active",
        )
        return self.session.scalars(stmt).all()


class WorkspaceJoinBatchItemRepository(SqlAlchemyRepository[WorkspaceJoinBatchItemModel]):
    model = WorkspaceJoinBatchItemModel


class CodexOAuthCredentialRepository(SqlAlchemyRepository[CodexOAuthCredentialModel]):
    model = CodexOAuthCredentialModel

    def get_current(
        self,
        *,
        user_account_id: str,
        team_workspace_id: str,
        codex_client_id: str,
    ) -> CodexOAuthCredentialModel | None:
        stmt = select(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.user_account_id == user_account_id,
            CodexOAuthCredentialModel.team_workspace_id == team_workspace_id,
            CodexOAuthCredentialModel.codex_client_id == codex_client_id,
        )
        return self.session.scalars(stmt).first()

    def upsert_from_values(self, values: dict) -> CodexOAuthCredentialModel:
        stmt = (
            insert(CodexOAuthCredentialModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["user_account_id", "team_workspace_id", "codex_client_id"],
                set_={
                    "credential_status": values["credential_status"],
                    "account_id": values["account_id"],
                    "token_chatgpt_account_id": values["token_chatgpt_account_id"],
                    "access_token": values["access_token"],
                    "id_token": values["id_token"],
                    "refresh_token": values["refresh_token"],
                    "expires_at": values["expires_at"],
                    "last_refresh_at": values["last_refresh_at"],
                    "failure_code": values["failure_code"],
                    "failure_message": values["failure_message"],
                    "updated_at": values["updated_at"],
                },
            )
            .returning(CodexOAuthCredentialModel)
        )
        return self.session.scalars(stmt).one()


class DownstreamCodexPushRecordRepository(SqlAlchemyRepository[DownstreamCodexPushRecordModel]):
    model = DownstreamCodexPushRecordModel

    def upsert_from_values(self, values: dict) -> DownstreamCodexPushRecordModel:
        stmt = (
            insert(DownstreamCodexPushRecordModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["batch_item_id", "downstream_provider"],
                set_={
                    "codex_credential_id": values["codex_credential_id"],
                    "user_account_id": values["user_account_id"],
                    "team_workspace_id": values["team_workspace_id"],
                    "membership_id": values["membership_id"],
                    "downstream_external_id": values["downstream_external_id"],
                    "push_status": values["push_status"],
                    "codex_client_id": values["codex_client_id"],
                    "codex_account_id": values["codex_account_id"],
                    "codex_email": values["codex_email"],
                    "downstream_chatgpt_account_id": values["downstream_chatgpt_account_id"],
                    "token_chatgpt_account_id": values["token_chatgpt_account_id"],
                    "codex_token_expires_at": values["codex_token_expires_at"],
                    "request_endpoint": values["request_endpoint"],
                    "error_code": values["error_code"],
                    "error_message": values["error_message"],
                    "updated_at": values["updated_at"],
                },
            )
            .returning(DownstreamCodexPushRecordModel)
        )
        return self.session.scalars(stmt).one()


class ProxyInventoryRepository(SqlAlchemyRepository[ProxyInventoryModel]):
    model = ProxyInventoryModel

    def upsert_from_values(self, values: dict) -> ProxyInventoryModel:
        stmt = (
            insert(ProxyInventoryModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["provider", "external_proxy_id"],
                set_={
                    "connection_mode": values["connection_mode"],
                    "proxy_host": values["proxy_host"],
                    "proxy_port": values["proxy_port"],
                    "proxy_scheme": values["proxy_scheme"],
                    "proxy_username": values["proxy_username"],
                    "proxy_password": values["proxy_password"],
                    "country_code": values["country_code"],
                    "city_name": values["city_name"],
                    "asn_name": values["asn_name"],
                    "proxy_status": values["proxy_status"],
                    "provider_valid": values["provider_valid"],
                    "last_provider_verification_at": values["last_provider_verification_at"],
                    "updated_at": values["updated_at"],
                },
            )
            .returning(ProxyInventoryModel)
        )
        return self.session.scalars(stmt).one()

    def first_available(self) -> ProxyInventoryModel | None:
        return self.least_bound_available_for_update()

    def least_bound_available_for_update(self) -> ProxyInventoryModel | None:
        bind_counts = (
            select(
                UserAccountProxyBindingModel.proxy_id.label("proxy_id"),
                func.count(UserAccountProxyBindingModel.id).label("active_bind_count"),
            )
            .where(UserAccountProxyBindingModel.bind_status == "active")
            .group_by(UserAccountProxyBindingModel.proxy_id)
            .subquery()
        )
        active_bind_count = func.coalesce(bind_counts.c.active_bind_count, 0)
        stmt = (
            select(ProxyInventoryModel)
            .outerjoin(bind_counts, bind_counts.c.proxy_id == ProxyInventoryModel.id)
            .where(
                ProxyInventoryModel.provider == "webshare",
                ProxyInventoryModel.proxy_status.in_(("available", "bound")),
                ProxyInventoryModel.provider_valid.is_(True),
            )
            .order_by(active_bind_count.asc(), ProxyInventoryModel.updated_at.asc())
            .with_for_update(of=ProxyInventoryModel, skip_locked=True)
            .limit(1)
        )
        return self.session.scalars(stmt).first()


class UserAccountProxyBindingRepository(SqlAlchemyRepository[UserAccountProxyBindingModel]):
    model = UserAccountProxyBindingModel

    def upsert_active_binding(self, values: dict) -> UserAccountProxyBindingModel:
        stmt = (
            insert(UserAccountProxyBindingModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["user_account_id"],
                set_={
                    "proxy_id": values["proxy_id"],
                    "bind_status": values["bind_status"],
                    "bind_reason": values["bind_reason"],
                    "bound_by_job_id": values["bound_by_job_id"],
                    "bound_at": values["bound_at"],
                    "last_error_code": "",
                    "updated_at": values["updated_at"],
                },
            )
            .returning(UserAccountProxyBindingModel)
        )
        return self.session.scalars(stmt).one()


class ExternalMailLeaseRepository(SqlAlchemyRepository[ExternalMailLeaseModel]):
    model = ExternalMailLeaseModel


class JobRepository(SqlAlchemyRepository[JobModel]):
    model = JobModel


class JobRunRepository(SqlAlchemyRepository[JobRunModel]):
    model = JobRunModel


class JobStepRepository(SqlAlchemyRepository[JobStepModel]):
    model = JobStepModel


class JobEventRepository(SqlAlchemyRepository[JobEventModel]):
    model = JobEventModel
