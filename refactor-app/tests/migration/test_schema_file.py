from __future__ import annotations

from pathlib import Path


def test_space_migrations_cover_target_runtime_tables() -> None:
    root = Path(__file__).resolve().parents[2]
    migration_sql = "\n".join(
        path.read_text() for path in sorted((root / "migrations" / "sql").glob("*.sql"))
    )

    for table_name in (
        "spaces",
        "space_credentials",
        "space_memberships",
        "space_push_bindings",
        "downstream_channel_credential_type_balances",
    ):
        assert table_name in migration_sql

    assert "DROP TABLE IF EXISTS user_account_auth" in migration_sql
