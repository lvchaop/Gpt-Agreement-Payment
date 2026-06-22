DO $$
DECLARE
  had_max_active_slots BOOLEAN;
  had_push_balance BOOLEAN;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'downstream_channels'
      AND column_name = 'max_active_slots'
  ) INTO had_max_active_slots;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'downstream_channels'
      AND column_name = 'push_balance'
  ) INTO had_push_balance;

  ALTER TABLE downstream_channels
    ADD COLUMN IF NOT EXISTS max_active_slots INTEGER NOT NULL DEFAULT 2;
  ALTER TABLE downstream_channels
    ADD COLUMN IF NOT EXISTS push_balance INTEGER NOT NULL DEFAULT 0;

  IF NOT had_max_active_slots THEN
    UPDATE downstream_channels
    SET max_active_slots = max_push_count;
  END IF;

  IF NOT had_push_balance THEN
    UPDATE downstream_channels
    SET push_balance = GREATEST(0, max_push_count - claimed_push_count);
  END IF;
END $$;

ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_max_active_slots_check;
ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_push_balance_check;
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_max_active_slots_check CHECK (max_active_slots >= 0);
ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_push_balance_check CHECK (push_balance >= 0);
