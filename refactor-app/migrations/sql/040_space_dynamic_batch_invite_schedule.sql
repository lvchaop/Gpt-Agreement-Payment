ALTER TABLE automation_schedules
  DROP CONSTRAINT IF EXISTS automation_schedules_schedule_type_check;

ALTER TABLE automation_schedules
  ADD CONSTRAINT automation_schedules_schedule_type_check
  CHECK (
    schedule_type IN (
      'automation.space_membership_invite_sync',
      'automation.space_membership_invite_dynamic',
      'automation.space_authorize',
      'automation.space_downstream_push',
      'automation.space_recycle_sweep',
      'automation.space_seat_expand'
    )
  );

INSERT INTO automation_schedules (
  id,
  schedule_type,
  schedule_status,
  enabled,
  interval_seconds,
  config_json,
  next_run_at,
  created_by,
  created_at,
  updated_at
)
VALUES (
  'automation-schedule-space-membership-invite-dynamic',
  'automation.space_membership_invite_dynamic',
  'active',
  FALSE,
  60,
  '{"space_id":""}'::jsonb,
  NULL,
  'system:space-default',
  NOW(),
  NOW()
)
ON CONFLICT (schedule_type) DO NOTHING;
