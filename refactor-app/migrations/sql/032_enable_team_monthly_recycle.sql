UPDATE space_recycle_rules
SET enabled = TRUE,
    threshold_percent = 95,
    action = 'mark_used',
    updated_at = NOW()
WHERE credential_type = 'team_monthly'
  AND quota_window_kind = 'monthly';
