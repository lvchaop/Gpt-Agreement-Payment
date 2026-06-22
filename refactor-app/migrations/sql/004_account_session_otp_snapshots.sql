CREATE TABLE IF NOT EXISTS account_session_otp_snapshots (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  source_membership_id TEXT NOT NULL DEFAULT '',
  snapshot_status TEXT NOT NULL CHECK (
    snapshot_status IN ('otp_collected', 'otp_pending', 'otp_validated', 'otp_missing', 'failed')
  ),
  snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  otp_code_len INTEGER NOT NULL DEFAULT 0 CHECK (otp_code_len >= 0),
  last_error_code TEXT NOT NULL DEFAULT '',
  last_error_message TEXT NOT NULL DEFAULT '',
  prepared_at TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id)
);

CREATE INDEX IF NOT EXISTS idx_account_session_otp_snapshots_user_account_id
  ON account_session_otp_snapshots(user_account_id);
CREATE INDEX IF NOT EXISTS idx_account_session_otp_snapshots_status
  ON account_session_otp_snapshots(snapshot_status);
CREATE INDEX IF NOT EXISTS idx_account_session_otp_snapshots_source_membership_id
  ON account_session_otp_snapshots(source_membership_id);
