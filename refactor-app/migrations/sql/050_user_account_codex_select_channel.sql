ALTER TABLE user_accounts
  ADD COLUMN IF NOT EXISTS codex_select_channel_required BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE user_accounts
  ADD COLUMN IF NOT EXISTS codex_select_channel_detected_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_user_accounts_codex_select_channel
  ON user_accounts (codex_select_channel_required);
