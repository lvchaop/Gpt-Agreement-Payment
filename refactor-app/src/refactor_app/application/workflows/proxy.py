from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.domain.enums import ProxyBindStatus, ProxyStatus
from refactor_app.infrastructure.db.models import (
    ProxyInventoryModel,
    TeamAdminProxyBindingModel,
    TeamAdminSessionModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import ProxyNode, ProxyProvider


class ProxyWorkflowError(RuntimeError):
    pass


class RefreshWebsharePoolWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        proxy_provider: ProxyProvider,
        proxy_type: str = "proxyserver",
    ) -> None:
        self._session_factory = session_factory
        self._proxy_provider = proxy_provider
        self._proxy_type = proxy_type

    def run(self) -> int:
        proxies = self._proxy_provider.list_proxies()
        now = datetime.now(UTC)

        with UnitOfWork(self._session_factory) as uow:
            if uow.proxy_inventory is None:
                raise ProxyWorkflowError("proxy_inventory repository is not initialized")
            for proxy in proxies:
                uow.proxy_inventory.upsert_from_values(
                    proxy_inventory_values(proxy, now, proxy_type=self._proxy_type)
                )

        return len(proxies)


class BindAccountProxyWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(
        self,
        *,
        user_account_id: str,
        bound_by_job_id: str = "",
        bind_reason: str = "",
    ) -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.user_accounts is None:
                raise ProxyWorkflowError("user_accounts repository is not initialized")
            if uow.proxy_inventory is None:
                raise ProxyWorkflowError("proxy_inventory repository is not initialized")
            if uow.user_account_proxy_bindings is None:
                raise ProxyWorkflowError("proxy binding repository is not initialized")

            account = uow.user_accounts.get(user_account_id)
            if account is None:
                raise ProxyWorkflowError(f"user account not found: {user_account_id}")

            proxy = uow.proxy_inventory.first_available()
            if proxy is None:
                raise ProxyWorkflowError("no available webshare proxy")

            binding = uow.user_account_proxy_bindings.upsert_active_binding(
                {
                    "id": f"proxy-binding-{uuid4()}",
                    "user_account_id": user_account_id,
                    "proxy_id": proxy.id,
                    "bind_status": ProxyBindStatus.ACTIVE.value,
                    "bind_reason": bind_reason,
                    "bound_by_job_id": bound_by_job_id,
                    "bound_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            proxy.proxy_status = ProxyStatus.BOUND.value
            proxy.updated_at = now

            return binding.id


class BindTeamAdminProxyWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(
        self,
        *,
        team_admin_session_id: str,
        bind_reason: str = "",
    ) -> str:
        with self._session_factory() as session:
            binding = bind_team_admin_static_proxy_in_session(
                session=session,
                team_admin_session_id=team_admin_session_id,
                bind_reason=bind_reason,
            )
            session.commit()
            return binding.id


def bind_team_admin_static_proxy_in_session(
    *,
    session: Session,
    team_admin_session_id: str,
    bind_reason: str = "",
) -> TeamAdminProxyBindingModel:
    now = datetime.now(UTC)
    admin_session = session.get(TeamAdminSessionModel, team_admin_session_id)
    if admin_session is None:
        raise ProxyWorkflowError(f"team admin session not found: {team_admin_session_id}")

    pending = _pending_team_admin_proxy_binding(session, team_admin_session_id)
    if pending is not None and pending.bind_status == ProxyBindStatus.ACTIVE.value:
        return pending

    existing = _active_team_admin_proxy_binding(session, team_admin_session_id)
    if existing is not None:
        return existing

    proxy = _least_bound_static_proxy_for_update(session)
    if proxy is None:
        raise ProxyWorkflowError("no available static webshare proxy")

    binding = pending or session.scalars(
        select(TeamAdminProxyBindingModel)
        .where(TeamAdminProxyBindingModel.team_admin_session_id == team_admin_session_id)
        .with_for_update()
    ).first()
    if binding is None:
        binding = TeamAdminProxyBindingModel(
            id=f"team-admin-proxy-binding-{uuid4()}",
            team_admin_session_id=team_admin_session_id,
            proxy_id=proxy.id,
            bind_status=ProxyBindStatus.ACTIVE.value,
            bind_reason=bind_reason,
            bound_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(binding)
    else:
        binding.proxy_id = proxy.id
        binding.bind_status = ProxyBindStatus.ACTIVE.value
        binding.bind_reason = bind_reason
        binding.bound_at = now
        binding.last_error_code = ""
        binding.updated_at = now
    proxy.proxy_status = ProxyStatus.BOUND.value
    proxy.updated_at = now
    return binding


def reassign_team_admin_static_proxy_in_session(
    *,
    session: Session,
    team_admin_session_id: str,
    error_code: str,
    bind_reason: str = "",
) -> TeamAdminProxyBindingModel:
    now = datetime.now(UTC)
    binding = _pending_team_admin_proxy_binding(session, team_admin_session_id) or session.scalars(
        select(TeamAdminProxyBindingModel)
        .where(TeamAdminProxyBindingModel.team_admin_session_id == team_admin_session_id)
        .with_for_update()
    ).first()
    if binding is not None:
        old_proxy = session.get(ProxyInventoryModel, binding.proxy_id)
        if old_proxy is not None:
            old_proxy.proxy_status = ProxyStatus.ERROR.value
            old_proxy.provider_valid = False
            old_proxy.updated_at = now
        binding.bind_status = ProxyBindStatus.RELEASED.value
        binding.last_error_code = error_code[:200]
        binding.updated_at = now
    return bind_team_admin_static_proxy_in_session(
        session=session,
        team_admin_session_id=team_admin_session_id,
        bind_reason=bind_reason,
    )


def _pending_team_admin_proxy_binding(
    session: Session,
    team_admin_session_id: str,
) -> TeamAdminProxyBindingModel | None:
    for obj in session.new:
        if (
            isinstance(obj, TeamAdminProxyBindingModel)
            and obj.team_admin_session_id == team_admin_session_id
        ):
            return obj
    return None


def ensure_team_admin_static_proxy_url_in_session(
    *,
    session: Session,
    team_admin_session_id: str,
    bind_reason: str = "",
) -> str:
    binding = bind_team_admin_static_proxy_in_session(
        session=session,
        team_admin_session_id=team_admin_session_id,
        bind_reason=bind_reason,
    )
    proxy = session.get(ProxyInventoryModel, binding.proxy_id)
    if proxy is None:
        raise ProxyWorkflowError("team admin proxy disappeared")
    return proxy_url_from_inventory(proxy)


def allocate_team_admin_invite_static_proxies_in_session(
    *,
    session: Session,
    team_admin_session_id: str,
    count: int,
) -> list[ProxyInventoryModel]:
    if count < 1:
        raise ProxyWorkflowError("invite static proxy count must be positive")
    if session.get(TeamAdminSessionModel, team_admin_session_id) is None:
        raise ProxyWorkflowError(f"team admin session not found: {team_admin_session_id}")

    proxies = list(
        session.scalars(
            select(ProxyInventoryModel)
            .where(
                ProxyInventoryModel.provider == "webshare",
                ProxyInventoryModel.proxy_type == "static_proxy",
                ProxyInventoryModel.proxy_status == ProxyStatus.AVAILABLE.value,
                ProxyInventoryModel.provider_valid.is_(True),
                ~ProxyInventoryModel.id.in_(_active_invite_proxy_ids()),
            )
            .order_by(ProxyInventoryModel.updated_at.asc(), ProxyInventoryModel.id.asc())
            .with_for_update(of=ProxyInventoryModel, skip_locked=True)
            .limit(count)
        ).all()
    )
    if len(proxies) != count:
        raise ProxyWorkflowError(
            f"not enough available static webshare proxies: required={count} actual={len(proxies)}"
        )

    now = datetime.now(UTC)
    for proxy in proxies:
        proxy.updated_at = now
    return proxies


def _active_team_admin_proxy_binding(
    session: Session,
    team_admin_session_id: str,
) -> TeamAdminProxyBindingModel | None:
    row = session.execute(
        select(TeamAdminProxyBindingModel, ProxyInventoryModel)
        .join(ProxyInventoryModel, ProxyInventoryModel.id == TeamAdminProxyBindingModel.proxy_id)
        .where(
            TeamAdminProxyBindingModel.team_admin_session_id == team_admin_session_id,
            TeamAdminProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
            ProxyInventoryModel.provider == "webshare",
            ProxyInventoryModel.proxy_type == "static_proxy",
            ProxyInventoryModel.proxy_status.in_(
                (ProxyStatus.AVAILABLE.value, ProxyStatus.BOUND.value)
            ),
            ProxyInventoryModel.provider_valid.is_(True),
            ~ProxyInventoryModel.id.in_(_active_invite_proxy_ids()),
        )
        .with_for_update(of=TeamAdminProxyBindingModel)
        .limit(1)
    ).first()
    if row is None:
        return None
    binding, _proxy = row
    return binding


def _least_bound_static_proxy_for_update(session: Session) -> ProxyInventoryModel | None:
    from sqlalchemy import func

    bind_counts = (
        select(
            TeamAdminProxyBindingModel.proxy_id.label("proxy_id"),
            func.count(TeamAdminProxyBindingModel.id).label("active_bind_count"),
        )
        .where(TeamAdminProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value)
        .group_by(TeamAdminProxyBindingModel.proxy_id)
        .subquery()
    )
    active_bind_count = func.coalesce(bind_counts.c.active_bind_count, 0)
    stmt = (
        select(ProxyInventoryModel)
        .outerjoin(bind_counts, bind_counts.c.proxy_id == ProxyInventoryModel.id)
        .where(
            ProxyInventoryModel.provider == "webshare",
            ProxyInventoryModel.proxy_type == "static_proxy",
            ProxyInventoryModel.proxy_status.in_(
                (ProxyStatus.AVAILABLE.value, ProxyStatus.BOUND.value)
            ),
            ProxyInventoryModel.provider_valid.is_(True),
        )
        .order_by(active_bind_count.asc(), ProxyInventoryModel.updated_at.asc())
        .with_for_update(of=ProxyInventoryModel, skip_locked=True)
        .limit(1)
    )
    return session.scalars(stmt).first()


def _active_invite_proxy_ids():
    return select(WorkItemModel.input_json["invite_proxy_id"].astext).where(
        WorkItemModel.work_type == "space.membership_invite.account",
        WorkItemModel.work_status.in_(("queued", "running")),
        WorkItemModel.input_json["invite_proxy_id"].astext != "",
    )


class HealthcheckProxyWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, *, proxy_id: str) -> dict:
        from refactor_app.application.workflows.account_auth import _probe_proxy_alive

        now = datetime.now(UTC)
        with self._session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is None:
                raise ProxyWorkflowError(f"proxy not found: {proxy_id}")
            proxy_url = proxy_url_from_inventory(proxy)

        alive = _probe_proxy_alive(proxy_url)
        released_bind_count = 0
        now = datetime.now(UTC)
        with self._session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is None:
                raise ProxyWorkflowError(f"proxy not found: {proxy_id}")
            proxy.last_healthcheck_at = now
            proxy.provider_valid = alive
            user_bindings = session.scalars(
                select(UserAccountProxyBindingModel).where(
                    UserAccountProxyBindingModel.proxy_id == proxy_id,
                    UserAccountProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
                )
            ).all()
            admin_bindings = session.scalars(
                select(TeamAdminProxyBindingModel).where(
                    TeamAdminProxyBindingModel.proxy_id == proxy_id,
                    TeamAdminProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
                )
            ).all()
            active_bindings = [*user_bindings, *admin_bindings]
            proxy.proxy_status = _proxy_status_after_healthcheck(
                alive=alive,
                has_active_binding=bool(active_bindings),
            )
            proxy.updated_at = now

            if not alive:
                released_bind_count = len(active_bindings)
                for binding in active_bindings:
                    binding.bind_status = ProxyBindStatus.RELEASED.value
                    binding.last_error_code = "proxy_healthcheck_failed"
                    binding.updated_at = now

            session.commit()
        return {
            "proxy_id": proxy_id,
            "alive": alive,
            "released_bind_count": released_bind_count,
        }


def _proxy_status_after_healthcheck(*, alive: bool, has_active_binding: bool) -> str:
    if not alive:
        return ProxyStatus.ERROR.value
    return ProxyStatus.BOUND.value if has_active_binding else ProxyStatus.AVAILABLE.value


def proxy_inventory_values(
    proxy: ProxyNode,
    now: datetime,
    *,
    proxy_type: str | None = None,
) -> dict:
    return {
        "id": f"proxy-webshare-{proxy.external_proxy_id}",
        "provider": proxy.provider,
        "proxy_type": proxy_type or proxy.proxy_type or "proxyserver",
        "external_proxy_id": proxy.external_proxy_id,
        "connection_mode": proxy.connection_mode,
        "proxy_host": proxy.proxy_host,
        "proxy_port": proxy.proxy_port,
        "proxy_scheme": proxy.proxy_scheme,
        "proxy_username": proxy.proxy_username,
        "proxy_password": proxy.proxy_password,
        "country_code": proxy.country_code,
        "city_name": proxy.city_name,
        "asn_name": proxy.asn_name,
        "proxy_status": (
            ProxyStatus.AVAILABLE.value if proxy.provider_valid else ProxyStatus.INVALID.value
        ),
        "provider_valid": proxy.provider_valid,
        "last_provider_verification_at": proxy.last_provider_verification_at,
        "created_at": now,
        "updated_at": now,
    }


def proxy_url_from_inventory(proxy: ProxyInventoryModel) -> str:
    from urllib.parse import quote

    scheme = proxy.proxy_scheme or "http"
    host = proxy.proxy_host
    port = proxy.proxy_port
    if proxy.proxy_username:
        username = quote(proxy.proxy_username, safe="")
        password = quote(proxy.proxy_password or "", safe="")
        return f"{scheme}://{username}:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def proxy_inventory_model_from_node(proxy: ProxyNode, now: datetime) -> ProxyInventoryModel:
    return ProxyInventoryModel(**proxy_inventory_values(proxy, now))
