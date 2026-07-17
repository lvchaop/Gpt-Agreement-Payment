UPDATE space_memberships
SET remote_user_id = split_part(remote_account_user_id, '__', 1),
    updated_at = NOW()
WHERE position('__' IN remote_account_user_id) > 0
  AND split_part(remote_account_user_id, '__', 1) LIKE 'user-%'
  AND remote_user_id IS DISTINCT FROM split_part(remote_account_user_id, '__', 1);
