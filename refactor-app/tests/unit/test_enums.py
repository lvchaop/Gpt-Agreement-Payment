from __future__ import annotations

from refactor_app.domain.enums import (
    AccountStatus,
    ActivationStatus,
    DownstreamProvider,
    PushStatus,
)


def test_core_enum_values_match_schema_terms() -> None:
    assert {item.value for item in AccountStatus} == {"active", "invalid"}
    assert "active" in {item.value for item in ActivationStatus}
    assert {item.value for item in DownstreamProvider} == {"cpa", "sub2api"}
    assert {item.value for item in PushStatus} == {"pending", "pushed", "failed", "skipped"}
