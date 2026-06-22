ALTER TABLE automation_schedules
  DROP CONSTRAINT IF EXISTS automation_schedules_type_check;

ALTER TABLE automation_schedules
  ADD CONSTRAINT automation_schedules_type_check
  CHECK (
    schedule_type IN (
      'automation.workspace_invite_sync',
      'automation.workspace_authorize',
      'automation.codex_heartbeat',
      'automation.downstream_push',
      'automation.downstream_usage_cleanup'
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
  'automation-schedule-codex-heartbeat',
  'automation.codex_heartbeat',
  'paused',
  false,
  60,
  $json${"credential_limit":100,"credential_concurrency":10}$json$::jsonb,
  NOW(),
  'migration',
  NOW(),
  NOW()
)
ON CONFLICT (id) DO NOTHING;
