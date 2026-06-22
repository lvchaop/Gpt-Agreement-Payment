ALTER TABLE team_workspaces
  ADD COLUMN IF NOT EXISTS seats_in_use INTEGER NOT NULL DEFAULT 0;
ALTER TABLE team_workspaces
  ADD COLUMN IF NOT EXISTS seats_entitled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE team_workspaces
  ADD COLUMN IF NOT EXISTS last_subscription_sync_at TIMESTAMPTZ;
ALTER TABLE team_workspaces
  DROP CONSTRAINT IF EXISTS team_workspaces_seats_in_use_check;
ALTER TABLE team_workspaces
  DROP CONSTRAINT IF EXISTS team_workspaces_seats_entitled_check;
ALTER TABLE team_workspaces
  ADD CONSTRAINT team_workspaces_seats_in_use_check CHECK (seats_in_use >= 0);
ALTER TABLE team_workspaces
  ADD CONSTRAINT team_workspaces_seats_entitled_check CHECK (seats_entitled >= 0);

ALTER TABLE codex_oauth_credentials
  ADD COLUMN IF NOT EXISTS push_lifecycle_status TEXT NOT NULL DEFAULT 'none';

ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS max_push_count INTEGER NOT NULL DEFAULT 2;
ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS claimed_push_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS pushed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS failed_push_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS used_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE downstream_codex_push_records
  ALTER COLUMN batch_item_id DROP NOT NULL;
ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS downstream_channel_id TEXT REFERENCES downstream_channels(id) ON DELETE SET NULL;
ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS usage_percent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS usage_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS last_usage_check_at TIMESTAMPTZ;
ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS used_at TIMESTAMPTZ;

ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_batch_item_id_downstream_provider_key;
ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_push_status_check;
ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_usage_status_check;
ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_usage_percent_check;
ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_push_status_check
  CHECK (push_status IN ('pending', 'pushing', 'pushed', 'failed', 'skipped', 'used'));
ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_usage_status_check
  CHECK (usage_status IN ('unknown', 'active', 'near_limit', 'used', 'check_failed'));
ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_usage_percent_check
  CHECK (usage_percent >= 0 AND usage_percent <= 100);

CREATE UNIQUE INDEX IF NOT EXISTS uq_downstream_push_one_credential
  ON downstream_codex_push_records(codex_credential_id);
CREATE INDEX IF NOT EXISTS idx_downstream_push_channel_id
  ON downstream_codex_push_records(downstream_channel_id);

ALTER TABLE codex_oauth_credentials
  DROP CONSTRAINT IF EXISTS codex_oauth_credentials_push_lifecycle_status_check;
ALTER TABLE codex_oauth_credentials
  ADD CONSTRAINT codex_oauth_credentials_push_lifecycle_status_check
  CHECK (push_lifecycle_status IN ('none', 'pending_push', 'pushing', 'pushed', 'used', 'failed', 'blocked'));

ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_max_push_count_check;
ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_claimed_push_count_check;
ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_pushed_count_check;
ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_failed_push_count_check;
ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_used_count_check;
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_max_push_count_check CHECK (max_push_count >= 0);
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_claimed_push_count_check CHECK (claimed_push_count >= 0);
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_pushed_count_check CHECK (pushed_count >= 0);
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_failed_push_count_check CHECK (failed_push_count >= 0);
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_used_count_check CHECK (used_count >= 0);

CREATE TABLE IF NOT EXISTS user_account_cooldowns (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  cooldown_type TEXT NOT NULL CHECK (cooldown_type IN ('post_usage_remove')),
  cooldown_until TIMESTAMPTZ NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  source_push_record_id TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id, team_workspace_id, cooldown_type)
);

CREATE INDEX IF NOT EXISTS idx_user_account_cooldowns_account_workspace
  ON user_account_cooldowns(user_account_id, team_workspace_id);
CREATE INDEX IF NOT EXISTS idx_user_account_cooldowns_until
  ON user_account_cooldowns(cooldown_until);

CREATE TABLE IF NOT EXISTS workspace_operation_locks (
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  lock_type TEXT NOT NULL CHECK (lock_type IN ('codex_fill', 'workspace_mutation')),
  locked_by TEXT NOT NULL,
  locked_until TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(team_workspace_id, lock_type)
);

CREATE INDEX IF NOT EXISTS idx_workspace_operation_locks_until
  ON workspace_operation_locks(locked_until);
