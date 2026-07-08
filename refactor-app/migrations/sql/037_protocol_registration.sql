ALTER TABLE user_accounts
  DROP CONSTRAINT IF EXISTS user_accounts_account_status_check;

ALTER TABLE user_accounts
  DROP CONSTRAINT IF EXISTS ck_user_accounts_account_status;

ALTER TABLE user_accounts
  ADD CONSTRAINT ck_user_accounts_account_status
  CHECK (account_status IN ('active', 'invalid', 'registering'));
