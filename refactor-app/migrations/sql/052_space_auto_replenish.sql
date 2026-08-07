ALTER TABLE spaces
  ADD COLUMN IF NOT EXISTS auto_replenish_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_spaces_auto_replenish
  ON spaces (auto_replenish_enabled, space_status, space_type);

CREATE TABLE IF NOT EXISTS space_replenish_emails (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  email_key TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL DEFAULT 'local_inventory',
  space_id TEXT REFERENCES spaces(id) ON DELETE SET NULL,
  user_account_id TEXT REFERENCES user_accounts(id) ON DELETE SET NULL,
  invite_batch_id TEXT NOT NULL DEFAULT '',
  invite_status TEXT NOT NULL DEFAULT 'available',
  process_status TEXT NOT NULL DEFAULT 'idle',
  space_credential_id TEXT NOT NULL DEFAULT '',
  replaces_space_credential_id TEXT NOT NULL DEFAULT '',
  invite_confirm_after TIMESTAMPTZ,
  invite_confirmed_at TIMESTAMPTZ,
  processing_started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  retry_count INTEGER NOT NULL DEFAULT 0,
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT space_replenish_emails_source_type_check
    CHECK (source_type IN ('existing_account', 'local_inventory')),
  CONSTRAINT space_replenish_emails_invite_status_check
    CHECK (invite_status IN ('available', 'reserved', 'confirm_pending', 'confirmed', 'failed')),
  CONSTRAINT space_replenish_emails_process_status_check
    CHECK (
      process_status IN (
        'idle', 'provisioning', 'credential_created', 'remove_pending', 'completed', 'failed'
      )
    ),
  CONSTRAINT space_replenish_emails_retry_count_check CHECK (retry_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_space_replenish_emails_space
  ON space_replenish_emails (space_id, invite_status);

CREATE INDEX IF NOT EXISTS idx_space_replenish_emails_process
  ON space_replenish_emails (space_id, process_status);

CREATE INDEX IF NOT EXISTS idx_space_replenish_emails_user_account
  ON space_replenish_emails (user_account_id);

CREATE INDEX IF NOT EXISTS idx_space_replenish_emails_batch
  ON space_replenish_emails (invite_batch_id);

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
      'automation.space_auto_replenish'
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
  'automation-schedule-space-auto-replenish',
  'automation.space_auto_replenish',
  'active',
  FALSE,
  120,
  '{"work_count":20}'::jsonb,
  NULL,
  'system:space-default',
  NOW(),
  NOW()
)
ON CONFLICT (schedule_type) DO NOTHING;
