from __future__ import annotations

from pathlib import Path


def test_migration_sql_matches_design_schema() -> None:
    root = Path(__file__).resolve().parents[2]
    design = root / "docs" / "schema" / "001_initial_schema.sql"
    migration = root / "migrations" / "sql" / "001_initial_schema.sql"

    assert migration.read_text() == design.read_text()
