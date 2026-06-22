CREATE TABLE IF NOT EXISTS automation_schedules (
  id TEXT PRIMARY KEY,
  schedule_type TEXT NOT NULL,
  schedule_status TEXT NOT NULL DEFAULT 'active',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  interval_seconds INTEGER NOT NULL,
  config_json JSONB NOT NULL DEFAULT '{}',
  last_run_at TIMESTAMPTZ,
  next_run_at TIMESTAMPTZ,
  last_job_id TEXT NOT NULL DEFAULT '',
  last_run_status TEXT NOT NULL DEFAULT '',
  locked_by TEXT NOT NULL DEFAULT '',
  locked_until TIMESTAMPTZ,
  last_error_code TEXT NOT NULL DEFAULT '',
  last_error_message TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT automation_schedules_type_check CHECK (
    schedule_type IN (
      'automation.workspace_invite_sync',
      'automation.workspace_authorize',
      'automation.downstream_push',
      'automation.downstream_usage_cleanup'
    )
  ),
  CONSTRAINT automation_schedules_status_check CHECK (
    schedule_status IN ('active', 'paused', 'error')
  ),
  CONSTRAINT automation_schedules_interval_check CHECK (interval_seconds >= 5)
);

CREATE INDEX IF NOT EXISTS idx_automation_schedules_due
  ON automation_schedules(enabled, schedule_status, next_run_at);

CREATE INDEX IF NOT EXISTS idx_automation_schedules_type
  ON automation_schedules(schedule_type);

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
VALUES
  (
    'automation-schedule-workspace-invite-sync',
    'automation.workspace_invite_sync',
    'paused',
    false,
    60,
    '{"workspace_limit":20,"workspace_concurrency":4,"invite_count":350,"invite_concurrency":350,"sync_after_seconds":120,"sync_page_size":100}'::jsonb,
    NOW(),
    'migration',
    NOW(),
    NOW()
  ),
  (
    'automation-schedule-workspace-authorize',
    'automation.workspace_authorize',
    'paused',
    false,
    60,
    '{"workspace_limit":20,"workspace_concurrency":4,"codex_client_id":"app_EMoamEEZ73f0CkXaXp7hrann","sync_page_size":100,"lock_ttl_seconds":1800}'::jsonb,
    NOW(),
    'migration',
    NOW(),
    NOW()
  ),
  (
    'automation-schedule-downstream-push',
    'automation.downstream_push',
    'paused',
    false,
    60,
    '{"channel_limit":20,"channel_concurrency":4,"push_concurrency":5,"per_channel_limit":50,"request_endpoint":""}'::jsonb,
    NOW(),
    'migration',
    NOW(),
    NOW()
  ),
  (
    'automation-schedule-downstream-usage-cleanup',
    'automation.downstream_usage_cleanup',
    'paused',
    false,
    300,
    '{"record_limit":100,"record_concurrency":10,"threshold_percent":95}'::jsonb,
    NOW(),
    'migration',
    NOW(),
    NOW()
  )
ON CONFLICT (id) DO NOTHING;
