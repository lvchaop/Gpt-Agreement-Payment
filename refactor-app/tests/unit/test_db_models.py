from __future__ import annotations

from refactor_app.infrastructure.db.models import Base


def test_sqlalchemy_models_cover_initial_schema_tables() -> None:
    assert {
        "account_session_otp_snapshots",
        "automation_schedules",
        "downstream_channel_credential_type_balances",
        "downstream_channels",
        "external_mail_leases",
        "job_events",
        "job_runs",
        "job_steps",
        "jobs",
        "proxy_inventory",
        "space_account_cooldowns",
        "space_credential_usage_states",
        "space_credentials",
        "space_memberships",
        "space_push_attempts",
        "space_push_bindings",
        "space_recycle_rules",
        "space_usage_checks",
        "spaces",
        "team_admin_account_checks",
        "team_admin_proxy_bindings",
        "team_admin_sessions",
        "user_account_proxy_bindings",
        "user_accounts",
        "work_items",
    }.issubset(set(Base.metadata.tables))

    assert "space_recycle_tasks" not in Base.metadata.tables


def test_user_accounts_contains_login_recovery_fields() -> None:
    table = Base.metadata.tables["user_accounts"]

    assert {
        "password",
        "session_token",
        "cookie_header",
        "auth_cookie_header",
        "device_id",
        "csrf_token",
        "access_token",
        "session_status",
        "last_session_refresh_at",
        "codex_select_channel_required",
        "codex_select_channel_detected_at",
    }.issubset(table.columns.keys())
    assert "refresh_token" not in table.columns
    assert "id_token" not in table.columns


def test_space_tables_have_expected_unique_keys() -> None:
    spaces = Base.metadata.tables["spaces"]
    credentials = Base.metadata.tables["space_credentials"]
    balances = Base.metadata.tables["downstream_channel_credential_type_balances"]

    assert {"provider", "external_space_id"}.issubset(spaces.columns.keys())
    assert {"space_id", "user_account_id"}.issubset(credentials.columns.keys())
    assert {"downstream_channel_id", "credential_type"} == {
        column.name for column in balances.primary_key.columns
    }


def test_non_space_runtime_tables_are_not_target_schema() -> None:
    non_space_runtime_tables = {
        "codex_oauth_credentials",
        "downstream_codex_push_records",
        "remote_member_release_tasks",
        "team_workspaces",
        "user_account_auth",
        "workspace_join_batches",
        "workspace_join_batch_items",
    }

    assert non_space_runtime_tables.isdisjoint(set(Base.metadata.tables))


def test_work_items_contains_unified_dispatch_fields() -> None:
    table = Base.metadata.tables["work_items"]

    assert {"execution_key", "lease_expires_at"}.issubset(table.columns.keys())
    checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if hasattr(constraint, "sqltext")
    }
    assert any("'skipped'" in check and "work_status" in check for check in checks)
