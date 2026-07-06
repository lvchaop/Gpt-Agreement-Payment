from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.domain.enums import ProxyBindStatus, ProxyStatus
from refactor_app.infrastructure.db.models import ProxyInventoryModel, UserAccountProxyBindingModel
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


class HealthcheckProxyWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, *, proxy_id: str) -> dict:
        from refactor_app.application.workflows.account_auth import _probe_proxy_alive, _proxy_url

        now = datetime.now(UTC)
        with self._session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is None:
                raise ProxyWorkflowError(f"proxy not found: {proxy_id}")
            proxy_url = _proxy_url(proxy)

        alive = _probe_proxy_alive(proxy_url)
        released_bind_count = 0
        now = datetime.now(UTC)
        with self._session_factory() as session:
            proxy = session.get(ProxyInventoryModel, proxy_id)
            if proxy is None:
                raise ProxyWorkflowError(f"proxy not found: {proxy_id}")
            proxy.last_healthcheck_at = now
            proxy.provider_valid = alive
            proxy.proxy_status = ProxyStatus.BOUND.value if alive else ProxyStatus.ERROR.value
            proxy.updated_at = now

            if not alive:
                bindings = session.scalars(
                    select(UserAccountProxyBindingModel)
                    .where(
                        UserAccountProxyBindingModel.proxy_id == proxy_id,
                        UserAccountProxyBindingModel.bind_status == ProxyBindStatus.ACTIVE.value,
                    )
                ).all()
                released_bind_count = len(bindings)
                for binding in bindings:
                    binding.bind_status = ProxyBindStatus.RELEASED.value
                    binding.last_error_code = "proxy_healthcheck_failed"
                    binding.updated_at = now

            session.commit()
        return {
            "proxy_id": proxy_id,
            "alive": alive,
            "released_bind_count": released_bind_count,
        }


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


def proxy_inventory_model_from_node(proxy: ProxyNode, now: datetime) -> ProxyInventoryModel:
    return ProxyInventoryModel(**proxy_inventory_values(proxy, now))
