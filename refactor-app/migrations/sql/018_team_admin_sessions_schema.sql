CREATE TABLE IF NOT EXISTS team_admin_sessions (
  id TEXT PRIMARY KEY,
  admin_email TEXT NOT NULL DEFAULT '',
  session_source TEXT NOT NULL DEFAULT 'chatgpt_api_auth_session',
  raw_session_json JSONB NOT NULL,
  access_token TEXT NOT NULL DEFAULT '',
  session_token TEXT NOT NULL DEFAULT '',
  cookie_header TEXT NOT NULL DEFAULT '',
  expires_at TIMESTAMPTZ,
  imported_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_admin_sessions_email
  ON team_admin_sessions(admin_email);

CREATE INDEX IF NOT EXISTS idx_team_admin_sessions_imported_at
  ON team_admin_sessions(imported_at);

CREATE TABLE IF NOT EXISTS team_admin_account_checks (
  id TEXT PRIMARY KEY,
  team_admin_session_id TEXT NOT NULL REFERENCES team_admin_sessions(id) ON DELETE CASCADE,
  raw_check_json JSONB NOT NULL,
  checked_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_admin_account_checks_session_id
  ON team_admin_account_checks(team_admin_session_id);

CREATE INDEX IF NOT EXISTS idx_team_admin_account_checks_checked_at
  ON team_admin_account_checks(checked_at);

ALTER TABLE team_workspaces
  ADD COLUMN IF NOT EXISTS source_admin_session_id TEXT NOT NULL DEFAULT '';

ALTER TABLE team_workspaces
  ADD COLUMN IF NOT EXISTS raw_workspace_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_team_workspaces_source_admin_session_id
  ON team_workspaces(source_admin_session_id);
