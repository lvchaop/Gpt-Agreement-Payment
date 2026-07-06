ALTER TABLE user_accounts
  ADD COLUMN IF NOT EXISTS access_token TEXT NOT NULL DEFAULT '';

DELETE FROM automation_schedules
WHERE schedule_type NOT IN (
  'automation.space_membership_invite_sync',
  'automation.space_authorize',
  'automation.space_downstream_push',
  'automation.space_recycle_sweep'
);

ALTER TABLE automation_schedules
  DROP CONSTRAINT IF EXISTS automation_schedules_schedule_type_check;

ALTER TABLE automation_schedules
  ADD CONSTRAINT automation_schedules_schedule_type_check
  CHECK (
    schedule_type IN (
      'automation.space_membership_invite_sync',
      'automation.space_authorize',
      'automation.space_downstream_push',
      'automation.space_recycle_sweep'
    )
  );
