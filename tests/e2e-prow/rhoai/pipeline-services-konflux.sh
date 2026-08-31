#!/bin/bash
# Deploy Llama (OpenAI run-from-source) + Lightspeed for Konflux E2E only. Prow uses pipeline-services.sh.

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$BASE_DIR/../../.." && pwd)"
NAMESPACE="${NAMESPACE:-e2e-rhoai-dsc}"
export NAMESPACE

if [ -f "$REPO_ROOT/tests/e2e/secrets/mcp-token" ]; then
  oc create secret generic mcp-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/mcp-token" \
    --dry-run=client -o yaml | oc apply -f -
fi

if [ -f "$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" ]; then
  oc create secret generic mcp-invalid-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" \
    --dry-run=client -o yaml | oc apply -f -
fi

# 1. OGX (run from source). Cluster DNS name matches oc expose --name=llama-stack-service-svc.
# Secret must exist before the pod: both LCS and OGX-container use E2E_LLAMA_HOSTNAME from it.
_LLAMA_SVC_FQDN="llama-stack-service-svc.${NAMESPACE}.svc.cluster.local"
oc create secret generic llama-stack-ip-secret \
  --from-literal=key="$_LLAMA_SVC_FQDN" \
  -n "$NAMESPACE" \
  --dry-run=client -o yaml | oc apply -f -

# PVC must exist before the pod (pipeline-konflux.sh creates it; guard here for standalone use).
oc get pvc llama-stack-app-root -n "$NAMESPACE" >/dev/null 2>&1 || \
  oc apply -n "$NAMESPACE" -f - <<'PVCEOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: llama-stack-app-root
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
PVCEOF

timeout 120 oc delete pod llama-stack-service -n "$NAMESPACE" --ignore-not-found=true --wait=true 2>/dev/null || true
oc apply -n "$NAMESPACE" -f "$BASE_DIR/manifests/lightspeed/llama-stack-openai.yaml"

# First boot runs the full init (dnf + git clone + uv sync ≈ 6-15 min); poll with progress updates
echo "Waiting for llama-stack-service to be ready (up to 15 min for first boot)..."
for i in $(seq 1 90); do
  if oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -q "True"; then
    echo "✅ llama-stack-service ready after $(( i * 10 ))s"
    break
  fi
  if [ $((i % 6)) -eq 0 ]; then
    echo "[$(( i * 10 ))s] Still waiting for llama-stack-service... (pod status: $(oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo 'unknown'))"
  fi
  if [ $i -eq 90 ]; then
    echo "❌ llama-stack-service not ready after 900s"
    oc get pod llama-stack-service -n "$NAMESPACE" -o wide 2>/dev/null || true
    oc describe pod llama-stack-service -n "$NAMESPACE" 2>/dev/null | tail -50 || true
    exit 1
  fi
  sleep 10
done

oc label pod llama-stack-service pod=llama-stack-service -n "$NAMESPACE"
oc expose pod llama-stack-service --name=llama-stack-service-svc --port=8321 --type=ClusterIP -n "$NAMESPACE"

# 2. Lightspeed Stack (image from env; default if unset)
LIGHTSPEED_STACK_IMAGE="${LIGHTSPEED_STACK_IMAGE:-quay.io/lightspeed-core/lightspeed-stack:dev-latest}"
export LIGHTSPEED_STACK_IMAGE
LIGHTSPEED_MANIFEST="$BASE_DIR/manifests/lightspeed/lightspeed-stack.yaml"
if command -v envsubst >/dev/null 2>&1; then
  envsubst '${LIGHTSPEED_STACK_IMAGE}' < "$LIGHTSPEED_MANIFEST" | oc apply -n "$NAMESPACE" -f -
else
  # ubi-minimal etc. may lack gettext; template only expands LIGHTSPEED_STACK_IMAGE
  sed "s|\${LIGHTSPEED_STACK_IMAGE}|${LIGHTSPEED_STACK_IMAGE}|g" "$LIGHTSPEED_MANIFEST" |
    oc apply -n "$NAMESPACE" -f -
fi
