ALTER TABLE downstream_channels
  DROP CONSTRAINT IF EXISTS downstream_channels_provider_type_check;

ALTER TABLE downstream_channels
  ADD CONSTRAINT downstream_channels_provider_type_check
  CHECK (provider_type IN ('sub2api', 'cpa', 'local_sub2api', 'custom_http'));

ALTER TABLE downstream_codex_push_records
  DROP CONSTRAINT IF EXISTS downstream_codex_push_records_downstream_provider_check;

ALTER TABLE downstream_codex_push_records
  ADD CONSTRAINT downstream_codex_push_records_downstream_provider_check
  CHECK (downstream_provider IN ('cpa', 'sub2api', 'local_sub2api', 'custom_http'));
