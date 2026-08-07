#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-6a5f00fd536b84a1337c5dae}"
ENVIRONMENT_ID="${ENVIRONMENT_ID:-6a5f00fdb0b7a4abeb4e628a}"
SERVICE_ID="${SERVICE_ID:-6a5f0152bf12353d8c0aaf4e}"
NAMESPACE="${NAMESPACE:-environment-${ENVIRONMENT_ID}}"
DEPLOYMENT="${DEPLOYMENT:-service-${SERVICE_ID}}"
CONTAINER_NAME="${CONTAINER_NAME:-invite-executor}"
CONTROL_PLANE="${CONTROL_PLANE:-root@209.146.115.187}"
SSH_IDENTITY="${SSH_IDENTITY:-/Users/chaopenglv/Documents/Codex/2026-07-02/qu/work/ssh/zeabur_tmp_ed25519}"
PINNED_NODE="${PINNED_NODE:-100.64.0.127}"
HOST_DATA_DIR="${HOST_DATA_DIR:-/opt/invite-executor/data}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-http://43.162.85.160:31372/health}"
HELPER_IMAGE="${HELPER_IMAGE:-busybox:1.36}"
EXPECTED_REPLENISHMENT_INTERVAL_S="${EXPECTED_REPLENISHMENT_INTERVAL_S:-60}"
EXPECTED_AUTO_REPLENISH_ENABLED="${EXPECTED_AUTO_REPLENISH_ENABLED:-true}"
MODE="${1:-deploy}"

SSH=(
  ssh
  -i "$SSH_IDENTITY"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=no
  -o ConnectTimeout=10
  "$CONTROL_PLANE"
)

if [[ ! -f "$SSH_IDENTITY" ]]; then
  printf 'SSH identity not found: %s\n' "$SSH_IDENTITY" >&2
  exit 1
fi

prepare_target_registry() {
  local image target_pod manifest
  image="$("${SSH[@]}" "sudo kubectl get deployment/$DEPLOYMENT -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}'" 2>/dev/null || true)"
  if [[ -z "$image" ]]; then
    image="$HELPER_IMAGE"
  fi
  target_pod="invite-executor-data-target"
  "${SSH[@]}" "sudo kubectl delete pod/$target_pod -n $NAMESPACE --ignore-not-found --wait=false" >/dev/null
  read -r -d '' manifest <<JSON || true
apiVersion: v1
kind: Pod
metadata:
  name: $target_pod
  namespace: $NAMESPACE
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: $PINNED_NODE
  securityContext:
    runAsUser: 0
    runAsGroup: 0
  containers:
    - name: data-helper
      image: $image
      command: ["/bin/sh", "-c", "sleep 600"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      hostPath:
        path: $HOST_DATA_DIR
        type: DirectoryOrCreate
JSON
  printf '%s\n' "$manifest" | "${SSH[@]}" "sudo kubectl apply -f -" >/dev/null
  "${SSH[@]}" "sudo kubectl wait pod/$target_pod -n $NAMESPACE --for=condition=Ready --timeout=120s" >/dev/null
  if ! "${SSH[@]}" "sudo kubectl exec $target_pod -n $NAMESPACE -- test -s /data/replenishment-registry.json"; then
    printf 'Registry is missing on pinned node %s.\n' "$PINNED_NODE" >&2
    exit 1
  fi
  printf 'Target registry exists on %s; preserving it.\n' "$PINNED_NODE"
  "${SSH[@]}" "sudo kubectl exec $target_pod -n $NAMESPACE -- chown 10001:10001 /data/replenishment-registry.json"
  "${SSH[@]}" "sudo kubectl delete pod/$target_pod -n $NAMESPACE --ignore-not-found --wait=false" >/dev/null
}

prepare_target_registry

case "$MODE" in
  deploy)
    old_image="$("${SSH[@]}" "sudo kubectl get deployment/$DEPLOYMENT -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}'" 2>/dev/null || true)"

    set +e
    npx zeabur@latest deploy \
      --project-id "$PROJECT_ID" \
      --service-id "$SERVICE_ID" \
      --environment-id "$ENVIRONMENT_ID" \
      -i=false \
      --json
    deploy_exit_code=$?
    set -e
    if [[ "$deploy_exit_code" -ne 0 ]]; then
      printf 'Zeabur CLI exited with %s; checking whether the Deployment was still published.\n' "$deploy_exit_code" >&2
    fi

    printf 'Waiting for Zeabur to publish the new image...\n'
    new_image=""
    for _ in $(seq 1 120); do
      new_image="$("${SSH[@]}" "sudo kubectl get deployment/$DEPLOYMENT -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].image}'" 2>/dev/null || true)"
      if [[ -n "$new_image" && "$new_image" != "$old_image" ]]; then
        break
      fi
      sleep 5
    done

    if [[ -z "$new_image" || "$new_image" == "$old_image" ]]; then
      printf 'Timed out waiting for the Zeabur Deployment image to change.\n' >&2
      exit 1
    fi
    ;;
  --restore-runtime-only)
    printf 'Skipping image deployment; restoring persistent runtime settings only.\n'
    ;;
  *)
    printf 'Usage: %s [deploy|--restore-runtime-only]\n' "$0" >&2
    exit 2
    ;;
esac

read -r -d '' deployment_patch <<JSON || true
{
  "spec": {
    "replicas": 1,
    "template": {
      "spec": {
        "nodeSelector": {
          "kubernetes.io/hostname": "$PINNED_NODE"
        },
        "securityContext": {
          "runAsUser": 10001,
          "runAsGroup": 10001,
          "fsGroup": 10001
        },
        "volumes": [
          {
            "name": "invite-executor-data",
            "hostPath": {
              "path": "$HOST_DATA_DIR",
              "type": "Directory"
            }
          }
        ],
        "initContainers": [
          {
            "name": "invite-executor-data-permissions",
            "image": "$HELPER_IMAGE",
            "command": [
              "/bin/sh",
              "-c",
              "mkdir -p /data/cache /data/artifacts && chown -R 10001:10001 /data"
            ],
            "securityContext": {
              "runAsUser": 0,
              "runAsGroup": 0
            },
            "volumeMounts": [
              {
                "name": "invite-executor-data",
                "mountPath": "/data"
              }
            ]
          }
        ],
        "containers": [
          {
            "name": "$CONTAINER_NAME",
            "volumeMounts": [
              {
                "name": "invite-executor-data",
                "mountPath": "/data"
              }
            ]
          }
        ]
      }
    }
  }
}
JSON

printf '%s' "$deployment_patch" | "${SSH[@]}" \
  "sudo kubectl patch deployment/$DEPLOYMENT -n $NAMESPACE --type strategic --patch-file=/dev/stdin"

"${SSH[@]}" \
  "sudo kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE --timeout=300s"

pod=""
for _ in $(seq 1 30); do
  pod="$("${SSH[@]}" "sudo kubectl get pods -n $NAMESPACE -l zeabur_service_id=$SERVICE_ID --field-selector=status.phase=Running --sort-by=.metadata.creationTimestamp -o name | tail -n 1 | cut -d/ -f2")"
  ready=""
  if [[ -n "$pod" ]]; then
    ready="$("${SSH[@]}" "sudo kubectl get pod/$pod -n $NAMESPACE -o jsonpath='{.status.containerStatuses[0].ready}'" 2>/dev/null || true)"
  fi
  if [[ "$ready" == "true" ]]; then
    break
  fi
  pod=""
  sleep 2
done
if [[ -z "$pod" ]]; then
  printf 'No running Pod found for service %s after rollout.\n' "$SERVICE_ID" >&2
  exit 1
fi

pod_node="$("${SSH[@]}" "sudo kubectl get pod/$pod -n $NAMESPACE -o jsonpath='{.spec.nodeName}'")"
if [[ "$pod_node" != "$PINNED_NODE" ]]; then
  printf 'Pod %s is running on %s, expected %s.\n' "$pod" "$pod_node" "$PINNED_NODE" >&2
  exit 1
fi

registry_ready="false"
for _ in $(seq 1 30); do
  if "${SSH[@]}" \
    "sudo kubectl exec $pod -n $NAMESPACE -- test -f /data/replenishment-registry.json"; then
    registry_ready="true"
    break
  fi
  sleep 2
done
if [[ "$registry_ready" != "true" ]]; then
  printf 'Persistent registry is missing in Pod %s.\n' "$pod" >&2
  exit 1
fi

runtime_spec="$("${SSH[@]}" "sudo kubectl get deployment/$DEPLOYMENT -n $NAMESPACE -o jsonpath='{.spec.replicas}|{.spec.template.spec.nodeSelector.kubernetes\\.io/hostname}|{.spec.template.spec.securityContext.runAsUser}|{.spec.template.spec.volumes[?(@.name==\"invite-executor-data\")].hostPath.path}|{.spec.template.spec.containers[?(@.name==\"$CONTAINER_NAME\")].volumeMounts[?(@.name==\"invite-executor-data\")].mountPath}'")"
expected_spec="1|$PINNED_NODE|10001|$HOST_DATA_DIR|/data"
if [[ "$runtime_spec" != "$expected_spec" ]]; then
  printf 'Unexpected runtime spec: %s\n' "$runtime_spec" >&2
  printf 'Expected runtime spec:   %s\n' "$expected_spec" >&2
  exit 1
fi

health_payload=""
startup_state=""
for _ in $(seq 1 90); do
  health_payload="$(curl -fsS --retry 2 --retry-delay 1 --retry-connrefused --max-time 10 "$PUBLIC_HEALTH_URL" 2>/dev/null || true)"
  if [[ -n "$health_payload" ]]; then
    startup_state="$(HEALTH_PAYLOAD="$health_payload" python3 -c 'import json, os; print((json.loads(os.environ["HEALTH_PAYLOAD"]).get("auto_replenishment") or {}).get("startup_state", ""))' 2>/dev/null || true)"
    if [[ "$EXPECTED_AUTO_REPLENISH_ENABLED" == "true" && "$startup_state" == "ready" ]]; then
      break
    fi
    if [[ "$EXPECTED_AUTO_REPLENISH_ENABLED" == "false" && "$startup_state" == "disabled" ]]; then
      break
    fi
  fi
  sleep 2
done
expected_startup_state="ready"
if [[ "$EXPECTED_AUTO_REPLENISH_ENABLED" == "false" ]]; then
  expected_startup_state="disabled"
fi
if [[ "$startup_state" != "$expected_startup_state" ]]; then
  printf 'Automatic replenishment startup state mismatch; actual=%s expected=%s\n' "$startup_state" "$expected_startup_state" >&2
  [[ -n "$health_payload" ]] && printf '%s\n' "$health_payload" >&2
  exit 1
fi
printf '%s\n' "$health_payload"

HEALTH_PAYLOAD="$health_payload" EXPECTED_REPLENISHMENT_INTERVAL_S="$EXPECTED_REPLENISHMENT_INTERVAL_S" EXPECTED_AUTO_REPLENISH_ENABLED="$EXPECTED_AUTO_REPLENISH_ENABLED" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["HEALTH_PAYLOAD"])
replenishment = payload.get("auto_replenishment") or {}
if payload.get("status") != "ok":
    raise SystemExit("health status is not ok")
expected_enabled = os.environ["EXPECTED_AUTO_REPLENISH_ENABLED"] == "true"
if bool(replenishment.get("enabled")) != expected_enabled:
    raise SystemExit(
        f"unexpected automatic replenishment enabled state: {replenishment.get('enabled')}"
    )
expected_startup_state = "ready" if expected_enabled else "disabled"
if replenishment.get("startup_state") != expected_startup_state:
    raise SystemExit(
        "unexpected automatic replenishment startup state: "
        f"{replenishment.get('startup_state')}, expected {expected_startup_state}"
    )
expected_interval = float(os.environ["EXPECTED_REPLENISHMENT_INTERVAL_S"])
actual_interval = float(replenishment.get("interval_s") or 0)
if actual_interval != expected_interval:
    raise SystemExit(
        f"unexpected replenishment interval: {actual_interval}, expected {expected_interval}"
    )
print(
    "deployment verified: interval_s="
    f"{actual_interval:g} configured_space_count="
    f"{replenishment.get('configured_space_count', 0)}"
)
PY
