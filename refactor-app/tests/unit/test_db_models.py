from __future__ import annotations

from refactor_app.infrastructure.db.models import Base


def test_sqlalchemy_models_cover_initial_schema_tables() -> None:
    assert set(Base.metadata.tables) == {
        "user_accounts",
        "team_workspaces",
        "user_account_auth",
        "user_account_team_workspace_memberships",
        "workspace_join_batches",
        "workspace_join_batch_items",
        "codex_oauth_credentials",
        "downstream_codex_push_records",
        "proxy_inventory",
        "user_account_proxy_bindings",
        "external_mail_leases",
        "jobs",
        "work_items",
        "job_runs",
        "job_steps",
        "job_events",
    }


def test_active_batch_partial_unique_index_is_mapped() -> None:
    batch_table = Base.metadata.tables["workspace_join_batches"]

    index = next(
        idx for idx in batch_table.indexes if idx.name == "uq_workspace_join_batches_one_active"
    )

    assert index.unique is True
    where_sql = str(index.dialect_options["postgresql"]["where"])
    assert "workspace_join_batches.activation_status" in where_sql


def test_user_account_auth_contains_login_recovery_fields() -> None:
    table = Base.metadata.tables["user_account_auth"]

    assert {
        "password",
        "session_token",
        "refresh_token",
        "cookie_header",
        "device_id",
        "csrf_token",
        "session_status",
        "last_session_refresh_at",
    }.issubset(table.columns.keys())
    assert "access_token" not in table.columns
    assert "id_token" not in table.columns
