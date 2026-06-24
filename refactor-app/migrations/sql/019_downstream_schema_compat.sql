ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS last_test_status TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS last_test_at TIMESTAMPTZ;

ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS last_error_code TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS last_error_message TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_last_test_status_check;

ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_last_test_status_check
  CHECK (last_test_status IN ('unknown', 'ok', 'failed', 'error'));

ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS allocation_id TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS downstream_channel_name TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS provider_type TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMPTZ;

ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_retry_count_check;

ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_retry_count_check
  CHECK (retry_count >= 0);

CREATE INDEX IF NOT EXISTS idx_downstream_push_allocation_id
  ON downstream_codex_push_records(allocation_id);

ALTER TABLE downstream_credential_allocations
  ADD COLUMN IF NOT EXISTS batch_id TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_credential_allocations
  ADD COLUMN IF NOT EXISTS allocated_by TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_credential_allocations
  ADD COLUMN IF NOT EXISTS allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE downstream_credential_allocations
  ADD COLUMN IF NOT EXISTS released_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_downstream_allocations_batch_id
  ON downstream_credential_allocations(batch_id);

