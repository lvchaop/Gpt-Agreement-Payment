UPDATE automation_schedules
SET config_json = jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(
          jsonb_set(
            COALESCE(config_json, '{}'::jsonb),
            '{space_limit}',
            '1'::jsonb,
            true
          ),
          '{invite_limit_per_space}',
          '350'::jsonb,
          true
        ),
        '{invite_concurrency}',
        '350'::jsonb,
        true
      ),
      '{membership_cap_per_space}',
      '1000'::jsonb,
      true
    ),
    '{barrier_timeout_s}',
    '30'::jsonb,
    true
  ),
  updated_at = NOW()
WHERE schedule_type = 'automation.space_membership_invite_sync';
