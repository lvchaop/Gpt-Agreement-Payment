ALTER TABLE spaces
  ADD COLUMN IF NOT EXISTS has_payment_method BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS payment_method_status TEXT NOT NULL DEFAULT 'missing',
  ADD COLUMN IF NOT EXISTS payment_method_attempt_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS payment_method_id TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS payment_method_last4 TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS payment_method_last_attempt_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS payment_method_last_error_code TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS payment_method_last_error_message TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'spaces_payment_method_status_check'
      AND conrelid = 'spaces'::regclass
  ) THEN
    ALTER TABLE spaces
      ADD CONSTRAINT spaces_payment_method_status_check
      CHECK (payment_method_status IN ('missing', 'binding', 'bound', 'failed'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'spaces_payment_method_attempt_count_check'
      AND conrelid = 'spaces'::regclass
  ) THEN
    ALTER TABLE spaces
      ADD CONSTRAINT spaces_payment_method_attempt_count_check
      CHECK (payment_method_attempt_count >= 0 AND payment_method_attempt_count <= 3);
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_spaces_payment_method
  ON spaces (space_type, payment_method_status);

CREATE TABLE IF NOT EXISTS payment_name_pool (
  id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  name_status TEXT NOT NULL DEFAULT 'active',
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT payment_name_pool_status_check
    CHECK (name_status IN ('active', 'disabled')),
  CONSTRAINT payment_name_pool_use_count_check CHECK (use_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_payment_name_pool_status
  ON payment_name_pool (name_status);

CREATE TABLE IF NOT EXISTS payment_address_pool (
  id TEXT PRIMARY KEY,
  address_key TEXT NOT NULL UNIQUE,
  line1 TEXT NOT NULL,
  line2 TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT '',
  postal_code TEXT NOT NULL,
  country TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  address_status TEXT NOT NULL DEFAULT 'active',
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT payment_address_pool_status_check
    CHECK (address_status IN ('active', 'disabled')),
  CONSTRAINT payment_address_pool_country_check
    CHECK (char_length(country) = 2),
  CONSTRAINT payment_address_pool_use_count_check CHECK (use_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_payment_address_pool_status
  ON payment_address_pool (address_status);

CREATE INDEX IF NOT EXISTS idx_payment_address_pool_country
  ON payment_address_pool (country);

CREATE TABLE IF NOT EXISTS payment_card_pool (
  id TEXT PRIMARY KEY,
  card_fingerprint TEXT NOT NULL UNIQUE,
  card_number TEXT NOT NULL,
  cvc TEXT NOT NULL,
  last4 TEXT NOT NULL,
  exp_month INTEGER NOT NULL,
  exp_year INTEGER NOT NULL,
  card_status TEXT NOT NULL DEFAULT 'available',
  reserved_by_space_id TEXT REFERENCES spaces(id) ON DELETE SET NULL,
  reserved_at TIMESTAMPTZ,
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  last_error_code TEXT NOT NULL DEFAULT '',
  last_error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT payment_card_pool_status_check
    CHECK (card_status IN ('available', 'in_use', 'used', 'failed', 'disabled')),
  CONSTRAINT payment_card_pool_number_check CHECK (card_number ~ '^[0-9]{12,19}$'),
  CONSTRAINT payment_card_pool_cvc_check CHECK (cvc ~ '^[0-9]{3,4}$'),
  CONSTRAINT payment_card_pool_last4_check CHECK (char_length(last4) = 4),
  CONSTRAINT payment_card_pool_exp_month_check CHECK (exp_month >= 1 AND exp_month <= 12),
  CONSTRAINT payment_card_pool_exp_year_check CHECK (exp_year >= 2000),
  CONSTRAINT payment_card_pool_use_count_check CHECK (use_count >= 0 AND use_count <= 1)
);

CREATE INDEX IF NOT EXISTS idx_payment_card_pool_status
  ON payment_card_pool (card_status);

CREATE INDEX IF NOT EXISTS idx_payment_card_pool_reserved_space
  ON payment_card_pool (reserved_by_space_id);

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
      'automation.space_auto_replenish',
      'automation.personal_payment_method_bind'
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
  'automation-schedule-personal-payment-method-bind',
  'automation.personal_payment_method_bind',
  'active',
  FALSE,
  60,
  '{"space_id":"","limit":10,"work_count":1}'::jsonb,
  NULL,
  'system:space-default',
  NOW(),
  NOW()
)
ON CONFLICT (schedule_type) DO NOTHING;
