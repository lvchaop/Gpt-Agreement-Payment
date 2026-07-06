ALTER TABLE user_accounts
  ADD COLUMN IF NOT EXISTS password TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS access_token TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS session_token TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS cookie_header TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS auth_cookie_header TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS device_id TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS csrf_token TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS session_status TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS last_session_refresh_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_login_error_code TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS last_login_error_message TEXT NOT NULL DEFAULT '';

ALTER TABLE user_accounts
  DROP CONSTRAINT IF EXISTS ck_user_accounts_session_status;

ALTER TABLE user_accounts
  ADD CONSTRAINT ck_user_accounts_session_status
  CHECK (session_status IN ('unknown', 'active', 'expired', 'invalid', 'refreshing', 'dead', 'error'));
