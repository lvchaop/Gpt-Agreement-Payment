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
        "payment_address_pool",
        "payment_card_pool",
        "payment_name_pool",
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
        "password_status",
        "password_last_error_code",
        "password_last_error_message",
        "mfa_status",
        "twofauth_account_id",
        "mfa_last_error_code",
        "mfa_last_error_message",
        "security_setup_last_attempt_at",
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


def test_personal_payment_method_tables_have_plaintext_card_fields() -> None:
    spaces = Base.metadata.tables["spaces"]
    cards = Base.metadata.tables["payment_card_pool"]
    names = Base.metadata.tables["payment_name_pool"]
    addresses = Base.metadata.tables["payment_address_pool"]

    assert {
        "has_promotion",
        "promotion_id",
        "has_payment_method",
        "payment_method_status",
        "payment_method_attempt_count",
        "payment_method_id",
        "payment_method_last4",
        "payment_method_last_attempt_at",
        "payment_method_cooldown_until",
        "payment_method_last_error_code",
        "payment_method_last_error_message",
    }.issubset(spaces.columns.keys())
    assert {
        "card_number",
        "cvc",
        "card_fingerprint",
        "last4",
        "card_status",
        "reserved_by_space_id",
        "reserved_at",
    }.issubset(cards.columns.keys())
    assert {"full_name", "normalized_name", "name_status"}.issubset(names.columns.keys())
    assert {"line1", "city", "postal_code", "country", "address_status"}.issubset(
        addresses.columns.keys()
    )


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
