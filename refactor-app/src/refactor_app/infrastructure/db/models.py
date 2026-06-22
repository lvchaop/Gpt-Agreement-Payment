from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserAccountModel(Base):
    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone_number: Mapped[str] = mapped_column(Text, nullable=False, default="")
    phone_dial_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    phone_country: Mapped[str] = mapped_column(Text, nullable=False, default="")
    openai_user_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("account_status IN ('active', 'invalid')"),
        Index("idx_user_accounts_email", "email"),
        Index("idx_user_accounts_phone_number", "phone_number"),
        Index("idx_user_accounts_openai_user_id", "openai_user_id"),
        Index("idx_user_accounts_account_status", "account_status"),
    )


class TeamWorkspaceModel(Base):
    __tablename__ = "team_workspaces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_workspace_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seat_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seats_in_use: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seats_entitled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workspace_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_admin_session_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_workspace_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_subscription_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_probe_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("provider = 'openai_chatgpt'"),
        CheckConstraint("seat_limit >= 0"),
        CheckConstraint("seats_in_use >= 0"),
        CheckConstraint("seats_entitled >= 0"),
        CheckConstraint(
            "workspace_status IN ('unknown', 'active', 'disabled', 'expired', 'error')"
        ),
        UniqueConstraint("provider", "external_workspace_id"),
        Index("idx_team_workspaces_status", "workspace_status"),
    )


class WorkspaceAutomationStateModel(Base):
    __tablename__ = "workspace_automation_states"

    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    automation_status: Mapped[str] = mapped_column(Text, nullable=False, default="paused")
    invite_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_sent")
    invite_job_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_invite_finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_authorization_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_usage_cleanup_at: Mapped[datetime | None] = mapped_column(nullable=True)
    pause_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("automation_status IN ('active', 'paused', 'stopped', 'error')"),
        CheckConstraint("invite_status IN ('not_sent', 'sent')"),
        Index("idx_workspace_automation_states_status", "automation_status", "invite_status"),
        Index("idx_workspace_automation_states_last_invite", "last_invite_finished_at"),
    )


class TeamAdminSessionModel(Base):
    __tablename__ = "team_admin_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    admin_email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_source: Mapped[str] = mapped_column(
        Text, nullable=False, default="chatgpt_api_auth_session"
    )
    raw_session_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cookie_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    imported_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("idx_team_admin_sessions_email", "admin_email"),
        Index("idx_team_admin_sessions_imported_at", "imported_at"),
    )


class TeamAdminAccountCheckModel(Base):
    __tablename__ = "team_admin_account_checks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    team_admin_session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_admin_sessions.id", ondelete="CASCADE"), nullable=False
    )
    raw_check_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("idx_team_admin_account_checks_session_id", "team_admin_session_id"),
        Index("idx_team_admin_account_checks_checked_at", "checked_at"),
    )


class UserAccountAuthModel(Base):
    __tablename__ = "user_account_auth"

    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    password: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cookie_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_cookie_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personal_chatgpt_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personal_chatgpt_account_discovered_at: Mapped[datetime | None] = mapped_column(
        nullable=True
    )
    device_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refresh_token_status: Mapped[str] = mapped_column(Text, nullable=False)
    session_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    last_refresh_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_session_refresh_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_auth_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_auth_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "refresh_token_status IN "
            "('missing', 'active', 'refreshing', 'expired', 'invalid', 'dead', 'error')"
        ),
        CheckConstraint(
            "session_status IN "
            "('unknown', 'active', 'expired', 'invalid', 'refreshing', 'dead', 'error')"
        ),
    )


class AccountSessionOtpSnapshotModel(Base):
    __tablename__ = "account_session_otp_snapshots"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    source_membership_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot_status: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    otp_code_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prepared_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id"),
        CheckConstraint(
            "snapshot_status IN "
            "('otp_collected', 'otp_pending', 'otp_validated', 'otp_missing', 'failed')"
        ),
        CheckConstraint("otp_code_len >= 0"),
        Index("idx_account_session_otp_snapshots_user_account_id", "user_account_id"),
        Index("idx_account_session_otp_snapshots_status", "snapshot_status"),
        Index("idx_account_session_otp_snapshots_source_membership_id", "source_membership_id"),
    )


class MembershipModel(Base):
    __tablename__ = "user_account_team_workspace_memberships"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    membership_status: Mapped[str] = mapped_column(Text, nullable=False)
    invite_permission: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    user_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seat_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    can_invite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_user_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remote_account_user_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remote_seat_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remote_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remote_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    chatgpt_web_backend_access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chatgpt_web_backend_id_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chatgpt_web_backend_access_token_expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True
    )
    chatgpt_web_backend_access_token_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="unknown"
    )
    last_chatgpt_web_backend_token_refresh_at: Mapped[datetime | None] = mapped_column(
        nullable=True
    )
    last_probe_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_probe_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id", "team_workspace_id"),
        CheckConstraint(
            "membership_status IN "
            "('unknown', 'invited', 'accepted', 'active', 'left', 'disabled', 'banned', 'failed')"
        ),
        CheckConstraint("invite_permission IN ('unknown', 'ok', 'no_permission', 'error')"),
        CheckConstraint("user_count >= 0"),
        CheckConstraint("invite_count >= 0"),
        CheckConstraint("seat_status IN ('unknown', 'available', 'full', 'error')"),
        CheckConstraint(
            "chatgpt_web_backend_access_token_status IN "
            "('unknown', 'active', 'expired', 'refreshing', 'revoked', 'invalid', 'dead', 'error')"
        ),
        Index("idx_memberships_user_account_id", "user_account_id"),
        Index("idx_memberships_team_workspace_id", "team_workspace_id"),
        Index("idx_memberships_can_invite", "can_invite"),
        Index("idx_memberships_status", "membership_status"),
    )


class WorkspaceJoinBatchModel(Base):
    __tablename__ = "workspace_join_batches"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    batch_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    batch_status: Mapped[str] = mapped_column(Text, nullable=False)
    activation_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_job_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pushed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "batch_status IN "
            "('created', 'running', 'partial_success', 'success', 'failed', 'cancelled')"
        ),
        CheckConstraint(
            "activation_status IN "
            "('inactive', 'activating', 'active', 'superseded', 'retired')"
        ),
        CheckConstraint("total_count >= 0"),
        CheckConstraint("success_count >= 0"),
        CheckConstraint("failed_count >= 0"),
        CheckConstraint("pushed_count >= 0"),
        Index("idx_batches_team_workspace_id", "team_workspace_id"),
        Index("idx_batches_status", "batch_status", "activation_status"),
        Index(
            "uq_workspace_join_batches_one_active",
            "team_workspace_id",
            unique=True,
            postgresql_where=(activation_status == "active"),
        ),
    )


class WorkspaceJoinBatchItemModel(Base):
    __tablename__ = "workspace_join_batch_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspace_join_batches.id", ondelete="CASCADE"), nullable=False
    )
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("user_account_team_workspace_memberships.id", ondelete="SET NULL")
    )
    codex_credential_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("codex_oauth_credentials.id", ondelete="RESTRICT")
    )
    item_status: Mapped[str] = mapped_column(Text, nullable=False)
    batch_binding_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    join_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    push_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    plan_tag: Mapped[str] = mapped_column(Text, nullable=False, default="")
    plan_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_chatgpt_web_backend_access_token: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    generated_chatgpt_web_backend_id_token: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    generated_chatgpt_web_backend_token_expires_at: Mapped[datetime | None] = mapped_column(
        nullable=True
    )
    downstream_provider: Mapped[str] = mapped_column(Text, nullable=False, default="")
    downstream_external_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("batch_id", "user_account_id", "team_workspace_id"),
        CheckConstraint(
            "item_status IN ('pending', 'joined', 'token_generated', 'pushed', 'failed', 'skipped')"
        ),
        CheckConstraint("batch_binding_status IN ('active', 'released')"),
        Index("idx_batch_items_batch_id", "batch_id"),
        Index("idx_batch_items_user_account_id", "user_account_id"),
        Index("idx_batch_items_team_workspace_id", "team_workspace_id"),
        Index("idx_batch_items_membership_id", "membership_id"),
        Index("idx_batch_items_codex_credential_id", "codex_credential_id"),
        Index("idx_batch_items_status", "item_status", "push_status"),
        Index("idx_batch_items_plan_tag", "plan_tag"),
        Index(
            "uq_batch_items_one_active_credential",
            "codex_credential_id",
            unique=True,
            postgresql_where=(batch_binding_status == "active"),
        ),
    )


class CodexOAuthCredentialModel(Base):
    __tablename__ = "codex_oauth_credentials"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    codex_client_id: Mapped[str] = mapped_column(Text, nullable=False)
    credential_status: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_chatgpt_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    id_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    push_lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_heartbeat_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    last_heartbeat_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_heartbeat_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id", "team_workspace_id", "codex_client_id"),
        CheckConstraint(
            "credential_status IN ('active', 'expired', 'refreshing', 'invalid', 'error')"
        ),
        CheckConstraint(
            "push_lifecycle_status IN "
            "('none', 'pending_push', 'pushing', 'pushed', 'used', 'failed', 'blocked')"
        ),
        CheckConstraint("last_heartbeat_status IN ('unknown', 'ok', 'failed', 'skipped', 'error')"),
        Index("idx_codex_credentials_user_account_id", "user_account_id"),
        Index("idx_codex_credentials_team_workspace_id", "team_workspace_id"),
        Index("idx_codex_credentials_status", "credential_status"),
        Index("idx_codex_credentials_expires_at", "expires_at"),
        Index("idx_codex_credentials_token_chatgpt_account_id", "token_chatgpt_account_id"),
        Index("idx_codex_credentials_heartbeat_status", "last_heartbeat_status"),
    )


class DownstreamCodexPushRecordModel(Base):
    __tablename__ = "downstream_codex_push_records"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_item_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("workspace_join_batch_items.id", ondelete="CASCADE")
    )
    codex_credential_id: Mapped[str] = mapped_column(
        Text, ForeignKey("codex_oauth_credentials.id", ondelete="CASCADE"), nullable=False
    )
    downstream_channel_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("downstream_channels.id", ondelete="SET NULL")
    )
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("user_account_team_workspace_memberships.id", ondelete="SET NULL")
    )
    downstream_provider: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_external_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    push_status: Mapped[str] = mapped_column(Text, nullable=False)
    codex_client_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    codex_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    codex_email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    downstream_chatgpt_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_chatgpt_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    codex_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    request_endpoint: Mapped[str] = mapped_column(Text, nullable=False, default="")
    push_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    last_usage_check_at: Mapped[datetime | None] = mapped_column(nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("codex_credential_id"),
        CheckConstraint("downstream_provider IN ('cpa', 'sub2api')"),
        CheckConstraint("push_status IN ('pending', 'pushing', 'pushed', 'failed', 'skipped', 'used')"),
        CheckConstraint("push_attempt_count >= 0"),
        CheckConstraint("usage_status IN ('unknown', 'active', 'near_limit', 'used', 'check_failed')"),
        CheckConstraint("usage_percent >= 0 AND usage_percent <= 100"),
        Index("idx_downstream_push_batch_item_id", "batch_item_id"),
        Index("idx_downstream_push_codex_credential_id", "codex_credential_id"),
        Index("idx_downstream_push_channel_id", "downstream_channel_id"),
        Index("idx_downstream_push_user_account_id", "user_account_id"),
        Index("idx_downstream_push_team_workspace_id", "team_workspace_id"),
        Index("idx_downstream_push_membership_id", "membership_id"),
        Index("idx_downstream_push_status", "downstream_provider", "push_status"),
    )


class DownstreamChannelModel(Base):
    __tablename__ = "downstream_channels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    admin_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    update_existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    max_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_active_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    push_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pushed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("provider_type IN ('sub2api', 'cpa')"),
        CheckConstraint("timeout_s > 0"),
        CheckConstraint("max_push_count >= 0"),
        CheckConstraint("max_active_slots >= 0"),
        CheckConstraint("push_balance >= 0"),
        CheckConstraint("claimed_push_count >= 0"),
        CheckConstraint("pushed_count >= 0"),
        CheckConstraint("failed_push_count >= 0"),
        CheckConstraint("used_count >= 0"),
        Index("idx_downstream_channels_provider_type", "provider_type"),
        Index("idx_downstream_channels_enabled", "enabled"),
    )


class UserAccountCooldownModel(Base):
    __tablename__ = "user_account_cooldowns"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    cooldown_type: Mapped[str] = mapped_column(Text, nullable=False)
    cooldown_until: Mapped[datetime] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_push_record_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id", "team_workspace_id", "cooldown_type"),
        CheckConstraint("cooldown_type IN ('post_usage_remove')"),
        Index("idx_user_account_cooldowns_account_workspace", "user_account_id", "team_workspace_id"),
        Index("idx_user_account_cooldowns_until", "cooldown_until"),
    )


class WorkspaceOperationLockModel(Base):
    __tablename__ = "workspace_operation_locks"

    team_workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    lock_type: Mapped[str] = mapped_column(Text, primary_key=True)
    locked_by: Mapped[str] = mapped_column(Text, nullable=False)
    locked_until: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("lock_type IN ('codex_fill', 'workspace_mutation')"),
        Index("idx_workspace_operation_locks_until", "locked_until"),
    )


class ProxyInventoryModel(Base):
    __tablename__ = "proxy_inventory"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_proxy_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    connection_mode: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_host: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_port: Mapped[int] = mapped_column(Integer, nullable=False)
    proxy_scheme: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_username: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proxy_password: Mapped[str] = mapped_column(Text, nullable=False, default="")
    country_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    city_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    asn_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proxy_status: Mapped[str] = mapped_column(Text, nullable=False)
    provider_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_provider_verification_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "external_proxy_id"),
        CheckConstraint("provider = 'webshare'"),
        CheckConstraint("proxy_port > 0 AND proxy_port <= 65535"),
        CheckConstraint(
            "proxy_status IN "
            "('unknown', 'available', 'bound', 'invalid', 'cooldown', 'retired', 'error')"
        ),
        Index("idx_proxy_inventory_status", "proxy_status"),
    )


class UserAccountProxyBindingModel(Base):
    __tablename__ = "user_account_proxy_bindings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    proxy_id: Mapped[str] = mapped_column(
        Text, ForeignKey("proxy_inventory.id", ondelete="RESTRICT"), nullable=False
    )
    bind_status: Mapped[str] = mapped_column(Text, nullable=False)
    bind_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bound_by_job_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bound_at: Mapped[datetime] = mapped_column(nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id"),
        CheckConstraint("bind_status IN ('active', 'repairing', 'disabled', 'released', 'error')"),
        Index("idx_proxy_bindings_proxy_id", "proxy_id"),
        Index("idx_proxy_bindings_status", "bind_status"),
    )


class ExternalMailLeaseModel(Base):
    __tablename__ = "external_mail_leases"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_lease_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    lease_status: Mapped[str] = mapped_column(Text, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "external_lease_id"),
        CheckConstraint("provider = 'external_mail_api'"),
        CheckConstraint("lease_status IN ('allocated', 'used', 'released', 'expired', 'failed')"),
        Index("idx_mail_leases_user_account_id", "user_account_id"),
        Index("idx_mail_leases_email", "email"),
        Index("idx_mail_leases_status", "lease_status"),
    )


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    job_status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("job_status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')"),
        Index("idx_jobs_status_priority", "job_status", "priority", "created_at"),
        Index("idx_jobs_type", "type"),
    )


class AutomationScheduleModel(Base):
    __tablename__ = "automation_schedules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_job_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_run_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    locked_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("schedule_type"),
        CheckConstraint(
            "schedule_type IN ("
            "'automation.workspace_invite_sync', "
            "'automation.workspace_authorize', "
            "'automation.codex_heartbeat', "
            "'automation.downstream_push', "
            "'automation.downstream_usage_cleanup'"
            ")"
        ),
        CheckConstraint("schedule_status IN ('active', 'paused', 'error')"),
        CheckConstraint("interval_seconds >= 5"),
        Index("idx_automation_schedules_due", "enabled", "schedule_status", "next_run_at"),
        Index("idx_automation_schedules_type", "schedule_type"),
    )


class WorkItemModel(Base):
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    work_type: Mapped[str] = mapped_column(Text, nullable=False)
    work_status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claimed_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("work_status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')"),
        CheckConstraint("priority >= 0"),
        Index("idx_work_items_job_id", "job_id"),
        Index("idx_work_items_claim", "work_status", "priority", "created_at"),
        Index("idx_work_items_type_status", "work_type", "work_status"),
    )


class JobRunModel(Base):
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    run_status: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("run_status IN ('running', 'succeeded', 'failed', 'cancelled')"),
        CheckConstraint("attempt >= 1"),
        Index("idx_job_runs_job_id", "job_id"),
        Index("idx_job_runs_status", "run_status"),
    )


class JobStepModel(Base):
    __tablename__ = "job_steps"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    step_status: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        CheckConstraint(
            "step_status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'retrying')"
        ),
        CheckConstraint("attempt >= 1"),
        Index("idx_job_steps_run_id", "run_id"),
        Index("idx_job_steps_status", "step_status"),
    )


class JobEventModel(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("job_steps.id", ondelete="SET NULL")
    )
    ts: Mapped[datetime] = mapped_column(nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("level IN ('DEBUG', 'INFO', 'WARN', 'ERROR')"),
        Index("idx_job_events_run_id_ts", "run_id", "ts"),
        Index("idx_job_events_step_id", "step_id"),
        Index("idx_job_events_type", "event_type"),
    )
