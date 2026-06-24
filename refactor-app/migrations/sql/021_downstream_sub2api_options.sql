ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS sub2api_concurrency INTEGER NOT NULL DEFAULT 0;

ALTER TABLE downstream_channels
  ADD COLUMN IF NOT EXISTS sub2api_group_ids TEXT NOT NULL DEFAULT '';

ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_sub2api_concurrency_check;

ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_sub2api_concurrency_check
  CHECK (sub2api_concurrency >= 0);
