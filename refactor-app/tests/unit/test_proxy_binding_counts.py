from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.orm import Session

from refactor_app.api.routes.resources import _active_proxy_binding_counts
from refactor_app.infrastructure.db.models import UserAccountProxyBindingModel


class FakeSession:
    def execute(self, _stmt: Any):
        return SimpleNamespace(all=lambda: [("proxy-1", 3), ("proxy-2", 1)])


def test_active_proxy_binding_counts_returns_page_counts() -> None:
    counts = _active_proxy_binding_counts(
        session=cast(Session, FakeSession()),
        proxy_ids=["proxy-1", "proxy-2", "proxy-3"],
        binding_model=UserAccountProxyBindingModel,
    )

    assert counts == {"proxy-1": 3, "proxy-2": 1}


def test_active_proxy_binding_counts_skips_query_for_empty_page() -> None:
    session = SimpleNamespace(execute=lambda _stmt: (_ for _ in ()).throw(AssertionError()))

    assert _active_proxy_binding_counts(
        session=cast(Session, session),
        proxy_ids=[],
        binding_model=UserAccountProxyBindingModel,
    ) == {}
