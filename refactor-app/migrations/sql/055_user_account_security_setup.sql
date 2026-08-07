ALTER TABLE user_accounts
  ADD COLUMN IF NOT EXISTS password_status TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS password_last_error_code TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS password_last_error_message TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS mfa_status TEXT NOT NULL DEFAULT 'not_configured',
  ADD COLUMN IF NOT EXISTS twofauth_account_id TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS mfa_last_error_code TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS mfa_last_error_message TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS security_setup_last_attempt_at TIMESTAMPTZ;

UPDATE user_accounts
SET password_status = 'configured'
WHERE password <> ''
  AND password_status = 'unknown';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'user_accounts_password_status_check'
      AND conrelid = 'user_accounts'::regclass
  ) THEN
    ALTER TABLE user_accounts
      ADD CONSTRAINT user_accounts_password_status_check
      CHECK (password_status IN ('unknown', 'configured', 'failed'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'user_accounts_mfa_status_check'
      AND conrelid = 'user_accounts'::regclass
  ) THEN
    ALTER TABLE user_accounts
      ADD CONSTRAINT user_accounts_mfa_status_check
      CHECK (mfa_status IN ('not_configured', 'configured', 'failed', 'unknown'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_user_accounts_password_status
  ON user_accounts (password_status);

CREATE INDEX IF NOT EXISTS idx_user_accounts_mfa_status
  ON user_accounts (mfa_status);

CREATE INDEX IF NOT EXISTS idx_user_accounts_twofauth_account_id
  ON user_accounts (twofauth_account_id)
  WHERE twofauth_account_id <> '';
