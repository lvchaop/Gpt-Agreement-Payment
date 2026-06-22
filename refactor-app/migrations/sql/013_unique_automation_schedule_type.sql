WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY schedule_type
      ORDER BY
        CASE
          WHEN id IN (
            'automation-schedule-workspace-invite-sync',
            'automation-schedule-workspace-authorize',
            'automation-schedule-downstream-push',
            'automation-schedule-downstream-usage-cleanup'
          ) THEN 0
          ELSE 1
        END,
        created_at ASC,
        id ASC
    ) AS rn
  FROM automation_schedules
)
DELETE FROM automation_schedules
WHERE id IN (
  SELECT id
  FROM ranked
  WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_schedules_schedule_type
  ON automation_schedules(schedule_type);
