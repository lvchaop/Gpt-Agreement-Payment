DELETE FROM team_admin_proxy_bindings binding
WHERE NOT EXISTS (
  SELECT 1
  FROM proxy_inventory proxy
  WHERE proxy.id = binding.proxy_id
);

ALTER TABLE team_admin_proxy_bindings
  DROP CONSTRAINT IF EXISTS fk_team_admin_proxy_bindings_proxy_id;

ALTER TABLE team_admin_proxy_bindings
  ADD CONSTRAINT fk_team_admin_proxy_bindings_proxy_id
  FOREIGN KEY (proxy_id)
  REFERENCES proxy_inventory(id)
  ON DELETE RESTRICT;
