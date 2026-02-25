#!/bin/bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Deploy llama-stack
envsubst < "$BASE_DIR/manifests/lightspeed/llama-stack.yaml" | oc apply -f -

oc wait pod/llama-stack-service \
  -n e2e-rhoai-dsc --for=condition=Ready --timeout=600s

# Get url address of llama-stack pod
oc label pod llama-stack-service pod=llama-stack-service -n e2e-rhoai-dsc

oc expose pod llama-stack-service \
  --name=llama-stack-service-svc \
  --port=8321 \
  --type=ClusterIP \
  -n e2e-rhoai-dsc

export E2E_LLAMA_HOSTNAME="llama-stack-service-svc.e2e-rhoai-dsc.svc.cluster.local"

oc create secret generic llama-stack-ip-secret \
    --from-literal=key="$E2E_LLAMA_HOSTNAME" \
    -n e2e-rhoai-dsc || echo "Secret exists"

# Deploy lightspeed-stack
oc apply -f "$BASE_DIR/manifests/lightspeed/lightspeed-stack.yaml"
