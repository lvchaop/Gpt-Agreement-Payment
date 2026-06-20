BEGIN;

ALTER TABLE user_account_auth
  ADD COLUMN IF NOT EXISTS personal_chatgpt_account_id TEXT NOT NULL DEFAULT '';

ALTER TABLE user_account_auth
  ADD COLUMN IF NOT EXISTS personal_chatgpt_account_discovered_at TIMESTAMPTZ;

COMMIT;
