-- Refactor target schema.
-- Database target: PostgreSQL 16+.
-- Source of truth for table definitions. Explanatory docs must align to this file.

BEGIN;

CREATE TABLE user_accounts (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  phone_number TEXT NOT NULL DEFAULT '',
  phone_dial_code TEXT NOT NULL DEFAULT '',
  phone_country TEXT NOT NULL DEFAULT '',
  openai_user_id TEXT NOT NULL DEFAULT '',
  account_status TEXT NOT NULL CHECK (
    account_status IN ('active', 'invalid', 'registering')
  ),
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE team_workspaces (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider = 'openai_chatgpt'),
  external_workspace_id TEXT NOT NULL,
  name TEXT NOT NULL,
  plan_type TEXT NOT NULL DEFAULT '',
  seat_limit INTEGER NOT NULL DEFAULT 0 CHECK (seat_limit >= 0),
  workspace_status TEXT NOT NULL CHECK (workspace_status IN ('unknown', 'active', 'disabled', 'expired', 'error')),
  last_probe_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(provider, external_workspace_id)
);

CREATE TABLE user_account_auth (
  user_account_id TEXT PRIMARY KEY REFERENCES user_accounts(id) ON DELETE CASCADE,
  password TEXT NOT NULL DEFAULT '',
  session_token TEXT NOT NULL DEFAULT '',
  refresh_token TEXT NOT NULL DEFAULT '',
  cookie_header TEXT NOT NULL DEFAULT '',
  device_id TEXT NOT NULL DEFAULT '',
  csrf_token TEXT NOT NULL DEFAULT '',
  token_type TEXT NOT NULL DEFAULT '',
  scope TEXT NOT NULL DEFAULT '',
  refresh_token_status TEXT NOT NULL CHECK (
    refresh_token_status IN ('missing', 'active', 'refreshing', 'expired', 'invalid', 'dead', 'error')
  ),
  session_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
    session_status IN ('unknown', 'active', 'expired', 'invalid', 'refreshing', 'dead', 'error')
  ),
  last_refresh_at TIMESTAMPTZ,
  last_session_refresh_at TIMESTAMPTZ,
  last_auth_error_code TEXT NOT NULL DEFAULT '',
  last_auth_error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE user_account_team_workspace_memberships (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT '',
  membership_status TEXT NOT NULL CHECK (
    membership_status IN ('unknown', 'invited', 'accepted', 'active', 'left', 'disabled', 'banned', 'failed')
  ),
  invite_permission TEXT NOT NULL DEFAULT 'unknown' CHECK (
    invite_permission IN ('unknown', 'ok', 'no_permission', 'error')
  ),
  user_count INTEGER NOT NULL DEFAULT 0 CHECK (user_count >= 0),
  invite_count INTEGER NOT NULL DEFAULT 0 CHECK (invite_count >= 0),
  seat_status TEXT NOT NULL DEFAULT 'unknown' CHECK (seat_status IN ('unknown', 'available', 'full', 'error')),
  can_invite BOOLEAN NOT NULL DEFAULT FALSE,
  chatgpt_web_backend_access_token TEXT NOT NULL DEFAULT '',
  chatgpt_web_backend_id_token TEXT NOT NULL DEFAULT '',
  chatgpt_web_backend_access_token_expires_at TIMESTAMPTZ,
  chatgpt_web_backend_access_token_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
    chatgpt_web_backend_access_token_status IN ('unknown', 'active', 'expired', 'refreshing', 'revoked', 'invalid', 'dead', 'error')
  ),
  last_chatgpt_web_backend_token_refresh_at TIMESTAMPTZ,
  last_probe_status TEXT NOT NULL DEFAULT '',
  last_probe_at TIMESTAMPTZ,
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id, team_workspace_id)
);

CREATE TABLE workspace_join_batches (
  id TEXT PRIMARY KEY,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  batch_name TEXT NOT NULL DEFAULT '',
  batch_status TEXT NOT NULL CHECK (
    batch_status IN ('created', 'running', 'partial_success', 'success', 'failed', 'cancelled')
  ),
  activation_status TEXT NOT NULL CHECK (
    activation_status IN ('inactive', 'activating', 'active', 'superseded', 'retired')
  ),
  source_type TEXT NOT NULL DEFAULT '',
  source_job_id TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  deactivated_at TIMESTAMPTZ,
  total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
  success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
  failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
  pushed_count INTEGER NOT NULL DEFAULT 0 CHECK (pushed_count >= 0),
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX uq_workspace_join_batches_one_active
  ON workspace_join_batches(team_workspace_id)
  WHERE activation_status = 'active';

CREATE TABLE workspace_join_batch_items (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES workspace_join_batches(id) ON DELETE CASCADE,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  membership_id TEXT REFERENCES user_account_team_workspace_memberships(id) ON DELETE SET NULL,
  item_status TEXT NOT NULL CHECK (
    item_status IN ('pending', 'joined', 'token_generated', 'pushed', 'failed', 'skipped')
  ),
  join_status TEXT NOT NULL DEFAULT '',
  token_status TEXT NOT NULL DEFAULT '',
  push_status TEXT NOT NULL DEFAULT '',
  plan_tag TEXT NOT NULL DEFAULT '',
  plan_type TEXT NOT NULL DEFAULT '',
  generated_chatgpt_web_backend_access_token TEXT NOT NULL DEFAULT '',
  generated_chatgpt_web_backend_id_token TEXT NOT NULL DEFAULT '',
  generated_chatgpt_web_backend_token_expires_at TIMESTAMPTZ,
  downstream_provider TEXT NOT NULL DEFAULT '',
  downstream_external_id TEXT NOT NULL DEFAULT '',
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(batch_id, user_account_id, team_workspace_id)
);

CREATE TABLE codex_oauth_credentials (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  codex_client_id TEXT NOT NULL,
  credential_status TEXT NOT NULL CHECK (
    credential_status IN ('active', 'expired', 'refreshing', 'invalid', 'error')
  ),
  account_id TEXT NOT NULL DEFAULT '',
  token_chatgpt_account_id TEXT NOT NULL DEFAULT '',
  access_token TEXT NOT NULL DEFAULT '',
  id_token TEXT NOT NULL DEFAULT '',
  refresh_token TEXT NOT NULL DEFAULT '',
  expires_at TIMESTAMPTZ,
  last_refresh_at TIMESTAMPTZ,
  last_heartbeat_at TIMESTAMPTZ,
  last_heartbeat_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
    last_heartbeat_status IN ('unknown', 'ok', 'failed', 'skipped', 'error')
  ),
  last_heartbeat_error_code TEXT NOT NULL DEFAULT '',
  last_heartbeat_error_message TEXT NOT NULL DEFAULT '',
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id, team_workspace_id, codex_client_id)
);

CREATE TABLE downstream_codex_push_records (
  id TEXT PRIMARY KEY,
  batch_item_id TEXT NOT NULL REFERENCES workspace_join_batch_items(id) ON DELETE CASCADE,
  codex_credential_id TEXT REFERENCES codex_oauth_credentials(id) ON DELETE SET NULL,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  team_workspace_id TEXT NOT NULL REFERENCES team_workspaces(id) ON DELETE CASCADE,
  membership_id TEXT REFERENCES user_account_team_workspace_memberships(id) ON DELETE SET NULL,
  downstream_provider TEXT NOT NULL CHECK (downstream_provider IN ('cpa', 'sub2api')),
  downstream_external_id TEXT NOT NULL DEFAULT '',
  push_status TEXT NOT NULL CHECK (push_status IN ('pending', 'pushed', 'failed', 'skipped')),
  codex_client_id TEXT NOT NULL DEFAULT '',
  codex_account_id TEXT NOT NULL DEFAULT '',
  codex_email TEXT NOT NULL DEFAULT '',
  downstream_chatgpt_account_id TEXT NOT NULL DEFAULT '',
  token_chatgpt_account_id TEXT NOT NULL DEFAULT '',
  codex_token_expires_at TIMESTAMPTZ,
  request_endpoint TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(batch_item_id, downstream_provider)
);

CREATE TABLE proxy_inventory (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider = 'webshare'),
  external_proxy_id TEXT NOT NULL DEFAULT '',
  connection_mode TEXT NOT NULL,
  proxy_host TEXT NOT NULL,
  proxy_port INTEGER NOT NULL CHECK (proxy_port > 0 AND proxy_port <= 65535),
  proxy_scheme TEXT NOT NULL,
  proxy_username TEXT NOT NULL DEFAULT '',
  proxy_password TEXT NOT NULL DEFAULT '',
  country_code TEXT NOT NULL DEFAULT '',
  city_name TEXT NOT NULL DEFAULT '',
  asn_name TEXT NOT NULL DEFAULT '',
  proxy_status TEXT NOT NULL CHECK (
    proxy_status IN ('unknown', 'available', 'bound', 'invalid', 'cooldown', 'retired', 'error')
  ),
  provider_valid BOOLEAN NOT NULL DEFAULT FALSE,
  last_provider_verification_at TIMESTAMPTZ,
  last_healthcheck_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(provider, external_proxy_id)
);

CREATE TABLE user_account_proxy_bindings (
  id TEXT PRIMARY KEY,
  user_account_id TEXT NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
  proxy_id TEXT NOT NULL REFERENCES proxy_inventory(id) ON DELETE RESTRICT,
  bind_status TEXT NOT NULL CHECK (bind_status IN ('active', 'repairing', 'disabled', 'released', 'error')),
  bind_reason TEXT NOT NULL DEFAULT '',
  bound_by_job_id TEXT NOT NULL DEFAULT '',
  bound_at TIMESTAMPTZ NOT NULL,
  last_used_at TIMESTAMPTZ,
  last_error_code TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(user_account_id)
);

CREATE TABLE external_mail_leases (
  id TEXT PRIMARY KEY,
  user_account_id TEXT REFERENCES user_accounts(id) ON DELETE SET NULL,
  provider TEXT NOT NULL CHECK (provider = 'external_mail_api'),
  external_lease_id TEXT NOT NULL,
  email TEXT NOT NULL,
  lease_status TEXT NOT NULL CHECK (
    lease_status IN ('allocated', 'used', 'released', 'expired', 'failed')
  ),
  allocated_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,
  failure_code TEXT NOT NULL DEFAULT '',
  failure_message TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(provider, external_lease_id)
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  job_status TEXT NOT NULL CHECK (job_status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  priority INTEGER NOT NULL DEFAULT 0,
  input_json JSONB NOT NULL,
  created_by TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE work_items (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  work_type TEXT NOT NULL,
  work_status TEXT NOT NULL CHECK (work_status IN ('queued', 'running', 'succeeded', 'skipped', 'failed', 'cancelled')),
  priority INTEGER NOT NULL DEFAULT 0 CHECK (priority >= 0),
  execution_key TEXT NOT NULL DEFAULT '',
  input_json JSONB NOT NULL,
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  claimed_by TEXT NOT NULL DEFAULT '',
  claimed_at TIMESTAMPTZ,
  lease_expires_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE job_runs (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  run_status TEXT NOT NULL CHECK (run_status IN ('running', 'succeeded', 'failed', 'cancelled')),
  attempt INTEGER NOT NULL CHECK (attempt >= 1),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE job_steps (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  step_status TEXT NOT NULL CHECK (
    step_status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'retrying')
  ),
  attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE job_events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
  step_id TEXT REFERENCES job_steps(id) ON DELETE SET NULL,
  ts TIMESTAMPTZ NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARN', 'ERROR')),
  event_type TEXT NOT NULL,
  message TEXT NOT NULL,
  data_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_user_accounts_email ON user_accounts(email);
CREATE INDEX idx_user_accounts_phone_number ON user_accounts(phone_number);
CREATE INDEX idx_user_accounts_openai_user_id ON user_accounts(openai_user_id);
CREATE INDEX idx_user_accounts_account_status ON user_accounts(account_status);

CREATE INDEX idx_team_workspaces_status ON team_workspaces(workspace_status);
CREATE INDEX idx_memberships_user_account_id ON user_account_team_workspace_memberships(user_account_id);
CREATE INDEX idx_memberships_team_workspace_id ON user_account_team_workspace_memberships(team_workspace_id);
CREATE INDEX idx_memberships_can_invite ON user_account_team_workspace_memberships(can_invite);
CREATE INDEX idx_memberships_status ON user_account_team_workspace_memberships(membership_status);

CREATE INDEX idx_batches_team_workspace_id ON workspace_join_batches(team_workspace_id);
CREATE INDEX idx_batches_status ON workspace_join_batches(batch_status, activation_status);

CREATE INDEX idx_batch_items_batch_id ON workspace_join_batch_items(batch_id);
CREATE INDEX idx_batch_items_user_account_id ON workspace_join_batch_items(user_account_id);
CREATE INDEX idx_batch_items_team_workspace_id ON workspace_join_batch_items(team_workspace_id);
CREATE INDEX idx_batch_items_membership_id ON workspace_join_batch_items(membership_id);
CREATE INDEX idx_batch_items_status ON workspace_join_batch_items(item_status, push_status);
CREATE INDEX idx_batch_items_plan_tag ON workspace_join_batch_items(plan_tag);

CREATE INDEX idx_codex_credentials_user_account_id ON codex_oauth_credentials(user_account_id);
CREATE INDEX idx_codex_credentials_team_workspace_id ON codex_oauth_credentials(team_workspace_id);
CREATE INDEX idx_codex_credentials_status ON codex_oauth_credentials(credential_status);
CREATE INDEX idx_codex_credentials_expires_at ON codex_oauth_credentials(expires_at);
CREATE INDEX idx_codex_credentials_token_chatgpt_account_id ON codex_oauth_credentials(token_chatgpt_account_id);
CREATE INDEX idx_codex_credentials_heartbeat_status ON codex_oauth_credentials(last_heartbeat_status);

CREATE INDEX idx_downstream_push_batch_item_id ON downstream_codex_push_records(batch_item_id);
CREATE INDEX idx_downstream_push_codex_credential_id ON downstream_codex_push_records(codex_credential_id);
CREATE INDEX idx_downstream_push_user_account_id ON downstream_codex_push_records(user_account_id);
CREATE INDEX idx_downstream_push_team_workspace_id ON downstream_codex_push_records(team_workspace_id);
CREATE INDEX idx_downstream_push_membership_id ON downstream_codex_push_records(membership_id);
CREATE INDEX idx_downstream_push_status ON downstream_codex_push_records(downstream_provider, push_status);

CREATE INDEX idx_proxy_inventory_status ON proxy_inventory(proxy_status);
CREATE INDEX idx_proxy_bindings_proxy_id ON user_account_proxy_bindings(proxy_id);
CREATE INDEX idx_proxy_bindings_status ON user_account_proxy_bindings(bind_status);

CREATE INDEX idx_mail_leases_user_account_id ON external_mail_leases(user_account_id);
CREATE INDEX idx_mail_leases_email ON external_mail_leases(email);
CREATE INDEX idx_mail_leases_status ON external_mail_leases(lease_status);

CREATE INDEX idx_jobs_status_priority ON jobs(job_status, priority, created_at);
CREATE INDEX idx_jobs_type ON jobs(type);
CREATE INDEX idx_work_items_job_id ON work_items(job_id);
CREATE INDEX idx_work_items_claim ON work_items(work_status, priority, created_at);
CREATE INDEX idx_work_items_execution_claim ON work_items(
  job_id, work_status, execution_key, priority, created_at
);
CREATE INDEX idx_work_items_type_status ON work_items(work_type, work_status);
CREATE INDEX idx_job_runs_job_id ON job_runs(job_id);
CREATE INDEX idx_job_runs_status ON job_runs(run_status);
CREATE INDEX idx_job_steps_run_id ON job_steps(run_id);
CREATE INDEX idx_job_steps_status ON job_steps(step_status);
CREATE INDEX idx_job_events_run_id_ts ON job_events(run_id, ts);
CREATE INDEX idx_job_events_step_id ON job_events(step_id);
CREATE INDEX idx_job_events_type ON job_events(event_type);

COMMIT;
