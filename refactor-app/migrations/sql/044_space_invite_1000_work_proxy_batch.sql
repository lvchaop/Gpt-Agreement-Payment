UPDATE automation_schedules
SET config_json = jsonb_build_object(
  'space_limit', 1,
  'invite_limit_per_space', 1000,
  'work_count', 1000,
  'static_proxy_count', 20,
  'invites_per_proxy', 50,
  'barrier_timeout_s', 30
),
updated_at = NOW()
WHERE schedule_type = 'automation.space_membership_invite_sync';
