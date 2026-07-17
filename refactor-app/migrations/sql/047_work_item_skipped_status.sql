ALTER TABLE work_items
  DROP CONSTRAINT IF EXISTS work_items_work_status_check;

ALTER TABLE work_items
  ADD CONSTRAINT work_items_work_status_check CHECK (
    work_status IN ('queued', 'running', 'succeeded', 'skipped', 'failed', 'cancelled')
  );
