ALTER TABLE automation_schedules
  DROP CONSTRAINT IF EXISTS automation_schedules_schedule_type_check;

ALTER TABLE automation_schedules
  ADD CONSTRAINT automation_schedules_schedule_type_check
  CHECK (
    schedule_type IN (
      'automation.space_membership_invite_sync',
      'automation.space_membership_invite_dynamic',
      'automation.space_membership_growth_round',
      'automation.space_authorize',
      'automation.space_downstream_push',
      'automation.space_recycle_sweep',
      'automation.space_seat_expand',
      'automation.space_auto_replenish',
      'automation.personal_payment_method_bind',
      'automation.personal_codex_credential_heartbeat'
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
  'automation-schedule-personal-codex-credential-heartbeat',
  'automation.personal_codex_credential_heartbeat',
  'active',
  FALSE,
  300,
  '{"space_id":"","limit":100,"work_count":10,"use_hero_sms_for_add_phone":true,"hero_sms_country":"187","hero_sms_max_price":"0.18","force_clean_browser_login":false}'::jsonb,
  NULL,
  'system:space-default',
  NOW(),
  NOW()
)
ON CONFLICT (schedule_type) DO NOTHING;
