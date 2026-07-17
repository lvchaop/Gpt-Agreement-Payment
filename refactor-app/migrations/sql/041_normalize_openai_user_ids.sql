UPDATE user_accounts
SET openai_user_id = split_part(openai_user_id, '__', 1),
    updated_at = NOW()
WHERE position('__' IN openai_user_id) > 0;

UPDATE space_credentials
SET account_id = split_part(account_id, '__', 1),
    updated_at = NOW()
WHERE position('__' IN account_id) > 0;

UPDATE space_memberships
SET remote_user_id = split_part(remote_user_id, '__', 1),
    updated_at = NOW()
WHERE position('__' IN remote_user_id) > 0;
