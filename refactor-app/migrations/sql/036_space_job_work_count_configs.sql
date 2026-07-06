UPDATE automation_schedules
SET config_json = jsonb_build_object(
  'space_limit', 1,
  'invite_limit_per_space', 350,
  'work_count', 350,
  'membership_cap_per_space', 1000,
  'page_size', 100,
  'barrier_timeout_s', 30
),
updated_at = now()
WHERE schedule_type = 'automation.space_membership_invite_sync';

UPDATE automation_schedules
SET config_json = jsonb_build_object('work_count', 5),
updated_at = now()
WHERE schedule_type = 'automation.space_authorize';

UPDATE automation_schedules
SET config_json = jsonb_build_object('work_count', 5),
updated_at = now()
WHERE schedule_type = 'automation.space_downstream_push';
