from __future__ import annotations

import json

from refactor_app.plugins.downstream_cpa.client import build_cpa_business_access_token_auth_file
from refactor_app.plugins.downstream_sub2api.client import (
    build_sub2api_business_access_token_import_payload,
)


def sample_business_payload() -> dict:
    return {
        "exported_at": "2026-07-04T05:48:27Z",
        "proxies": [],
        "accounts": [
            {
                "name": "母-owner@example.test-子-child@example.test",
                "platform": "openai",
                "type": "oauth",
                "credentials": {
                    "access_token": "at-1",
                    "auth_mode": "personalAccessToken",
                    "chatgpt_account_id": "space-1",
                    "chatgpt_user_id": "user-1",
                    "email": "child@example.test",
                    "openai_auth_mode": "personal_access_token",
                    "plan_type": "team",
                    "token_type": "Bearer",
                },
                "extra": {},
            }
        ],
    }


def test_sub2api_business_access_token_payload_wraps_export_file() -> None:
    body = build_sub2api_business_access_token_import_payload(sample_business_payload())

    assert body["name"] == "pat-child@example.test-space-1.json"
    content = json.loads(body["content"])
    credentials = content["accounts"][0]["credentials"]
    assert credentials["access_token"] == "at-1"
    assert credentials["chatgpt_account_id"] == "space-1"
    assert "refresh_token" not in credentials


def test_cpa_business_access_token_payload_uses_same_body() -> None:
    payload = sample_business_payload()
    name, body = build_cpa_business_access_token_auth_file(payload)

    assert name.endswith("-child@example.test-space-1.json")
    assert body == payload
