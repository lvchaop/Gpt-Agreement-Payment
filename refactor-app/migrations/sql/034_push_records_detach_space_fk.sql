ALTER TABLE space_push_bindings
  DROP CONSTRAINT IF EXISTS space_push_bindings_space_credential_id_fkey;

ALTER TABLE space_push_bindings
  DROP CONSTRAINT IF EXISTS space_push_bindings_space_id_fkey;

ALTER TABLE space_push_bindings
  DROP CONSTRAINT IF EXISTS space_push_bindings_downstream_channel_id_fkey;

ALTER TABLE space_push_attempts
  DROP CONSTRAINT IF EXISTS space_push_attempts_space_credential_id_fkey;

ALTER TABLE space_push_attempts
  DROP CONSTRAINT IF EXISTS space_push_attempts_space_id_fkey;

ALTER TABLE space_push_attempts
  DROP CONSTRAINT IF EXISTS space_push_attempts_downstream_channel_id_fkey;
