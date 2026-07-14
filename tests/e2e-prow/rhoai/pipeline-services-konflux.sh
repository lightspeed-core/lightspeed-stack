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

# 1. Llama Stack (run from source; manifest is static, no envsubst)
oc apply -n "$NAMESPACE" -f "$BASE_DIR/manifests/lightspeed/llama-stack-openai.yaml"
if ! oc wait pod/llama-stack-service -n "$NAMESPACE" --for=condition=Ready --timeout=600s; then
  echo "FAILED: llama-stack-service pod did not become ready"
  echo "========== pod status =========="
  oc get pod llama-stack-service -n "$NAMESPACE" -o wide 2>&1 || true
  echo "========== pod describe (events) =========="
  oc describe pod llama-stack-service -n "$NAMESPACE" 2>&1 | tail -40 || true
  echo "========== init container: setup-from-source logs =========="
  oc logs llama-stack-service -n "$NAMESPACE" -c setup-from-source 2>&1 | tail -80 || true
  echo "========== init container: setup-rag-data logs =========="
  oc logs llama-stack-service -n "$NAMESPACE" -c setup-rag-data 2>&1 | tail -40 || true
  echo "========== main container: llama-stack-container logs =========="
  oc logs llama-stack-service -n "$NAMESPACE" -c llama-stack-container 2>&1 | tail -80 || true
fi

oc label pod llama-stack-service pod=llama-stack-service -n "$NAMESPACE"
oc expose pod llama-stack-service --name=llama-stack-service-svc --port=8321 --type=ClusterIP -n "$NAMESPACE"

export E2E_LLAMA_HOSTNAME="llama-stack-service-svc.${NAMESPACE}.svc.cluster.local"
oc create secret generic llama-stack-ip-secret --from-literal=key="$E2E_LLAMA_HOSTNAME" -n "$NAMESPACE" || true

# 2. Lightspeed Stack (image from env; default if unset)
if [[ -z "${LIGHTSPEED_STACK_IMAGE:-}" ]]; then
  echo "LIGHTSPEED_STACK_IMAGE is not set"; exit 1
fi
export LIGHTSPEED_STACK_IMAGE
LIGHTSPEED_MANIFEST="$BASE_DIR/manifests/lightspeed/lightspeed-stack.yaml"
if command -v envsubst >/dev/null 2>&1; then
  envsubst < "$LIGHTSPEED_MANIFEST" | oc apply -n "$NAMESPACE" -f -
else
  # ubi-minimal etc. may lack gettext; template only expands LIGHTSPEED_STACK_IMAGE
  sed "s|\${LIGHTSPEED_STACK_IMAGE}|${LIGHTSPEED_STACK_IMAGE}|g" "$LIGHTSPEED_MANIFEST" |
    oc apply -n "$NAMESPACE" -f -
fi
