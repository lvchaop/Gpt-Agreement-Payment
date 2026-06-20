BEGIN;

ALTER TABLE workspace_join_batch_items
  ADD COLUMN IF NOT EXISTS codex_credential_id TEXT REFERENCES codex_oauth_credentials(id) ON DELETE RESTRICT;

ALTER TABLE workspace_join_batch_items
  ADD COLUMN IF NOT EXISTS batch_binding_status TEXT NOT NULL DEFAULT 'active';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_batch_items_binding_status'
  ) THEN
    ALTER TABLE workspace_join_batch_items
      ADD CONSTRAINT ck_batch_items_binding_status
      CHECK (batch_binding_status IN ('active', 'released'));
  END IF;
END $$;

UPDATE workspace_join_batch_items item
SET codex_credential_id = credential.id
FROM codex_oauth_credentials credential
WHERE item.codex_credential_id IS NULL
  AND credential.user_account_id = item.user_account_id
  AND credential.team_workspace_id = item.team_workspace_id
  AND credential.credential_status = 'active';

CREATE INDEX IF NOT EXISTS idx_batch_items_codex_credential_id
  ON workspace_join_batch_items(codex_credential_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_items_one_active_credential
  ON workspace_join_batch_items(codex_credential_id)
  WHERE codex_credential_id IS NOT NULL
    AND batch_binding_status = 'active';

COMMIT;
