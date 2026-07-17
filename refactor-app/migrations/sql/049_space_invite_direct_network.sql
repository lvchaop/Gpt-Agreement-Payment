UPDATE automation_schedules
SET config_json = COALESCE(config_json, '{}'::jsonb)
                  - 'static_proxy_count'
                  - 'invites_per_proxy',
    updated_at = NOW()
WHERE schedule_type = 'automation.space_membership_invite_sync';
