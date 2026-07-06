CREATE TABLE IF NOT EXISTS spaces (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL DEFAULT 'openai_chatgpt' CHECK (provider = 'openai_chatgpt'),
  external_space_id TEXT NOT NULL,
  owner_user_account_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  space_type TEXT NOT NULL CHECK (space_type IN ('personal', 'business')),
  auth_mode TEXT NOT NULL CHECK (auth_mode IN ('codex_oauth', 'backend_access_token')),
  credential_type TEXT NOT NULL CHECK (
    credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')
  ),
  plan_type TEXT NOT NULL DEFAULT '',
  seat_limit INTEGER NOT NULL DEFAULT 0 CHECK (seat_limit >= 0),
  seats_in_use INTEGER NOT NULL DEFAULT 0 CHECK (seats_in_use >= 0),
  seats_entitled INTEGER NOT NULL DEFAULT 0 CHECK (seats_entitled >= 0),
  space_status TEXT NOT NULL CHECK (
    space_status IN ('unknown', 'active', 'disabled', 'expired', 'error')
  ),
  source_admin_session_id TEXT NOT NULL DEFAULT '',
  raw_space_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_subscription_sync_at TIMESTAMPTZ,
  last_probe_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(provider, external_space_id)
);

CREATE INDEX IF NOT EXISTS idx_spaces_type_status
  ON spaces(space_type, space_status);

CREATE INDEX IF NOT EXISTS idx_spaces_credential_type
  ON spaces(credential_type);

CREATE INDEX IF NOT EXISTS idx_spaces_owner_user_account_id
  ON spaces(owner_user_account_id);

CREATE TABLE IF NOT EXISTS space_memberships (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT '',
  membership_status TEXT NOT NULL CHECK (
    membership_status IN ('unknown', 'invited', 'accepted', 'active', 'left', 'disabled', 'banned', 'failed')
  ),
  invite_permission TEXT NOT NULL DEFAULT 'unknown' CHECK (
    invite_permission IN ('unknown', 'ok', 'no_permission', 'error')
  ),
  user_count INTEGER NOT NULL DEFAULT 0 CHECK (user_count >= 0),
  invite_count INTEGER NOT NULL DEFAULT 0 CHECK (invite_count >= 0),
  seat_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
    seat_status IN ('unknown', 'available', 'full', 'error')
  ),
  can_invite BOOLEAN NOT NULL DEFAULT FALSE,
  remote_user_id TEXT NOT NULL DEFAULT '',
  remote_account_user_id TEXT NOT NULL DEFAULT '',
  remote_seat_type TEXT NOT NULL DEFAULT '',
  remote_role TEXT NOT NULL DEFAULT '',
  remote_synced_at TIMESTAMPTZ,
  last_probe_status TEXT NOT NULL DEFAULT '',
  last_probe_at TIMESTAMPTZ,
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(space_id, user_account_id)
);

CREATE INDEX IF NOT EXISTS idx_space_memberships_space_id
  ON space_memberships(space_id);

CREATE INDEX IF NOT EXISTS idx_space_memberships_user_account_id
  ON space_memberships(user_account_id);

CREATE INDEX IF NOT EXISTS idx_space_memberships_status
  ON space_memberships(membership_status);

CREATE INDEX IF NOT EXISTS idx_space_memberships_remote_user_id
  ON space_memberships(remote_user_id);

CREATE TABLE IF NOT EXISTS space_credentials (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  space_membership_id TEXT REFERENCES space_memberships(id) ON DELETE SET NULL,
  external_credential_id TEXT NOT NULL DEFAULT '',
  credential_status TEXT NOT NULL DEFAULT 'missing' CHECK (
    credential_status IN ('missing', 'active', 'expired', 'invalid', 'revoked', 'error')
  ),
  access_token TEXT NOT NULL DEFAULT '',
  id_token TEXT NOT NULL DEFAULT '',
  refresh_token TEXT NOT NULL DEFAULT '',
  codex_client_id TEXT NOT NULL DEFAULT '',
  account_id TEXT NOT NULL DEFAULT '',
  token_chatgpt_account_id TEXT NOT NULL DEFAULT '',
  expires_at TIMESTAMPTZ,
  last_authorized_at TIMESTAMPTZ,
  last_probe_at TIMESTAMPTZ,
  last_probe_status TEXT NOT NULL DEFAULT '',
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  raw_credential_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(space_id, user_account_id)
);

CREATE INDEX IF NOT EXISTS idx_space_credentials_space_id
  ON space_credentials(space_id);

CREATE INDEX IF NOT EXISTS idx_space_credentials_user_account_id
  ON space_credentials(user_account_id);

CREATE INDEX IF NOT EXISTS idx_space_credentials_status
  ON space_credentials(credential_status);

CREATE INDEX IF NOT EXISTS idx_space_credentials_external_credential_id
  ON space_credentials(external_credential_id);

CREATE TABLE IF NOT EXISTS downstream_channel_credential_type_balances (
  downstream_channel_id TEXT NOT NULL REFERENCES downstream_channels(id) ON DELETE CASCADE,
  credential_type TEXT NOT NULL CHECK (
    credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')
  ),
  max_active_slots INTEGER NOT NULL DEFAULT 0 CHECK (max_active_slots >= 0),
  push_balance INTEGER NOT NULL DEFAULT 0 CHECK (push_balance >= 0),
  claimed_push_count INTEGER NOT NULL DEFAULT 0 CHECK (claimed_push_count >= 0),
  pushed_count INTEGER NOT NULL DEFAULT 0 CHECK (pushed_count >= 0),
  failed_push_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_push_count >= 0),
  used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
  balance_status TEXT NOT NULL DEFAULT 'active' CHECK (balance_status IN ('active', 'disabled')),
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(downstream_channel_id, credential_type)
);

CREATE INDEX IF NOT EXISTS idx_downstream_type_balances_credential_type
  ON downstream_channel_credential_type_balances(credential_type);

CREATE INDEX IF NOT EXISTS idx_downstream_type_balances_status
  ON downstream_channel_credential_type_balances(balance_status);

CREATE TABLE IF NOT EXISTS space_push_bindings (
  space_credential_id TEXT PRIMARY KEY REFERENCES space_credentials(id) ON DELETE CASCADE,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  downstream_channel_id TEXT REFERENCES downstream_channels(id) ON DELETE SET NULL,
  push_status TEXT NOT NULL DEFAULT 'none' CHECK (
    push_status IN ('none', 'pending', 'pushing', 'pushed', 'failed', 'skipped', 'used')
  ),
  downstream_external_id TEXT NOT NULL DEFAULT '',
  pushed_count INTEGER NOT NULL DEFAULT 0 CHECK (pushed_count >= 0),
  failed_push_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_push_count >= 0),
  used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
  recycle_status TEXT NOT NULL DEFAULT 'none' CHECK (
    recycle_status IN ('none', 'pending', 'running', 'done', 'failed', 'blocked')
  ),
  recycled_at TIMESTAMPTZ,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_space_push_bindings_space_id
  ON space_push_bindings(space_id);

CREATE INDEX IF NOT EXISTS idx_space_push_bindings_downstream_channel_id
  ON space_push_bindings(downstream_channel_id);

CREATE INDEX IF NOT EXISTS idx_space_push_bindings_status
  ON space_push_bindings(push_status, recycle_status);

CREATE TABLE IF NOT EXISTS space_push_attempts (
  id TEXT PRIMARY KEY,
  space_credential_id TEXT NOT NULL REFERENCES space_credentials(id) ON DELETE CASCADE,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  downstream_channel_id TEXT REFERENCES downstream_channels(id) ON DELETE SET NULL,
  payload_type TEXT NOT NULL CHECK (
    payload_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')
  ),
  request_endpoint TEXT NOT NULL DEFAULT '',
  request_body_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  attempt_status TEXT NOT NULL CHECK (
    attempt_status IN ('running', 'pushed', 'failed', 'skipped')
  ),
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_space_push_attempts_credential_id
  ON space_push_attempts(space_credential_id);

CREATE INDEX IF NOT EXISTS idx_space_push_attempts_space_id
  ON space_push_attempts(space_id);

CREATE INDEX IF NOT EXISTS idx_space_push_attempts_channel_id
  ON space_push_attempts(downstream_channel_id);

CREATE INDEX IF NOT EXISTS idx_space_push_attempts_status
  ON space_push_attempts(attempt_status);

CREATE TABLE IF NOT EXISTS space_credential_usage_states (
  space_credential_id TEXT NOT NULL REFERENCES space_credentials(id) ON DELETE CASCADE,
  quota_window_kind TEXT NOT NULL CHECK (
    quota_window_kind IN ('five_hour', 'weekly', 'monthly')
  ),
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  usage_percent INTEGER NOT NULL DEFAULT 0 CHECK (usage_percent >= 0 AND usage_percent <= 100),
  usage_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
    usage_status IN ('unknown', 'active', 'near_limit', 'used', 'check_failed')
  ),
  limit_window_seconds INTEGER NOT NULL DEFAULT 0 CHECK (limit_window_seconds >= 0),
  reset_after_seconds INTEGER NOT NULL DEFAULT 0 CHECK (reset_after_seconds >= 0),
  reset_at TIMESTAMPTZ,
  last_checked_at TIMESTAMPTZ,
  raw_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(space_credential_id, quota_window_kind)
);

CREATE INDEX IF NOT EXISTS idx_space_usage_states_space_id
  ON space_credential_usage_states(space_id);

CREATE INDEX IF NOT EXISTS idx_space_usage_states_status
  ON space_credential_usage_states(usage_status);

CREATE TABLE IF NOT EXISTS space_usage_checks (
  id TEXT PRIMARY KEY,
  space_credential_id TEXT NOT NULL REFERENCES space_credentials(id) ON DELETE CASCADE,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  quota_window_kind TEXT NOT NULL CHECK (
    quota_window_kind IN ('five_hour', 'weekly', 'monthly')
  ),
  usage_percent INTEGER NOT NULL DEFAULT 0 CHECK (usage_percent >= 0 AND usage_percent <= 100),
  limit_window_seconds INTEGER NOT NULL DEFAULT 0 CHECK (limit_window_seconds >= 0),
  reset_after_seconds INTEGER NOT NULL DEFAULT 0 CHECK (reset_after_seconds >= 0),
  reset_at TIMESTAMPTZ,
  allowed BOOLEAN NOT NULL DEFAULT TRUE,
  limit_reached BOOLEAN NOT NULL DEFAULT FALSE,
  raw_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  check_status TEXT NOT NULL CHECK (check_status IN ('ok', 'failed')),
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  checked_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_space_usage_checks_credential_id
  ON space_usage_checks(space_credential_id);

CREATE INDEX IF NOT EXISTS idx_space_usage_checks_space_id
  ON space_usage_checks(space_id);

CREATE INDEX IF NOT EXISTS idx_space_usage_checks_checked_at
  ON space_usage_checks(checked_at);

CREATE TABLE IF NOT EXISTS space_recycle_rules (
  id TEXT PRIMARY KEY,
  credential_type TEXT NOT NULL CHECK (
    credential_type IN ('personal_account', 'team_5h_weekly', 'team_monthly')
  ),
  quota_window_kind TEXT NOT NULL CHECK (
    quota_window_kind IN ('five_hour', 'weekly', 'monthly')
  ),
  threshold_percent INTEGER NOT NULL DEFAULT 95 CHECK (
    threshold_percent >= 1 AND threshold_percent <= 100
  ),
  action TEXT NOT NULL CHECK (
    action IN ('mark_used', 'disable_push_only')
  ),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(credential_type, quota_window_kind)
);

CREATE INDEX IF NOT EXISTS idx_space_recycle_rules_enabled
  ON space_recycle_rules(enabled);

INSERT INTO space_recycle_rules (
  id, credential_type, quota_window_kind, threshold_percent, action, enabled, created_at, updated_at
)
VALUES
  ('space-recycle-rule-personal-monthly', 'personal_account', 'monthly', 95, 'mark_used', TRUE, NOW(), NOW()),
  ('space-recycle-rule-team-5h', 'team_5h_weekly', 'five_hour', 95, 'mark_used', FALSE, NOW(), NOW()),
  ('space-recycle-rule-team-weekly', 'team_5h_weekly', 'weekly', 95, 'mark_used', TRUE, NOW(), NOW()),
  ('space-recycle-rule-team-monthly', 'team_monthly', 'monthly', 95, 'mark_used', TRUE, NOW(), NOW())
ON CONFLICT (credential_type, quota_window_kind) DO NOTHING;

CREATE TABLE IF NOT EXISTS space_account_cooldowns (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  cooldown_type TEXT NOT NULL CHECK (cooldown_type IN ('post_usage_remove')),
  cooldown_until TIMESTAMPTZ NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  source_space_push_binding_id TEXT NOT NULL DEFAULT '',
  source_space_usage_check_id TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id, space_id, cooldown_type)
);

CREATE INDEX IF NOT EXISTS idx_space_account_cooldowns_account_space
  ON space_account_cooldowns(user_account_id, space_id);

CREATE INDEX IF NOT EXISTS idx_space_account_cooldowns_until
  ON space_account_cooldowns(cooldown_until);
