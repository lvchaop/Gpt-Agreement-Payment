CREATE TABLE IF NOT EXISTS downstream_channels (
  id TEXT PRIMARY KEY,
  provider_type TEXT NOT NULL CHECK (provider_type IN ('sub2api', 'cpa')),
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  admin_key TEXT NOT NULL DEFAULT '',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  update_existing BOOLEAN NOT NULL DEFAULT FALSE,
  timeout_s INTEGER NOT NULL DEFAULT 30 CHECK (timeout_s > 0),
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_downstream_channels_provider_type
  ON downstream_channels(provider_type);
CREATE INDEX IF NOT EXISTS idx_downstream_channels_enabled
  ON downstream_channels(enabled);

CREATE TABLE IF NOT EXISTS downstream_credential_allocations (
  id TEXT PRIMARY KEY,
  batch_item_id TEXT NOT NULL REFERENCES workspace_join_batch_items(id) ON DELETE CASCADE,
  codex_credential_id TEXT NOT NULL REFERENCES codex_oauth_credentials(id) ON DELETE CASCADE,
  downstream_channel_id TEXT NOT NULL REFERENCES downstream_channels(id) ON DELETE RESTRICT,
  allocation_status TEXT NOT NULL CHECK (
    allocation_status IN ('allocated', 'pushing', 'pushed', 'failed', 'released')
  ),
  pushed_at TIMESTAMPTZ,
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(codex_credential_id)
);

CREATE INDEX IF NOT EXISTS idx_downstream_credential_allocations_batch_item_id
  ON downstream_credential_allocations(batch_item_id);
CREATE INDEX IF NOT EXISTS idx_downstream_credential_allocations_channel_id
  ON downstream_credential_allocations(downstream_channel_id);
CREATE INDEX IF NOT EXISTS idx_downstream_credential_allocations_status
  ON downstream_credential_allocations(allocation_status);
