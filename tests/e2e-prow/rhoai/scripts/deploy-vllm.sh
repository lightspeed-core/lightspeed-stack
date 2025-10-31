#!/bin/bash

BASE_DIR="$1"

# Wait until the CRDs exist
for crd in servingruntimes.serving.kserve.io inferenceservices.serving.kserve.io; do
  echo "Waiting for CRD $crd to exist..."
  until oc get crd $crd &>/dev/null; do
    sleep 5
  done
  echo "CRD $crd exists. Waiting to be established..."
  oc wait --for=condition=established crd/$crd --timeout=120s
done

# Wait for KServe controller deployment to appear
echo "Waiting for kserve-controller-manager deployment to be created..."
until oc get deployment kserve-controller-manager -n redhat-ods-applications &>/dev/null; do
  sleep 10
done

# Wait for rollout to complete
echo "Waiting for kserve-controller-manager rollout..."
oc rollout status deployment/kserve-controller-manager -n redhat-ods-applications --timeout=300s

# Wait for the webhook service endpoints to become ready
echo "Waiting for KServe webhook service endpoints..."
until oc get endpoints kserve-webhook-server-service -n redhat-ods-applications -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | grep -qE '.'; do
  sleep 5
done
echo "✅ KServe webhook service is ready."

oc apply -f "$BASE_DIR/manifests/vllm/vllm-runtime-cpu.yaml"

oc apply -f "$BASE_DIR/manifests/vllm/inference-service.yaml"