from refactor_app.application.workflows.proxy import _proxy_status_after_healthcheck


def test_proxy_healthcheck_status_follows_real_binding_state() -> None:
    assert _proxy_status_after_healthcheck(alive=True, has_active_binding=False) == "available"
    assert _proxy_status_after_healthcheck(alive=True, has_active_binding=True) == "bound"
    assert _proxy_status_after_healthcheck(alive=False, has_active_binding=False) == "error"
    assert _proxy_status_after_healthcheck(alive=False, has_active_binding=True) == "error"
