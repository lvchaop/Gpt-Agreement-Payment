from __future__ import annotations

import httpx


def make_http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)
