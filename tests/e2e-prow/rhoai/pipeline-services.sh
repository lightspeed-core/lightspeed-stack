#!/bin/bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${NAMESPACE:-e2e-rhoai-dsc}"

# Deploy llama-stack (substitute only LLAMA_STACK_IMAGE, leave other ${} intact)
envsubst '${LLAMA_STACK_IMAGE}' < "$BASE_DIR/manifests/lightspeed/llama-stack-prow.yaml" | oc apply -n "$NAMESPACE" -f -

oc wait pod/llama-stack-service \
  -n "$NAMESPACE" --for=condition=Ready --timeout=600s

# Get url address of llama-stack pod
oc label pod llama-stack-service pod=llama-stack-service -n "$NAMESPACE"

oc expose pod llama-stack-service \
  --name=llama-stack-service-svc \
  --port=8321 \
  --type=ClusterIP \
  -n "$NAMESPACE"

export E2E_LLAMA_HOSTNAME="llama-stack-service-svc.${NAMESPACE}.svc.cluster.local"

oc create secret generic llama-stack-ip-secret \
    --from-literal=key="$E2E_LLAMA_HOSTNAME" \
    -n "$NAMESPACE" || echo "Secret exists"

# Deploy lightspeed-stack (substitute only LIGHTSPEED_STACK_IMAGE, leave other ${} intact)
LIGHTSPEED_STACK_IMAGE="${LIGHTSPEED_STACK_IMAGE:-quay.io/lightspeed-core/lightspeed-stack:dev-latest}"
export LIGHTSPEED_STACK_IMAGE
envsubst '${LIGHTSPEED_STACK_IMAGE}' < "$BASE_DIR/manifests/lightspeed/lightspeed-stack.yaml" | oc apply -n "$NAMESPACE" -f -
