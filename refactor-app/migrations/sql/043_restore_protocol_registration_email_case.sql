WITH registration_claims AS (
  SELECT DISTINCT ON (work_items.output_json->>'user_account_id')
    work_items.output_json->>'user_account_id' AS user_account_id,
    work_items.output_json#>>'{mail_claim,email}' AS claimed_email
  FROM work_items
  JOIN jobs ON jobs.id = work_items.job_id
  WHERE jobs.type = 'account.protocol_register'
    AND work_items.work_status = 'succeeded'
    AND COALESCE(work_items.output_json->>'user_account_id', '') <> ''
    AND COALESCE(work_items.output_json#>>'{mail_claim,email}', '') <> ''
  ORDER BY work_items.output_json->>'user_account_id', work_items.updated_at DESC
)
UPDATE user_accounts
SET email = registration_claims.claimed_email,
    updated_at = NOW()
FROM registration_claims
WHERE user_accounts.id = registration_claims.user_account_id
  AND LOWER(user_accounts.email) = LOWER(registration_claims.claimed_email)
  AND user_accounts.email IS DISTINCT FROM registration_claims.claimed_email;
