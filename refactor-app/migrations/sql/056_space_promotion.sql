ALTER TABLE spaces
  ADD COLUMN IF NOT EXISTS has_promotion BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS promotion_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_spaces_promotion
  ON spaces (space_type, has_promotion);
