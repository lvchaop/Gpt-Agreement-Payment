ALTER TABLE space_memberships
  ADD COLUMN IF NOT EXISTS session_account_detected BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_space_memberships_session_account_detected
  ON space_memberships(session_account_detected);
