ALTER TABLE spaces
  ADD COLUMN IF NOT EXISTS payment_method_cooldown_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_spaces_payment_method_cooldown
  ON spaces (payment_method_cooldown_until);

UPDATE spaces
SET payment_method_cooldown_until =
  COALESCE(payment_method_last_attempt_at, NOW()) + INTERVAL '6 hours'
WHERE payment_method_attempt_count >= 3
  AND payment_method_status = 'failed'
  AND payment_method_cooldown_until IS NULL;
