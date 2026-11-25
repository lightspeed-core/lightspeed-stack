#!/bin/bash
# Deploy Lightspeed Stack (library mode) for Konflux E2E only. Classic Prow uses pipeline-services.sh.

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

LIGHTSPEED_STACK_IMAGE="${LIGHTSPEED_STACK_IMAGE:-quay.io/lightspeed-core/lightspeed-stack:dev-latest}"
export LIGHTSPEED_STACK_IMAGE
LIGHTSPEED_MANIFEST="$BASE_DIR/manifests/lightspeed/lightspeed-stack.yaml"

timeout 120 oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --wait=true 2>/dev/null || \
  oc delete pod lightspeed-stack-service -n "$NAMESPACE" --ignore-not-found=true --force --grace-period=0 2>/dev/null || true

if command -v envsubst >/dev/null 2>&1; then
  envsubst '${LIGHTSPEED_STACK_IMAGE}' < "$LIGHTSPEED_MANIFEST" | oc apply -n "$NAMESPACE" -f -
else
  sed "s|\${LIGHTSPEED_STACK_IMAGE}|${LIGHTSPEED_STACK_IMAGE}|g" "$LIGHTSPEED_MANIFEST" |
    oc apply -n "$NAMESPACE" -f -
fi

oc wait pod/lightspeed-stack-service -n "$NAMESPACE" --for=condition=Ready --timeout=900s
oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n "$NAMESPACE" --overwrite