# Zeabur Deployment

> Historical/optional deployment path. The current deployment target is a standalone virtual
> machine using the host bind mount documented in `VM_DEPLOYMENT.md`.

Deployment date: 2026-07-21

## Build

- Build root: `refactor-app`
- Service name: `invite-executor`
- Dockerfile selected by Zeabur: `Dockerfile.invite-executor`
- Container port: `8080`

The build root must remain `refactor-app` because the executor imports the existing
`refactor_app.plugins.openai_chatgpt` client.

## Zeabur Resources

- Project name: `invite-executor-snones`
- Project ID: `6a5f00fd536b84a1337c5dae`
- Environment ID: `6a5f00fdb0b7a4abeb4e628a`
- Service ID: `6a5f0152bf12353d8c0aaf4e`
- Initial deployment ID: `6a5f0177b33bf4df98a583f0`
- Backbone deployment ID: `6a5f2b9a9cfc4cd5e689112d`
- Prewarmed async deployment ID: `6a5f469a9cfc4cd5e68914e1`
- Endpoint fallback deployment ID: `6a5f61cde9e39c7397907073` (`invite-executor 0.4.3`)
- Session OTP deployment ID: `6a5f99ceb33bf4df98a5a414` (`invite-executor 0.5.0`)
- Linear OTP release deployment ID: `6a60e72ae9e39c739790a767`
- Region: `server-6a496ff958ae234d279e7995` (`Wonder Mesh`)

## Scheduling

The service must run as one replica and one Uvicorn worker. Its in-memory barrier and
result store cannot be shared between processes or replicas.

Required Kubernetes scheduling state:

```yaml
spec:
  replicas: 1
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: 100.64.0.126
```

`100.64.0.126` is the Wonder Mesh address of the server whose public IP is
`43.162.85.160`. After every Zeabur redeploy, verify both fields from the K3s control
plane:

```bash
kubectl get deployment service-6a5f0152bf12353d8c0aaf4e \
  -n environment-6a5f00fdb0b7a4abeb4e628a \
  -o jsonpath='{.spec.replicas}{" "}{.spec.template.spec.nodeSelector}{"\n"}'

kubectl get pods \
  -n environment-6a5f00fdb0b7a4abeb4e628a \
  -l zeabur_service_id=6a5f0152bf12353d8c0aaf4e \
  -o wide
```

If the selector is missing, restore it:

```bash
kubectl patch deployment service-6a5f0152bf12353d8c0aaf4e \
  -n environment-6a5f00fdb0b7a4abeb4e628a \
  --type merge \
  -p '{"spec":{"replicas":1,"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"100.64.0.126"}}}}}'
```

## Required Variables

- `INVITE_EXECUTOR_API_KEY`: required secret; never commit its value
- `INVITE_EXECUTOR_MAX_BATCH_SIZE=1000`
- `INVITE_EXECUTOR_BARRIER_TIMEOUT_S=30`
- `INVITE_EXECUTOR_INVITE_RELEASE_INTERVAL_MS=1`
- `INVITE_EXECUTOR_SESSION_OTP_BARRIER_TIMEOUT_S=120`
- `INVITE_EXECUTOR_SESSION_OTP_RELEASE_WINDOW_S=0`
- `INVITE_EXECUTOR_REQUEST_TIMEOUT_S=30`
- `INVITE_EXECUTOR_PREWARM_ROUNDS=1`
- `INVITE_EXECUTOR_PREWARM_ATTEMPTS=10`
- `INVITE_EXECUTOR_PREWARM_START_INTERVAL_MS=20`
- `INVITE_EXECUTOR_PREWARM_KEEPALIVE_INTERVAL_S=5`
- `INVITE_EXECUTOR_PREWARM_TIMEOUT_S=5`
- `INVITE_EXECUTOR_RESULT_TTL_S=3600`
- `INVITE_EXECUTOR_CHATGPT_BASE_URL=https://chatgpt.com`
- `INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_HOST=p.webshare.io`
- `INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_PORT=80`
- `INVITE_EXECUTOR_STATIC_PROXY_USERNAME`: required Webshare Backbone base username
- `INVITE_EXECUTOR_STATIC_PROXY_PASSWORD`: required Webshare Backbone password
- `INVITE_EXECUTOR_STATIC_PROXY_COUNTRY=US`
- `INVITE_EXECUTOR_INVITE_PROXY_COUNT=1000`
- `INVITE_EXECUTOR_INVITES_PER_PROXY=1`
- `INVITE_EXECUTOR_LOG_LEVEL=info`
- `REFACTOR_APP_BROWSER_IMPERSONATE=chrome142`

Automatic replenishment is the server-side second step and is disabled by default. The local
Portal remains responsible for the first-step invitation batch. To enable the second step, also
configure:

- `INVITE_EXECUTOR_AUTO_REPLENISH_ENABLED=true`
- `INVITE_EXECUTOR_AUTO_REPLENISH_INTERVAL_S=120`
- `INVITE_EXECUTOR_AUTO_REPLENISH_MAX_WORKERS=20`
- `INVITE_EXECUTOR_AUTO_REPLENISH_REGISTRY_PATH=/data/replenishment-registry.json`
- `INVITE_EXECUTOR_AUTO_REPLENISH_ACCOUNT_PROXY_COUNT=1000`
- `INVITE_EXECUTOR_AUTO_REPLENISH_BUSINESS_AT_MIN_INTERVAL_S=10`
- `INVITE_EXECUTOR_AUTO_REPLENISH_USAGE_THRESHOLD_PERCENT=90`
- `INVITE_EXECUTOR_AUTO_REPLENISH_BROWSER_HEADLESS=true`
- `INVITE_EXECUTOR_AUTO_REPLENISH_BROWSER_OTP_TIMEOUT_S=180`
- `INVITE_EXECUTOR_AUTO_REPLENISH_BROWSER_ARTIFACT_ROOT=/data/artifacts`
- `INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_BASE_URL`
- `INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_API_KEY`
- `INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_ID`
- `INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_IDS`，例如 `6,10`
- `INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_BASE_URL`
- `INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_API_KEY`
- `OTP_TIMEOUT=180`

The local Portal registers or updates a Space when it submits the existing server-side invitation
batch. Administrators and Spaces are stored separately in the registry file: multiple Spaces may
reference the same administrator and therefore reuse one Cookie record and one stable admin proxy.
Each Space stores its own workspace access token, so another Space owned by the same administrator
cannot overwrite it. The registry is updated atomically and must be stored on a persistent `/data`
volume.

No local database, Redis, SMTP, or separate background-worker service is required. A persistent
volume is required for the administrator and Space registry.
Automatic replenishment reads remote ChatGPT state and calls the Sub2API Admin API; it does not
connect directly to the Sub2API database. Its account login, target Space switch, and Business AT
creation run inside Camoufox using the account's assigned static proxy. The browser posts
`/backend-api/wham/auth-credentials` itself after fetching the target workspace session token, so
the request retains the browser cookie, Origin, Referer, and browser networking context. The
Camoufox browser binary is downloaded on the first browser provisioning run into
`/data/cache/camoufox`; `/data` must remain a persistent mount so subsequent pod restarts do not
download it again.
The service generates Backbone usernames as `base_username-COUNTRY-endpoint` and resolves the
fixed gateway once before each invite batch. It does not download a proxy list. All CONNECT + TLS
warmups must succeed before the single in-memory barrier releases any invitation POST.

## Internal Endpoints

Inside this Zeabur project:

```text
http://invite-executor.zeabur.internal:8080
```

From another project in the same K3s cluster:

```text
http://service-6a5f0152bf12353d8c0aaf4e.environment-6a5f00fdb0b7a4abeb4e628a.svc.cluster.local:8080
```

No public domain is attached. Keep invitation access tokens and cookies on the
cluster-internal network unless an HTTPS domain is added.

## API

- `GET /health`: public health check
- `POST /v1/invite-batches`: create one batch, Bearer authentication required
- `GET /v1/invite-batches/{batch_id}`: query batch status, Bearer authentication required
- `POST /v1/session-otp-submit-batches`: create one OTP validate batch, Bearer authentication required
- `GET /v1/session-otp-submit-batches/{batch_id}`: query OTP batch status, Bearer authentication required
- `GET /v1/replenishment/spaces`: query isolated per-Space replenishment state, Bearer authentication required
- `POST /v1/replenishment/spaces/{external_space_id}/run`: trigger one Space cycle, Bearer authentication required
- `PUT /v1/replenishment/spaces/{external_space_id}`: dynamically add or update a Space and administrator authentication
- `DELETE /v1/replenishment/spaces/{external_space_id}`: remove a non-running Space from automatic replenishment

The create request requires `external_space_id`, `access_token`, and a non-empty,
duplicate-free `emails` list. `cookie_header` and `barrier_timeout_s` are optional. When the local
Portal includes `replenishment`, the service persists the administrator and Space before submitting
the invitation batch, so newly added Spaces enter the server scheduler without a restart.

The OTP create request contains a duplicate-free `items` list. Every item carries its
`item_id`, `email`, original direct `proxy_url`, and protocol `snapshot`. The service
does not allocate or replace OTP proxies. It restores each snapshot into one pinned
`AsyncSession`, prewarms `auth.openai.com`, validates connection reuse, releases one
memory barrier, and then releases `POST /api/accounts/email-otp/validate`
requests over the configured window. Set `INVITE_EXECUTOR_SESSION_OTP_RELEASE_WINDOW_S=0`
to submit all requests immediately after the barrier.

Invitation and OTP batches share one process-wide execution gate. Only one batch of
either type may run at a time.

Automatic replenishment does not use that execution gate. The same Space cannot re-enter while its
cycle is queued or running; different Spaces can run independently up to
`INVITE_EXECUTOR_AUTO_REPLENISH_MAX_WORKERS`.

## Redeploy

Run from the `refactor-app` directory. Do not call `zeabur deploy` directly because Zeabur
regenerates the Kubernetes Deployment and removes the hostPath mount. The deployment script waits
for the new image, restores the persistent mount and runtime constraints, and verifies that the
registry is loaded:

```bash
./packages/invite-executor/deploy-zeabur.sh
```
