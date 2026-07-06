from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    Base,
    DownstreamChannelModel,
    ExternalMailLeaseModel,
    JobEventModel,
    JobModel,
    JobRunModel,
    JobStepModel,
    ProxyInventoryModel,
    TeamAdminProxyBindingModel,
    DownstreamChannelCredentialTypeBalanceModel,
    SpaceAccountCooldownModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushAttemptModel,
    SpacePushBindingModel,
    SpaceRecycleRuleModel,
    SpaceUsageCheckModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
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


class SpaceRepository(SqlAlchemyRepository[SpaceModel]):
    model = SpaceModel

    def get_by_provider_external_id(
        self,
        *,
        provider: str,
        external_space_id: str,
    ) -> SpaceModel | None:
        stmt = select(SpaceModel).where(
            SpaceModel.provider == provider,
            SpaceModel.external_space_id == external_space_id,
        )
        return self.session.scalars(stmt).first()

    def upsert_from_values(self, values: dict) -> SpaceModel:
        stmt = (
            insert(SpaceModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["provider", "external_space_id"],
                set_={
                    "owner_user_account_id": values.get("owner_user_account_id", ""),
                    "name": values.get("name", ""),
                    "space_type": values["space_type"],
                    "auth_mode": values["auth_mode"],
                    "credential_type": values["credential_type"],
                    "plan_type": values.get("plan_type", ""),
                    "seat_limit": values.get("seat_limit", 0),
                    "seats_in_use": values.get("seats_in_use", 0),
                    "seats_entitled": values.get("seats_entitled", 0),
                    "space_status": values["space_status"],
                    "source_admin_session_id": values.get("source_admin_session_id", ""),
                    "raw_space_json": values.get("raw_space_json", {}),
                    "last_subscription_sync_at": values.get("last_subscription_sync_at"),
                    "last_probe_at": values.get("last_probe_at"),
                    "updated_at": values["updated_at"],
                },
            )
            .returning(SpaceModel)
        )
        return self.session.scalars(stmt).one()


class SpaceCredentialRepository(SqlAlchemyRepository[SpaceCredentialModel]):
    model = SpaceCredentialModel

    def get_current(
        self,
        *,
        space_id: str,
        user_account_id: str,
    ) -> SpaceCredentialModel | None:
        stmt = select(SpaceCredentialModel).where(
            SpaceCredentialModel.space_id == space_id,
            SpaceCredentialModel.user_account_id == user_account_id,
        )
        return self.session.scalars(stmt).first()

    def upsert_from_values(self, values: dict) -> SpaceCredentialModel:
        stmt = (
            insert(SpaceCredentialModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["space_id", "user_account_id"],
                set_={
                    "space_membership_id": values.get("space_membership_id"),
                    "external_credential_id": values.get("external_credential_id", ""),
                    "credential_status": values["credential_status"],
                    "access_token": values.get("access_token", ""),
                    "id_token": values.get("id_token", ""),
                    "refresh_token": values.get("refresh_token", ""),
                    "codex_client_id": values.get("codex_client_id", ""),
                    "account_id": values.get("account_id", ""),
                    "token_chatgpt_account_id": values.get("token_chatgpt_account_id", ""),
                    "expires_at": values.get("expires_at"),
                    "last_authorized_at": values.get("last_authorized_at"),
                    "last_probe_at": values.get("last_probe_at"),
                    "last_probe_status": values.get("last_probe_status", ""),
                    "failure_code": values.get("failure_code", ""),
                    "failure_message": values.get("failure_message", ""),
                    "raw_credential_json": values.get("raw_credential_json", {}),
                    "updated_at": values["updated_at"],
                },
            )
            .returning(SpaceCredentialModel)
        )
        return self.session.scalars(stmt).one()


class SpaceMembershipRepository(SqlAlchemyRepository[SpaceMembershipModel]):
    model = SpaceMembershipModel

    def get_by_user_and_space(
        self,
        *,
        user_account_id: str,
        space_id: str,
    ) -> SpaceMembershipModel | None:
        stmt = select(SpaceMembershipModel).where(
            SpaceMembershipModel.user_account_id == user_account_id,
            SpaceMembershipModel.space_id == space_id,
        )
        return self.session.scalars(stmt).first()


class DownstreamChannelCredentialTypeBalanceRepository(
    SqlAlchemyRepository[DownstreamChannelCredentialTypeBalanceModel]
):
    model = DownstreamChannelCredentialTypeBalanceModel

    def get_for_channel_type(
        self,
        *,
        downstream_channel_id: str,
        credential_type: str,
    ) -> DownstreamChannelCredentialTypeBalanceModel | None:
        return self.session.get(
            DownstreamChannelCredentialTypeBalanceModel,
            {
                "downstream_channel_id": downstream_channel_id,
                "credential_type": credential_type,
            },
        )


class SpacePushBindingRepository(SqlAlchemyRepository[SpacePushBindingModel]):
    model = SpacePushBindingModel


class SpacePushAttemptRepository(SqlAlchemyRepository[SpacePushAttemptModel]):
    model = SpacePushAttemptModel


class SpaceCredentialUsageStateRepository(
    SqlAlchemyRepository[SpaceCredentialUsageStateModel]
):
    model = SpaceCredentialUsageStateModel


class SpaceUsageCheckRepository(SqlAlchemyRepository[SpaceUsageCheckModel]):
    model = SpaceUsageCheckModel


class SpaceRecycleRuleRepository(SqlAlchemyRepository[SpaceRecycleRuleModel]):
    model = SpaceRecycleRuleModel


class SpaceAccountCooldownRepository(SqlAlchemyRepository[SpaceAccountCooldownModel]):
    model = SpaceAccountCooldownModel


class DownstreamChannelRepository(SqlAlchemyRepository[DownstreamChannelModel]):
    model = DownstreamChannelModel


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
                    "proxy_type": values["proxy_type"],
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
        bind_counts = _proxy_bind_counts(UserAccountProxyBindingModel)
        active_bind_count = func.coalesce(bind_counts.c.active_bind_count, 0)
        stmt = (
            select(ProxyInventoryModel)
            .outerjoin(bind_counts, bind_counts.c.proxy_id == ProxyInventoryModel.id)
            .where(
                ProxyInventoryModel.provider == "webshare",
                ProxyInventoryModel.proxy_type == "proxyserver",
                ProxyInventoryModel.proxy_status.in_(("available", "bound")),
                ProxyInventoryModel.provider_valid.is_(True),
            )
            .order_by(active_bind_count.asc(), ProxyInventoryModel.updated_at.asc())
            .with_for_update(of=ProxyInventoryModel, skip_locked=True)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def least_bound_static_available_for_update(self) -> ProxyInventoryModel | None:
        bind_counts = _proxy_bind_counts(TeamAdminProxyBindingModel)
        active_bind_count = func.coalesce(bind_counts.c.active_bind_count, 0)
        stmt = (
            select(ProxyInventoryModel)
            .outerjoin(bind_counts, bind_counts.c.proxy_id == ProxyInventoryModel.id)
            .where(
                ProxyInventoryModel.provider == "webshare",
                ProxyInventoryModel.proxy_type == "static_proxy",
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


class TeamAdminProxyBindingRepository(SqlAlchemyRepository[TeamAdminProxyBindingModel]):
    model = TeamAdminProxyBindingModel

    def upsert_active_binding(self, values: dict) -> TeamAdminProxyBindingModel:
        stmt = (
            insert(TeamAdminProxyBindingModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["team_admin_session_id"],
                set_={
                    "proxy_id": values["proxy_id"],
                    "bind_status": values["bind_status"],
                    "bind_reason": values["bind_reason"],
                    "bound_at": values["bound_at"],
                    "last_error_code": "",
                    "updated_at": values["updated_at"],
                },
            )
            .returning(TeamAdminProxyBindingModel)
        )
        return self.session.scalars(stmt).one()


def _proxy_bind_counts(binding_model):
    return (
        select(
            binding_model.proxy_id.label("proxy_id"),
            func.count(binding_model.id).label("active_bind_count"),
        )
        .where(binding_model.bind_status == "active")
        .group_by(binding_model.proxy_id)
        .subquery()
    )


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
