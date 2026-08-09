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
    password: Mapped[str] = mapped_column(Text, nullable=False, default="")
    password_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    password_last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    password_last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mfa_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_configured")
    twofauth_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mfa_last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mfa_last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    security_setup_last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    session_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cookie_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_cookie_header: Mapped[str] = mapped_column(Text, nullable=False, default="")
    device_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    codex_select_channel_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    codex_select_channel_detected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    session_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    last_session_refresh_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_login_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("account_status IN ('active', 'invalid', 'registering')"),
        CheckConstraint("password_status IN ('unknown', 'configured', 'failed')"),
        CheckConstraint(
            "mfa_status IN ('not_configured', 'configured', 'failed', 'unknown')"
        ),
        CheckConstraint(
            "session_status IN "
            "('unknown', 'active', 'expired', 'invalid', 'refreshing', 'dead', 'error')"
        ),
        Index("idx_user_accounts_email", "email"),
        Index("idx_user_accounts_phone_number", "phone_number"),
        Index("idx_user_accounts_openai_user_id", "openai_user_id"),
        Index("idx_user_accounts_account_status", "account_status"),
        Index("idx_user_accounts_codex_select_channel", "codex_select_channel_required"),
        Index("idx_user_accounts_password_status", "password_status"),
        Index("idx_user_accounts_mfa_status", "mfa_status"),
        Index("idx_user_accounts_twofauth_account_id", "twofauth_account_id"),
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


class SpaceModel(Base):
    __tablename__ = "spaces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="openai_chatgpt")
    external_space_id: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    space_type: Mapped[str] = mapped_column(Text, nullable=False)
    auth_mode: Mapped[str] = mapped_column(Text, nullable=False)
    credential_type: Mapped[str] = mapped_column(Text, nullable=False)
    plan_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seat_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seats_in_use: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seats_entitled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_replenish_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_promotion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promotion_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_payment_method: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payment_method_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="missing"
    )
    payment_method_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    payment_method_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payment_method_last4: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payment_method_last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_method_cooldown_until: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_method_last_error_code: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    payment_method_last_error_message: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    space_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_admin_session_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_space_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_subscription_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_probe_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("provider = 'openai_chatgpt'"),
        CheckConstraint("space_type IN ('personal', 'business')"),
        CheckConstraint("auth_mode IN ('codex_oauth', 'backend_access_token')"),
        CheckConstraint(
            "credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')"
        ),
        CheckConstraint("seat_limit >= 0"),
        CheckConstraint("seats_in_use >= 0"),
        CheckConstraint("seats_entitled >= 0"),
        CheckConstraint(
            "payment_method_status IN ('missing', 'binding', 'bound', 'failed')"
        ),
        CheckConstraint(
            "payment_method_attempt_count >= 0 AND payment_method_attempt_count <= 3"
        ),
        CheckConstraint("space_status IN ('unknown', 'active', 'disabled', 'expired', 'error')"),
        UniqueConstraint("provider", "external_space_id"),
        Index("idx_spaces_type_status", "space_type", "space_status"),
        Index("idx_spaces_credential_type", "credential_type"),
        Index("idx_spaces_owner_user_account_id", "owner_user_account_id"),
        Index("idx_spaces_auto_replenish", "auto_replenish_enabled", "space_status", "space_type"),
        Index("idx_spaces_promotion", "space_type", "has_promotion"),
        Index("idx_spaces_payment_method", "space_type", "payment_method_status"),
    )


class PaymentNamePoolModel(Base):
    __tablename__ = "payment_name_pool"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("name_status IN ('active', 'disabled')"),
        CheckConstraint("use_count >= 0"),
        Index("idx_payment_name_pool_status", "name_status"),
    )


class PaymentAddressPoolModel(Base):
    __tablename__ = "payment_address_pool"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    address_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    line1: Mapped[str] = mapped_column(Text, nullable=False)
    line2: Mapped[str] = mapped_column(Text, nullable=False, default="")
    city: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="")
    postal_code: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    address_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("address_status IN ('active', 'disabled')"),
        CheckConstraint("char_length(country) = 2"),
        CheckConstraint("use_count >= 0"),
        Index("idx_payment_address_pool_status", "address_status"),
        Index("idx_payment_address_pool_country", "country"),
    )


class PaymentCardPoolModel(Base):
    __tablename__ = "payment_card_pool"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    card_fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    card_number: Mapped[str] = mapped_column(Text, nullable=False)
    cvc: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(Text, nullable=False)
    exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    card_status: Mapped[str] = mapped_column(Text, nullable=False, default="available")
    reserved_by_space_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="SET NULL"), nullable=True
    )
    reserved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "card_status IN ('available', 'in_use', 'used', 'failed', 'disabled')"
        ),
        CheckConstraint("card_number ~ '^[0-9]{12,19}$'"),
        CheckConstraint("cvc ~ '^[0-9]{3,4}$'"),
        CheckConstraint("char_length(last4) = 4"),
        CheckConstraint("exp_month >= 1 AND exp_month <= 12"),
        CheckConstraint("exp_year >= 2000"),
        CheckConstraint("use_count >= 0 AND use_count <= 1"),
        Index("idx_payment_card_pool_status", "card_status"),
        Index("idx_payment_card_pool_reserved_space", "reserved_by_space_id"),
    )


class SpaceCredentialModel(Base):
    __tablename__ = "space_credentials"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    space_membership_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("space_memberships.id", ondelete="SET NULL")
    )
    external_credential_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="backend_access_token"
    )
    credential_status: Mapped[str] = mapped_column(Text, nullable=False, default="missing")
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    id_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    codex_client_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_chatgpt_account_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_authorized_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_probe_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_probe_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_credential_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("space_id", "user_account_id"),
        CheckConstraint(
            "credential_status IN ('missing', 'active', 'expired', 'invalid', 'revoked', 'error')"
        ),
        CheckConstraint("auth_mode IN ('codex_oauth', 'backend_access_token')"),
        Index("idx_space_credentials_space_id", "space_id"),
        Index("idx_space_credentials_user_account_id", "user_account_id"),
        Index("idx_space_credentials_auth_mode", "auth_mode"),
        Index("idx_space_credentials_status", "credential_status"),
        Index("idx_space_credentials_external_credential_id", "external_credential_id"),
    )


class SpaceMembershipModel(Base):
    __tablename__ = "space_memberships"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
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
    session_account_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_probe_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_probe_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("space_id", "user_account_id"),
        CheckConstraint(
            "membership_status IN "
            "('unknown', 'invited', 'accepted', 'active', 'left', 'disabled', 'banned', 'failed')"
        ),
        CheckConstraint("invite_permission IN ('unknown', 'ok', 'no_permission', 'error')"),
        CheckConstraint("user_count >= 0"),
        CheckConstraint("invite_count >= 0"),
        CheckConstraint("seat_status IN ('unknown', 'available', 'full', 'error')"),
        Index("idx_space_memberships_space_id", "space_id"),
        Index("idx_space_memberships_user_account_id", "user_account_id"),
        Index("idx_space_memberships_status", "membership_status"),
        Index("idx_space_memberships_remote_user_id", "remote_user_id"),
    )


class SpaceReplenishEmailModel(Base):
    __tablename__ = "space_replenish_emails"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="local_inventory")
    space_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="SET NULL"), nullable=True
    )
    user_account_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True
    )
    invite_batch_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    invite_status: Mapped[str] = mapped_column(Text, nullable=False, default="available")
    process_status: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    space_credential_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    replaces_space_credential_id: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    invite_confirm_after: Mapped[datetime | None] = mapped_column(nullable=True)
    invite_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("source_type IN ('existing_account', 'local_inventory')"),
        CheckConstraint(
            "invite_status IN "
            "('available', 'reserved', 'confirm_pending', 'confirmed', 'failed')"
        ),
        CheckConstraint(
            "process_status IN "
            "('idle', 'provisioning', 'credential_created', "
            "'remove_pending', 'completed', 'failed')"
        ),
        CheckConstraint("retry_count >= 0"),
        Index("idx_space_replenish_emails_space", "space_id", "invite_status"),
        Index("idx_space_replenish_emails_process", "space_id", "process_status"),
        Index("idx_space_replenish_emails_user_account", "user_account_id"),
        Index("idx_space_replenish_emails_batch", "invite_batch_id"),
    )


class DownstreamChannelCredentialTypeBalanceModel(Base):
    __tablename__ = "downstream_channel_credential_type_balances"

    downstream_channel_id: Mapped[str] = mapped_column(
        Text, ForeignKey("downstream_channels.id", ondelete="CASCADE"), primary_key=True
    )
    credential_type: Mapped[str] = mapped_column(Text, primary_key=True)
    max_active_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    push_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pushed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balance_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')"
        ),
        CheckConstraint("max_active_slots >= 0"),
        CheckConstraint("push_balance >= 0"),
        CheckConstraint("claimed_push_count >= 0"),
        CheckConstraint("pushed_count >= 0"),
        CheckConstraint("failed_push_count >= 0"),
        CheckConstraint("used_count >= 0"),
        CheckConstraint("balance_status IN ('active', 'disabled')"),
        Index("idx_downstream_type_balances_credential_type", "credential_type"),
        Index("idx_downstream_type_balances_status", "balance_status"),
    )


class SpacePushBindingModel(Base):
    __tablename__ = "space_push_bindings"

    space_credential_id: Mapped[str] = mapped_column(Text, primary_key=True)
    space_id: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_channel_id: Mapped[str | None] = mapped_column(Text)
    push_status: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    downstream_external_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pushed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_push_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recycle_status: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    recycled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "push_status IN ('none', 'pending', 'pushing', 'pushed', 'failed', 'skipped', 'used')"
        ),
        CheckConstraint("pushed_count >= 0"),
        CheckConstraint("failed_push_count >= 0"),
        CheckConstraint("used_count >= 0"),
        CheckConstraint(
            "recycle_status IN ('none', 'pending', 'running', 'done', 'failed', 'blocked')"
        ),
        Index("idx_space_push_bindings_space_id", "space_id"),
        Index("idx_space_push_bindings_downstream_channel_id", "downstream_channel_id"),
        Index("idx_space_push_bindings_status", "push_status", "recycle_status"),
    )


class SpacePushAttemptModel(Base):
    __tablename__ = "space_push_attempts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    space_credential_id: Mapped[str] = mapped_column(Text, nullable=False)
    space_id: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_channel_id: Mapped[str | None] = mapped_column(Text)
    payload_type: Mapped[str] = mapped_column(Text, nullable=False)
    request_endpoint: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_body_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    attempt_status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("payload_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')"),
        CheckConstraint("attempt_status IN ('running', 'pushed', 'failed', 'skipped')"),
        Index("idx_space_push_attempts_credential_id", "space_credential_id"),
        Index("idx_space_push_attempts_space_id", "space_id"),
        Index("idx_space_push_attempts_channel_id", "downstream_channel_id"),
        Index("idx_space_push_attempts_status", "attempt_status"),
    )


class SpaceCredentialUsageStateModel(Base):
    __tablename__ = "space_credential_usage_states"

    space_credential_id: Mapped[str] = mapped_column(
        Text, ForeignKey("space_credentials.id", ondelete="CASCADE"), primary_key=True
    )
    quota_window_kind: Mapped[str] = mapped_column(Text, primary_key=True)
    space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    usage_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_status: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    limit_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    raw_usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("quota_window_kind IN ('five_hour', 'weekly', 'monthly')"),
        CheckConstraint(
            "usage_status IN ('unknown', 'active', 'near_limit', 'used', 'check_failed')"
        ),
        CheckConstraint("usage_percent >= 0 AND usage_percent <= 100"),
        CheckConstraint("limit_window_seconds >= 0"),
        CheckConstraint("reset_after_seconds >= 0"),
        Index("idx_space_usage_states_space_id", "space_id"),
        Index("idx_space_usage_states_status", "usage_status"),
    )


class SpaceUsageCheckModel(Base):
    __tablename__ = "space_usage_checks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    space_credential_id: Mapped[str] = mapped_column(
        Text, ForeignKey("space_credentials.id", ondelete="CASCADE"), nullable=False
    )
    space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    quota_window_kind: Mapped[str] = mapped_column(Text, nullable=False)
    usage_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_at: Mapped[datetime | None] = mapped_column(nullable=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    limit_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    check_status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("quota_window_kind IN ('five_hour', 'weekly', 'monthly')"),
        CheckConstraint("usage_percent >= 0 AND usage_percent <= 100"),
        CheckConstraint("limit_window_seconds >= 0"),
        CheckConstraint("reset_after_seconds >= 0"),
        CheckConstraint("check_status IN ('ok', 'failed')"),
        Index("idx_space_usage_checks_credential_id", "space_credential_id"),
        Index("idx_space_usage_checks_space_id", "space_id"),
        Index("idx_space_usage_checks_checked_at", "checked_at"),
    )


class SpaceRecycleRuleModel(Base):
    __tablename__ = "space_recycle_rules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    credential_type: Mapped[str] = mapped_column(Text, nullable=False)
    quota_window_kind: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=95)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("credential_type", "quota_window_kind"),
        CheckConstraint(
            "credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')"
        ),
        CheckConstraint("quota_window_kind IN ('five_hour', 'weekly', 'monthly')"),
        CheckConstraint("threshold_percent >= 1 AND threshold_percent <= 100"),
        CheckConstraint("action IN ('mark_used', 'disable_push_only')"),
        Index("idx_space_recycle_rules_enabled", "enabled"),
    )


class SpaceAccountCooldownModel(Base):
    __tablename__ = "space_account_cooldowns"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    cooldown_type: Mapped[str] = mapped_column(Text, nullable=False)
    cooldown_until: Mapped[datetime] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_space_push_binding_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_space_usage_check_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("user_account_id", "space_id", "cooldown_type"),
        CheckConstraint("cooldown_type IN ('post_usage_remove')"),
        Index("idx_space_account_cooldowns_account_space", "user_account_id", "space_id"),
        Index("idx_space_account_cooldowns_until", "cooldown_until"),
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


class DownstreamChannelModel(Base):
    __tablename__ = "downstream_channels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    admin_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_payload_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_auth_header_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_auth_header_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    update_existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    sub2api_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sub2api_group_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
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
        CheckConstraint("provider_type IN ('sub2api', 'cpa', 'local_sub2api', 'custom_http')"),
        CheckConstraint("custom_payload_type IN ('', 'sub2api', 'sub2api_admin_accounts', 'cpa')"),
        CheckConstraint("timeout_s > 0"),
        CheckConstraint("sub2api_concurrency >= 0"),
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


class ProxyInventoryModel(Base):
    __tablename__ = "proxy_inventory"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_type: Mapped[str] = mapped_column(Text, nullable=False, default="proxyserver")
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
        CheckConstraint("proxy_type IN ('proxyserver', 'static_proxy')"),
        CheckConstraint("proxy_port > 0 AND proxy_port <= 65535"),
        CheckConstraint(
            "proxy_status IN "
            "('unknown', 'available', 'bound', 'invalid', 'cooldown', 'retired', 'error')"
        ),
        Index("idx_proxy_inventory_status", "proxy_status"),
        Index("idx_proxy_inventory_type_status", "proxy_type", "proxy_status"),
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


class TeamAdminProxyBindingModel(Base):
    __tablename__ = "team_admin_proxy_bindings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    team_admin_session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("team_admin_sessions.id", ondelete="CASCADE"), nullable=False
    )
    proxy_id: Mapped[str] = mapped_column(
        Text, ForeignKey("proxy_inventory.id", ondelete="RESTRICT"), nullable=False
    )
    bind_status: Mapped[str] = mapped_column(Text, nullable=False)
    bind_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    bound_at: Mapped[datetime] = mapped_column(nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("team_admin_session_id"),
        CheckConstraint("bind_status IN ('active', 'repairing', 'disabled', 'released', 'error')"),
        Index("idx_team_admin_proxy_bindings_proxy_id", "proxy_id"),
        Index("idx_team_admin_proxy_bindings_status", "bind_status"),
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
            "'automation.space_membership_invite_sync', "
            "'automation.space_membership_invite_dynamic', "
            "'automation.space_membership_growth_round', "
            "'automation.space_authorize', "
            "'automation.space_downstream_push', "
            "'automation.space_recycle_sweep', "
            "'automation.space_seat_expand', "
            "'automation.space_auto_replenish', "
            "'automation.personal_payment_method_bind', "
            "'automation.personal_codex_credential_heartbeat'"
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
    execution_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claimed_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    claimed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "work_status IN ('queued', 'running', 'succeeded', 'skipped', 'failed', 'cancelled')"
        ),
        CheckConstraint("priority >= 0"),
        Index("idx_work_items_job_id", "job_id"),
        Index("idx_work_items_claim", "work_status", "priority", "created_at"),
        Index(
            "idx_work_items_execution_claim",
            "job_id",
            "work_status",
            "execution_key",
            "priority",
            "created_at",
        ),
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
