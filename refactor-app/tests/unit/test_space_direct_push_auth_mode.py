from __future__ import annotations

from datetime import UTC, datetime

from refactor_app.application.workflows.space_direct_push import _push_payload
from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamPushResult


class RecordingProvider:
    def __init__(self) -> None:
        self.codex_calls = 0
        self.business_at_calls = 0

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        self.codex_calls += 1
        return DownstreamPushResult(pushed=True, downstream_external_id=payload.email)

    def push_business_access_token(self, payload: dict) -> DownstreamPushResult:
        self.business_at_calls += 1
        return DownstreamPushResult(pushed=True, downstream_external_id=str(payload.get("name")))


def test_team_codex_oauth_payload_uses_codex_downstream_method() -> None:
    provider = RecordingProvider()
    payload = DownstreamCodexPayload(
        access_token="access",
        id_token="id",
        refresh_token="refresh",
        email="business-oauth@example.test",
        account_id="user-1",
        downstream_chatgpt_account_id="downstream-1",
        token_chatgpt_account_id="workspace-1",
        client_id="client-1",
        expires_at=datetime.now(UTC),
    )

    result = _push_payload(
        provider=provider,
        payload=payload,
        payload_type="team_monthly",
    )

    assert result.pushed is True
    assert provider.codex_calls == 1
    assert provider.business_at_calls == 0


def test_team_backend_access_token_payload_uses_business_at_method() -> None:
    provider = RecordingProvider()

    result = _push_payload(
        provider=provider,
        payload={"name": "business-at"},
        payload_type="team_5h_weekly",
    )

    assert result.pushed is True
    assert provider.codex_calls == 0
    assert provider.business_at_calls == 1
