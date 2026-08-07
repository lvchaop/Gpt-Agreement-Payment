# Virtual Machine Deployment

## 0. Fixed deployment target

Do not create a new service, change the node, or replace the SSH identity when redeploying.

```text
Public IP: 43.162.85.160
SSH user: root
SSH identity: /Users/chaopenglv/Documents/Codex/2026-07-02/qu/work/ssh/zeabur_tmp_ed25519
SSH public key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKlR8SwmZdHHujr5+JY2OxYjYYp9wLbX3sy65OCo9vK2 codex-temp-zeabur-debug
Reference host using the same identity: root@209.146.115.187
Zeabur server ID: 6a1d2938d62982be05bfe10d
Zeabur project ID: 6a5f00fd536b84a1337c5dae
Zeabur environment ID: 6a5f00fdb0b7a4abeb4e628a
Zeabur service ID: 6a5f0152bf12353d8c0aaf4e
Kubernetes namespace: environment-6a5f00fdb0b7a4abeb4e628a
Kubernetes deployment: service-6a5f0152bf12353d8c0aaf4e
Pinned node: 100.64.0.126
Kubernetes control plane: root@209.146.115.187
Public endpoint: http://43.162.85.160:31372
Container port: 8080
Host data directory: /opt/invite-executor/data
Container data directory: /data
Current deployment ID: 6a69d0abeac99cc636f2a89f
```

Connection check:

```bash
ssh \
  -i /Users/chaopenglv/Documents/Codex/2026-07-02/qu/work/ssh/zeabur_tmp_ed25519 \
  -o IdentitiesOnly=yes \
  root@43.162.85.160
```

## 1. Persistent directory

The service runs in the image as UID/GID `10001`. Create the host directory before starting the
container:

```bash
sudo install -d -m 700 -o 10001 -g 10001 /opt/invite-executor/data
```

The Kubernetes `hostPath` mount is:

```text
/opt/invite-executor/data -> /data
```

The dynamic administrator and Space registry is therefore stored on the VM at:

```text
/opt/invite-executor/data/replenishment-registry.json
```

## 2. Configuration

The Zeabur service owns the runtime environment variables. Automatic replenishment requires the
`INVITE_EXECUTOR_AUTO_REPLENISH_*` variables from `.env.example`; secret values must be read from
the existing Portal mail configuration and enabled Sub2API downstream channel. Do not replace the
existing invitation variables when updating them.

The deployed fixed values include:

```text
INVITE_EXECUTOR_AUTO_REPLENISH_ENABLED=true
INVITE_EXECUTOR_AUTO_REPLENISH_INTERVAL_S=120
INVITE_EXECUTOR_AUTO_REPLENISH_REGISTRY_PATH=/data/replenishment-registry.json
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_ID=6
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_IDS=6,10
```

## 3. Deploy the existing Zeabur service

Run from the `refactor-app` directory. Always pass the existing service ID so this updates the
current service instead of creating a duplicate:

Do not call `zeabur deploy` directly. Use the checked-in deployment script, which waits for the new
Zeabur image, reapplies these runtime properties, and verifies the persistent registry:

```bash
./packages/invite-executor/deploy-zeabur.sh
```

The script restores these properties through the Kubernetes control plane:

```text
replicas: 1
nodeSelector: kubernetes.io/hostname=100.64.0.126
runAsUser/runAsGroup/fsGroup: 10001
hostPath: /opt/invite-executor/data
mountPath: /data
```

The service must remain one Pod with one Uvicorn worker because invitation and OTP barriers are
process-local. Before changing the Deployment, save its YAML and the Service YAML. The backup for
deployment `6a69d0abeac99cc636f2a89f` is on the control plane at:

```text
/root/backups/invite-executor-20260729/deployment.yaml
/root/backups/invite-executor-20260729/service.yaml
```

## 4. Verify

```bash
curl http://43.162.85.160:31372/health

ssh -i /Users/chaopenglv/Documents/Codex/2026-07-02/qu/work/ssh/zeabur_tmp_ed25519 \
  root@209.146.115.187 \
  "kubectl get pods -n environment-6a5f00fdb0b7a4abeb4e628a -o wide"
```

Expected health fields:

```text
status=ok
auto_replenishment.enabled=true
auto_replenishment.dynamic_registration=true
auto_replenishment.interval_s=120
```

After the first Portal invitation registers a Space, verify the host file:

```bash
sudo stat /opt/invite-executor/data/replenishment-registry.json
```

The registry file mode must be `0600` and its owner must be UID/GID `10001`.
