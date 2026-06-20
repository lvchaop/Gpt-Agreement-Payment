from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from refactor_app.application.workflows.proxy import (
    BindAccountProxyWorkflow,
    RefreshWebsharePoolWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    ProxyInventoryModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
)
from refactor_app.plugins.contracts import HealthcheckResult, ProxyNode


class StaticProxyProvider:
    name = "static-webshare-test"

    def __init__(self, proxies: list[ProxyNode]) -> None:
        self._proxies = proxies

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["ops.proxy.fetch_webshare_pool"]

    def list_proxies(self) -> list[ProxyNode]:
        return self._proxies


def test_refresh_webshare_pool_upserts_inventory_and_bind_account_proxy() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    account_id = "test-proxy-workflow-account"
    proxy_id = "proxy-webshare-proxy-1"
    now = datetime.now(UTC)

    with session_factory() as session:
        session.execute(delete(UserAccountProxyBindingModel).where(
            UserAccountProxyBindingModel.user_account_id == account_id
        ))
        session.execute(delete(ProxyInventoryModel).where(ProxyInventoryModel.id == proxy_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="proxy-workflow@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticProxyProvider(
        [
            ProxyNode(
                provider="webshare",
                external_proxy_id="proxy-1",
                connection_mode="direct",
                proxy_host="1.2.3.4",
                proxy_port=1111,
                proxy_scheme="http",
                proxy_username="u",
                proxy_password="p",
                provider_valid=True,
            )
        ]
    )

    refresh_count = RefreshWebsharePoolWorkflow(
        session_factory=session_factory,
        proxy_provider=provider,
    ).run()
    binding_id = BindAccountProxyWorkflow(session_factory=session_factory).run(
        user_account_id=account_id,
        bound_by_job_id="job-1",
        bind_reason="test",
    )

    with session_factory() as session:
        proxy = session.get(ProxyInventoryModel, proxy_id)
        binding = session.get(UserAccountProxyBindingModel, binding_id)
        bindings = session.scalars(
            select(UserAccountProxyBindingModel).where(
                UserAccountProxyBindingModel.user_account_id == account_id
            )
        ).all()

        assert refresh_count == 1
        assert proxy is not None
        assert proxy.proxy_host == "1.2.3.4"
        assert proxy.proxy_status == "bound"
        assert binding is not None
        assert binding.proxy_id == proxy_id
        assert binding.bind_status == "active"
        assert len(bindings) == 1

        session.execute(delete(UserAccountProxyBindingModel).where(
            UserAccountProxyBindingModel.user_account_id == account_id
        ))
        session.execute(delete(ProxyInventoryModel).where(ProxyInventoryModel.id == proxy_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()
