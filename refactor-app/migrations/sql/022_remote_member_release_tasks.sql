CREATE TABLE IF NOT EXISTS remote_member_release_tasks (
  id TEXT PRIMARY KEY,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  user_account_id TEXT REFERENCES user_accounts(id) ON DELETE SET NULL,
  codex_credential_id TEXT NOT NULL DEFAULT '',
  downstream_push_record_id TEXT NOT NULL DEFAULT '',
  external_workspace_id TEXT NOT NULL,
  remote_user_id TEXT NOT NULL,
  release_reason TEXT NOT NULL DEFAULT '',
  release_status TEXT NOT NULL DEFAULT 'pending',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ,
  last_attempt_at TIMESTAMPTZ,
  confirmed_at TIMESTAMPTZ,
  last_error_code TEXT NOT NULL DEFAULT '',
  last_error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(team_workspace_id, remote_user_id),
  CHECK (release_status IN ('pending', 'running', 'retrying', 'confirmed', 'blocked')),
  CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_remote_release_due
  ON remote_member_release_tasks(release_status, next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_remote_release_workspace
  ON remote_member_release_tasks(team_workspace_id);

CREATE INDEX IF NOT EXISTS idx_remote_release_user_account
  ON remote_member_release_tasks(user_account_id);

CREATE INDEX IF NOT EXISTS idx_remote_release_push_record
  ON remote_member_release_tasks(downstream_push_record_id);

ALTER TABLE automation_schedules
  DROP CONSTRAINT IF EXISTS automation_schedules_schedule_type_check;

ALTER TABLE automation_schedules
  ADD CONSTRAINT automation_schedules_schedule_type_check
  CHECK (
    schedule_type IN (
      'automation.workspace_invite_sync',
      'automation.workspace_authorize',
      'automation.codex_heartbeat',
      'automation.downstream_push',
      'automation.downstream_usage_cleanup',
      'automation.remote_member_release'
    )
  );
