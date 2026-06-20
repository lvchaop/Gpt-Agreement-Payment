from __future__ import annotations

import httpx
import pytest

from refactor_app.plugins.contracts import ProxyProvider
from refactor_app.plugins.proxy_webshare import (
    WebshareClient,
    WebshareClientConfig,
    WebshareProxyPlugin,
)
from refactor_app.plugins.proxy_webshare.client import WebshareClientError


def test_webshare_client_lists_paginated_proxies() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Token token-1"
        if str(request.url).endswith("/api/v2/proxy/list/?mode=direct&page=1&page_size=2"):
            return httpx.Response(
                200,
                json={
                    "next": "https://proxy.webshare.io/api/v2/proxy/list/?page=2&page_size=2",
                    "results": [
                        {
                            "id": "proxy-1",
                            "username": "u1",
                            "password": "p1",
                            "proxy_address": "1.2.3.4",
                            "port": 1111,
                            "valid": True,
                            "last_verification": "2026-06-19T01:02:03Z",
                            "country_code": "US",
                            "city_name": "Los Angeles",
                            "asn_name": "Example ASN",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "next": None,
                "results": [
                    {
                        "id": "proxy-2",
                        "username": "u2",
                        "password": "p2",
                        "proxy_address": "5.6.7.8",
                        "port": 2222,
                        "valid": False,
                    }
                ],
            },
        )

    http_client = httpx.Client(
        base_url="https://proxy.webshare.io",
        headers={"Authorization": "Token token-1"},
        transport=httpx.MockTransport(handler),
    )
    client = WebshareClient(
        WebshareClientConfig(api_token="token-1", page_size=2),
        http_client=http_client,
    )

    proxies = client.list_proxy_nodes()

    assert [proxy.external_proxy_id for proxy in proxies] == ["proxy-1", "proxy-2"]
    assert proxies[0].provider == "webshare"
    assert proxies[0].connection_mode == "direct"
    assert proxies[0].proxy_host == "1.2.3.4"
    assert proxies[0].proxy_port == 1111
    assert proxies[0].provider_valid is True
    assert proxies[1].provider_valid is False
    assert len(requests) == 2


def test_webshare_client_lists_downloaded_proxy_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "Authorization" not in request.headers
        assert str(request.url) == "https://proxy.webshare.io/download.txt"
        return httpx.Response(
            200,
            text="1.2.3.4:1111:user1:pass1\n5.6.7.8:2222:user2:pass2\n",
        )

    http_client = httpx.Client(
        base_url="https://proxy.webshare.io",
        transport=httpx.MockTransport(handler),
    )
    client = WebshareClient(
        WebshareClientConfig(api_token="", download_url="https://proxy.webshare.io/download.txt"),
        http_client=http_client,
    )

    proxies = client.list_proxy_nodes()

    assert [proxy.proxy_host for proxy in proxies] == ["1.2.3.4", "5.6.7.8"]
    assert proxies[0].connection_mode == "direct"
    assert proxies[0].proxy_port == 1111
    assert proxies[0].proxy_username == "user1"
    assert proxies[0].proxy_password == "pass1"
    assert proxies[0].provider_valid is True
    assert len(requests) == 1


def test_webshare_client_rejects_missing_required_fields() -> None:
    http_client = httpx.Client(
        base_url="https://proxy.webshare.io",
        headers={"Authorization": "Token token-1"},
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"next": None, "results": [{"id": "p1"}]})
        ),
    )
    client = WebshareClient(
        WebshareClientConfig(api_token="token-1"),
        http_client=http_client,
    )

    with pytest.raises(WebshareClientError):
        client.list_proxy_nodes()


def test_webshare_plugin_implements_proxy_provider_contract() -> None:
    http_client = httpx.Client(
        base_url="https://proxy.webshare.io",
        headers={"Authorization": "Token token-1"},
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"next": None, "results": []})
        ),
    )
    plugin: ProxyProvider = WebshareProxyPlugin(
        WebshareClient(WebshareClientConfig(api_token="token-1"), http_client=http_client)
    )

    assert plugin.healthcheck().status == "ok"
    assert "ops.proxy.fetch_webshare_pool" in plugin.capabilities()
    assert plugin.list_proxies() == []
