ALTER TABLE space_credentials
  ADD COLUMN IF NOT EXISTS auth_mode TEXT NOT NULL DEFAULT 'backend_access_token';

UPDATE space_credentials AS credential
SET auth_mode = 'codex_oauth'
FROM spaces AS space
WHERE credential.space_id = space.id
  AND (
    space.space_type = 'personal'
    OR credential.refresh_token <> ''
  );

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'space_credentials_auth_mode_check'
      AND conrelid = 'space_credentials'::regclass
  ) THEN
    ALTER TABLE space_credentials
      ADD CONSTRAINT space_credentials_auth_mode_check
      CHECK (auth_mode IN ('codex_oauth', 'backend_access_token'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_space_credentials_auth_mode
  ON space_credentials (auth_mode);
