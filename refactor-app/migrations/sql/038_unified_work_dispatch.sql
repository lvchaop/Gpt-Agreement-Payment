ALTER TABLE work_items
  ADD COLUMN IF NOT EXISTS execution_key TEXT NOT NULL DEFAULT '';

ALTER TABLE work_items
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

UPDATE work_items
SET execution_key = 'space:' || COALESCE(input_json->>'external_space_id', '')
WHERE work_type = 'space.business_access_token.create.account'
  AND COALESCE(input_json->>'external_space_id', '') <> ''
  AND execution_key = '';

CREATE INDEX IF NOT EXISTS idx_work_items_execution_claim
  ON work_items(job_id, work_status, execution_key, priority, created_at);
