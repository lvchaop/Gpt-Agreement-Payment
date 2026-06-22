ALTER TABLE downstream_codex_push_records
  ADD COLUMN IF NOT EXISTS push_attempt_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_push_attempt_count_check;
ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_push_attempt_count_check
  CHECK (push_attempt_count >= 0);
