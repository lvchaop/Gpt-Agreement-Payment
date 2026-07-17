from refactor_app.api.routes.resources import (
    _proxy_status_filter_values,
    _proxy_type_filter_values,
)


def test_proxy_filter_values_accept_current_and_cached_frontend_values() -> None:
    assert _proxy_type_filter_values("proxyserver,proxy_server") == [
        "proxyserver",
        "proxyserver",
    ]
    assert _proxy_status_filter_values("available,bound,allocated,error,dead") == [
        "available",
        "bound",
        "bound",
        "error",
        "error",
    ]
