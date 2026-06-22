CREATE TABLE IF NOT EXISTS workspace_automation_states (
  team_workspace_id TEXT PRIMARY KEY REFERENCES team_workspaces(id) ON DELETE CASCADE,
  automation_status TEXT NOT NULL DEFAULT 'active',
  invite_status TEXT NOT NULL DEFAULT 'not_sent',
  invite_job_id TEXT NOT NULL DEFAULT '',
  last_invite_finished_at TIMESTAMPTZ,
  last_sync_at TIMESTAMPTZ,
  last_authorization_at TIMESTAMPTZ,
  last_push_at TIMESTAMPTZ,
  last_usage_cleanup_at TIMESTAMPTZ,
  pause_reason TEXT NOT NULL DEFAULT '',
  last_error_code TEXT NOT NULL DEFAULT '',
  last_error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT workspace_automation_states_automation_status_check
    CHECK (automation_status IN ('active', 'paused', 'stopped', 'error')),
  CONSTRAINT workspace_automation_states_invite_status_check
    CHECK (invite_status IN ('not_sent', 'sent'))
);

CREATE INDEX IF NOT EXISTS idx_workspace_automation_states_status
  ON workspace_automation_states(automation_status, invite_status);

CREATE INDEX IF NOT EXISTS idx_workspace_automation_states_last_invite
  ON workspace_automation_states(last_invite_finished_at);

INSERT INTO workspace_automation_states (
  team_workspace_id,
  automation_status,
  invite_status,
  created_at,
  updated_at
)
SELECT
  id,
  'active',
  'not_sent',
  NOW(),
  NOW()
FROM team_workspaces
ON CONFLICT (team_workspace_id) DO NOTHING;
