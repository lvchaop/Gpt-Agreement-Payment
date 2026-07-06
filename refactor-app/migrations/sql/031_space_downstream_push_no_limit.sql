UPDATE automation_schedules
SET config_json = COALESCE(config_json, '{}'::jsonb) - 'limit',
    updated_at = NOW()
WHERE schedule_type = 'automation.space_downstream_push'
  AND COALESCE(config_json, '{}'::jsonb) ? 'limit';
