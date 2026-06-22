ALTER TABLE user_account_team_workspace_memberships
  ADD COLUMN IF NOT EXISTS remote_user_id TEXT NOT NULL DEFAULT '';

ALTER TABLE user_account_team_workspace_memberships
  ADD COLUMN IF NOT EXISTS remote_account_user_id TEXT NOT NULL DEFAULT '';

ALTER TABLE user_account_team_workspace_memberships
  ADD COLUMN IF NOT EXISTS remote_seat_type TEXT NOT NULL DEFAULT '';

ALTER TABLE user_account_team_workspace_memberships
  ADD COLUMN IF NOT EXISTS remote_role TEXT NOT NULL DEFAULT '';

ALTER TABLE user_account_team_workspace_memberships
  ADD COLUMN IF NOT EXISTS remote_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_memberships_remote_user_id
  ON user_account_team_workspace_memberships(remote_user_id);

CREATE INDEX IF NOT EXISTS idx_memberships_remote_account_user_id
  ON user_account_team_workspace_memberships(remote_account_user_id);
