ALTER TABLE workspace_join_batches
  DROP CONSTRAINT IF EXISTS workspace_join_batches_batch_status_check;

ALTER TABLE workspace_join_batches
  ADD CONSTRAINT workspace_join_batches_batch_status_check
  CHECK (batch_status IN ('active', 'inactive'));

UPDATE workspace_join_batches
SET batch_status = 'active'
WHERE batch_status NOT IN ('active', 'inactive');
