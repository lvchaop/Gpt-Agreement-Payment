ALTER TABLE proxy_inventory
  ADD COLUMN IF NOT EXISTS proxy_type TEXT NOT NULL DEFAULT 'proxyserver';

UPDATE proxy_inventory
SET proxy_type = 'proxyserver'
WHERE proxy_type = '';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_proxy_inventory_proxy_type'
  ) THEN
    ALTER TABLE proxy_inventory
      ADD CONSTRAINT ck_proxy_inventory_proxy_type
      CHECK (proxy_type IN ('proxyserver', 'static_proxy'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_proxy_inventory_type_status
  ON proxy_inventory(proxy_type, proxy_status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_proxy_inventory_id_unique
  ON proxy_inventory(id);

CREATE TABLE IF NOT EXISTS team_admin_proxy_bindings (
  id TEXT PRIMARY KEY,
  team_admin_session_id TEXT NOT NULL,
  proxy_id TEXT NOT NULL,
  bind_status TEXT NOT NULL CHECK (
    bind_status IN ('active', 'repairing', 'disabled', 'released', 'error')
  ),
  bind_reason TEXT NOT NULL DEFAULT '',
  bound_at TIMESTAMPTZ NOT NULL,
  last_used_at TIMESTAMPTZ,
  last_error_code TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(team_admin_session_id)
);

CREATE INDEX IF NOT EXISTS idx_team_admin_proxy_bindings_proxy_id
  ON team_admin_proxy_bindings(proxy_id);

CREATE INDEX IF NOT EXISTS idx_team_admin_proxy_bindings_status
  ON team_admin_proxy_bindings(bind_status);
