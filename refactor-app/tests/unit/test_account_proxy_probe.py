from types import SimpleNamespace

from refactor_app.application.workflows import account_auth


class _Session:
    def __init__(self, response) -> None:
        self.response = response
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def get(self, url: str, **kwargs):
        self.request = (url, kwargs)
        return self.response


def test_proxy_probe_requires_successful_chatgpt_csrf(monkeypatch) -> None:
    session = _Session(
        SimpleNamespace(status_code=200, json=lambda: {"csrfToken": "csrf-token"})
    )
    monkeypatch.setattr(
        account_auth.curl_requests,
        "Session",
        lambda **_kwargs: session,
    )

    assert account_auth._probe_proxy_alive("http://proxy.example") is True
    assert session.request is not None
    assert session.request[0] == "https://chatgpt.com/api/auth/csrf"


def test_proxy_probe_rejects_cloudflare_challenge(monkeypatch) -> None:
    session = _Session(SimpleNamespace(status_code=403, json=lambda: {}))
    monkeypatch.setattr(
        account_auth.curl_requests,
        "Session",
        lambda **_kwargs: session,
    )

    assert account_auth._probe_proxy_alive("http://proxy.example") is False


def test_proxy_probe_rejects_200_without_csrf_token(monkeypatch) -> None:
    session = _Session(SimpleNamespace(status_code=200, json=lambda: {}))
    monkeypatch.setattr(
        account_auth.curl_requests,
        "Session",
        lambda **_kwargs: session,
    )

    assert account_auth._probe_proxy_alive("http://proxy.example") is False
