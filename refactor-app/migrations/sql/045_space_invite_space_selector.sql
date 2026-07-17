UPDATE automation_schedules
SET config_json = jsonb_set(
  COALESCE(config_json, '{}'::jsonb),
  '{space_id}',
  '""'::jsonb,
  true
),
updated_at = NOW()
WHERE schedule_type = 'automation.space_membership_invite_sync';
