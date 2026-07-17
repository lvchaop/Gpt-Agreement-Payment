UPDATE automation_schedules
SET config_json = jsonb_set(
  jsonb_set(
    COALESCE(config_json, '{}'::jsonb),
    '{static_proxy_count}',
    '50'::jsonb,
    true
  ),
  '{invites_per_proxy}',
  '20'::jsonb,
  true
),
updated_at = NOW()
WHERE schedule_type = 'automation.space_membership_invite_sync';
