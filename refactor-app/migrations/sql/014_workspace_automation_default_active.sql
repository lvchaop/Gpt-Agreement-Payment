ALTER TABLE workspace_automation_states
  ALTER COLUMN automation_status SET DEFAULT 'active';

UPDATE workspace_automation_states
SET
  automation_status = 'active',
  updated_at = NOW()
WHERE automation_status = 'paused'
  AND invite_status = 'not_sent'
  AND COALESCE(pause_reason, '') = ''
  AND COALESCE(last_error_code, '') = ''
  AND COALESCE(last_error_message, '') = '';
