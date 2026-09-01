#!/bin/bash
set -euo pipefail
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

# Signal to e2e tests that we're running in Prow/OpenShift
export RUNNING_PROW=true

#========================================
# 1. GLOBAL CONFIG
#========================================
NAMESPACE="e2e-rhoai-dsc"
export NAMESPACE
MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# RHOAI OGX image (unused when building from source via ogx-openai.yaml)
# LLAMA_STACK_IMAGE="${LLAMA_STACK_IMAGE:-quay.io/rhoai/odh-llama-stack-core-rhel9:rhoai-3.4-ea.2}"
# echo "Using OGX image: $LLAMA_STACK_IMAGE"
# export LLAMA_STACK_IMAGE

#========================================
# 2. ENVIRONMENT SETUP
#========================================
echo "===== Setting up environment variables ====="
export HUGGING_FACE_HUB_TOKEN=$(cat /var/run/huggingface/hf-token-ces-lcore-test || true)
export VLLM_API_KEY=$(cat /var/run/vllm/vllm-api-key-lcore-test || true)
export QUAY_ROBOT_NAME=$(cat /var/run/quay-aipcc-name/lcore-quay-name-lcore-test || true)
export QUAY_ROBOT_PASSWORD=$(cat /var/run/quay-aipcc-password/lcore-quay-password-lcore-test || true)


[[ -n "$HUGGING_FACE_HUB_TOKEN" ]] && echo "✅ HUGGING_FACE_HUB_TOKEN is set" || { echo "❌ Missing HUGGING_FACE_HUB_TOKEN"; exit 1; }
[[ -n "$VLLM_API_KEY" ]] && echo "✅ VLLM_API_KEY is set" || { echo "❌ Missing VLLM_API_KEY"; exit 1; }
[[ -n "$QUAY_ROBOT_NAME" ]] && echo "✅ QUAY_ROBOT_NAME is set" || { echo "❌ Missing QUAY_ROBOT_NAME"; exit 1; }
[[ -n "$QUAY_ROBOT_PASSWORD" ]] && echo "✅ QUAY_ROBOT_PASSWORD is set" || { echo "❌ Missing QUAY_ROBOT_PASSWORD"; exit 1; }

# Basic info
ls -A || true
oc version
oc whoami

#========================================
# 3. BOOTSTRAP OPERATORS & DSC (before namespace — DSC operator may delete it)
#========================================
echo "===== Bootstrapping operators ====="
# Create NFD and NVIDIA namespaces (needed by operator subscriptions)
oc apply -f "$PIPELINE_DIR/manifests/namespaces/nfd.yaml"
oc apply -f "$PIPELINE_DIR/manifests/namespaces/nvidia-operator.yaml"

# Install operators and apply DataScienceCluster (this may delete/recreate namespaces)
"$PIPELINE_DIR/scripts/bootstrap.sh" "$PIPELINE_DIR"

#========================================
# 4. CREATE NAMESPACE & SECRETS (after DSC settles)
#========================================
echo "===== Creating namespace & secrets ====="
oc get ns "$NAMESPACE" >/dev/null 2>&1 || oc create namespace "$NAMESPACE"

create_secret() {
    local name=$1; shift
    echo "Creating secret $name..."
    oc create secret generic "$name" "$@" -n "$NAMESPACE" 2>/dev/null || echo "Secret $name exists"
}

create_secret hf-token-secret --from-literal=token="$HUGGING_FACE_HUB_TOKEN"
create_secret vllm-api-key-secret --from-literal=key="$VLLM_API_KEY"
create_secret openai-api-key-secret --from-literal=key=""
create_secret vllm-model-secret --from-literal=key="$MODEL_NAME"

# MCP token secrets for lightspeed-stack
REPO_ROOT="$(cd "$PIPELINE_DIR/../../.." && pwd)"
if [ -f "$REPO_ROOT/tests/e2e/secrets/mcp-token" ]; then
  oc create secret generic mcp-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/mcp-token" \
    --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -
  echo "✅ mcp-file-auth-token secret applied"
fi
if [ -f "$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" ]; then
  oc create secret generic mcp-invalid-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" \
    --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -
  echo "✅ mcp-invalid-file-auth-token secret applied"
fi

# Create Quay pull secret for OGX images
echo "Creating Quay pull secret..."
oc create secret docker-registry quay-lightspeed-pull-secret \
  --docker-server=quay.io \
  --docker-username="$QUAY_ROBOT_NAME" \
  --docker-password="$QUAY_ROBOT_PASSWORD" \
  -n "$NAMESPACE" 2>/dev/null && echo "✅ Quay pull secret created" || echo "⚠️  Secret exists or creation failed"

# Link the secret to default service account for image pulls
oc secrets link default quay-lightspeed-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"

# Create Red Hat registry pull secret for OKP images
# Option 1: Use mounted docker-registry secret (preferred - simpler)
if [[ -f /var/run/redhat-registry-pull-secret/.dockerconfigjson ]]; then
  echo "Creating Red Hat registry pull secret from mounted docker-registry secret..."

  DOCKERCONFIG_BASE64=$(cat /var/run/redhat-registry-pull-secret/.dockerconfigjson | base64 -w0)

  # Get current pipeline Pod metadata for ownerReference (ensures cleanup after job completes)
  PIPELINE_POD_NAME="${HOSTNAME}"
  # Pipeline pod runs in its own namespace - read from service account mount
  PIPELINE_POD_NAMESPACE=""
  if [[ -f /var/run/secrets/kubernetes.io/serviceaccount/namespace ]]; then
    PIPELINE_POD_NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
  fi
  if [[ -z "$PIPELINE_POD_NAMESPACE" ]]; then
    echo "❌ FATAL: Cannot determine pipeline pod namespace"
    echo "   Service account namespace file not found or empty"
    exit 1
  fi
  echo "DEBUG: PIPELINE_POD_NAME=$PIPELINE_POD_NAME"
  echo "DEBUG: PIPELINE_POD_NAMESPACE=$PIPELINE_POD_NAMESPACE"
  echo "DEBUG: Attempting: oc get pod $PIPELINE_POD_NAME -n $PIPELINE_POD_NAMESPACE"

  PIPELINE_POD_UID=""
  if ! PIPELINE_POD_UID=$(oc get pod "$PIPELINE_POD_NAME" -n "$PIPELINE_POD_NAMESPACE" -o jsonpath='{.metadata.uid}' 2>&1); then
    echo "DEBUG: oc get pod failed with: $PIPELINE_POD_UID"
    # Try listing pods in the namespace to see what's available
    echo "DEBUG: Pods in namespace $PIPELINE_POD_NAMESPACE:"
    oc get pods -n "$PIPELINE_POD_NAMESPACE" -o name 2>&1 | head -10 || true
  fi

  if [[ -n "$PIPELINE_POD_UID" ]]; then
    echo "Setting ownerReference to pipeline Pod: $PIPELINE_POD_NAME (namespace: $PIPELINE_POD_NAMESPACE)"

    # Create secret with ownerReference using YAML (ensures automatic cleanup)
    cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: redhat-registry-pull-secret
  namespace: $NAMESPACE
  ownerReferences:
  - apiVersion: v1
    kind: Pod
    name: $PIPELINE_POD_NAME
    uid: $PIPELINE_POD_UID
    controller: false
    blockOwnerDeletion: false
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: $DOCKERCONFIG_BASE64
EOF
    echo "✅ Red Hat registry pull secret created with ownerReference"

    # Link to default service account
    oc secrets link default redhat-registry-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"
  else
    # SECURITY: Fail closed if we cannot set ownerReference
    # Creating secrets without ownerReference leads to credential sprawl
    echo "❌ FATAL: Cannot get pipeline Pod metadata for ownerReference"
    echo "   Secret creation requires valid owner UID to ensure cleanup"
    echo "   Pipeline Pod: $PIPELINE_POD_NAME"
    exit 1
  fi

# Option 2: Fallback to environment variables (legacy Prow approach)
elif [[ -n "${REDHAT_REGISTRY_USERNAME:-}" ]] && [[ -n "${REDHAT_REGISTRY_PASSWORD:-}" ]]; then
  echo "Creating Red Hat registry pull secret from environment variables..."

  # Get current pipeline Pod metadata for ownerReference (ensures cleanup after job completes)
  PIPELINE_POD_NAME="${HOSTNAME}"
  # Pipeline pod runs in its own namespace - read from service account mount
  PIPELINE_POD_NAMESPACE=""
  if [[ -f /var/run/secrets/kubernetes.io/serviceaccount/namespace ]]; then
    PIPELINE_POD_NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
  fi
  if [[ -z "$PIPELINE_POD_NAMESPACE" ]]; then
    echo "❌ FATAL: Cannot determine pipeline pod namespace"
    echo "   Service account namespace file not found or empty"
    exit 1
  fi
  echo "DEBUG: PIPELINE_POD_NAME=$PIPELINE_POD_NAME"
  echo "DEBUG: PIPELINE_POD_NAMESPACE=$PIPELINE_POD_NAMESPACE"
  echo "DEBUG: Attempting: oc get pod $PIPELINE_POD_NAME -n $PIPELINE_POD_NAMESPACE"

  PIPELINE_POD_UID=""
  if ! PIPELINE_POD_UID=$(oc get pod "$PIPELINE_POD_NAME" -n "$PIPELINE_POD_NAMESPACE" -o jsonpath='{.metadata.uid}' 2>&1); then
    echo "DEBUG: oc get pod failed with: $PIPELINE_POD_UID"
    # Try listing pods in the namespace to see what's available
    echo "DEBUG: Pods in namespace $PIPELINE_POD_NAMESPACE:"
    oc get pods -n "$PIPELINE_POD_NAMESPACE" -o name 2>&1 | head -10 || true
  fi

  if [[ -n "$PIPELINE_POD_UID" ]]; then
    echo "Setting ownerReference to pipeline Pod: $PIPELINE_POD_NAME (namespace: $PIPELINE_POD_NAMESPACE)"

    # Create secret with ownerReference (oc handles JSON encoding safely)
    oc create secret docker-registry redhat-registry-pull-secret \
      --docker-server=registry.redhat.io \
      --docker-username="$REDHAT_REGISTRY_USERNAME" \
      --docker-password="$REDHAT_REGISTRY_PASSWORD" \
      -n "$NAMESPACE" \
      --dry-run=client -o json | \
    jq --arg name "$PIPELINE_POD_NAME" --arg uid "$PIPELINE_POD_UID" \
      '.metadata.ownerReferences = [{"apiVersion":"v1","kind":"Pod","name":$name,"uid":$uid,"controller":false,"blockOwnerDeletion":false}]' | \
    oc apply -f -
    echo "✅ Red Hat registry pull secret created with ownerReference"
  else
    # SECURITY: Fail closed if we cannot set ownerReference
    # Creating secrets without ownerReference leads to credential sprawl
    echo "❌ FATAL: Cannot get pipeline Pod metadata for ownerReference"
    echo "   Secret creation requires valid owner UID to ensure cleanup"
    echo "   Pipeline Pod: $PIPELINE_POD_NAME"
    exit 1
  fi

  # Link to default service account
  oc secrets link default redhat-registry-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"
else
  echo "⚠️  REDHAT_REGISTRY_USERNAME/PASSWORD not set - OKP image pull may fail"
  echo "   (This is OK if not testing OKP features)"
fi


#========================================
# 5. CONFIGMAPS
#========================================
echo "===== Setting up configmaps ====="

curl -sL -o tool_chat_template_llama3.1_json.jinja \
    https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_llama3.1_json.jinja \
    || { echo "❌ Failed to download jinja template"; exit 1; }

oc create configmap vllm-chat-template -n "$NAMESPACE" \
    --from-file=tool_chat_template_llama3.1_json.jinja --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -


#========================================
# 6. DEPLOY vLLM (GPU setup + deploy, bootstrap already done)
#========================================
echo "===== Deploying vLLM ====="
"$PIPELINE_DIR/scripts/gpu-setup.sh" "$PIPELINE_DIR"
source "$PIPELINE_DIR/scripts/fetch-vllm-image.sh"
"$PIPELINE_DIR/scripts/deploy-vllm.sh" "$PIPELINE_DIR"
"$PIPELINE_DIR/scripts/get-vllm-pod-info.sh"
oc get pods -n "$NAMESPACE"


#========================================
# 6. WAIT FOR POD & TEST API
#========================================
source pod.env
oc wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=600s

echo "===== Testing vLLM endpoint ====="
start_time=$(date +%s)
timeout=200

while true; do
  # Create a temporary pod for testing (if it doesn't exist)
  if ! oc get pod vllm-test-curl -n "$NAMESPACE" &>/dev/null; then
    oc run vllm-test-curl --image=curlimages/curl:latest \
      --restart=Never -n "$NAMESPACE" -- sleep 3600
    oc wait --for=condition=Ready pod/vllm-test-curl -n "$NAMESPACE" --timeout=60s
  fi

  # Execute curl inside the pod and capture response
  response=$(oc exec vllm-test-curl -n "$NAMESPACE" -- \
      curl -sk -w '\n%{http_code}' \
      -H 'Content-Type: application/json' \
      -H "Authorization: Bearer $VLLM_API_KEY" \
      -d "{
          \"model\": \"$MODEL_NAME\",
          \"prompt\": \"Who won the world series in 2020?\",
          \"max_new_tokens\": 100
          }" \
      "$KSVC_URL/v1/completions" 2>&1 || echo -e "\n000")

  # Extract HTTP code from last line
  http_code=$(echo "$response" | tail -1 | tr -d '[:space:]')
  # Extract body from all lines except last
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" == "200" && "$body" == *'"object":"text_completion"'* ]]; then
    echo "✅ API test passed."
    echo "$body" | jq . 2>/dev/null || echo "$body"
    break
  else
    echo "❌ API test failed (HTTP $http_code)"
    echo "$body" | jq . 2>/dev/null || echo "$body"
  fi

  current_time=$(date +%s)
  elapsed=$((current_time - start_time))

  if (( elapsed >= timeout )); then
      echo "⏰ Timeout reached ($timeout seconds). Stopping test."
      oc delete pod vllm-test-curl -n "$NAMESPACE" --ignore-not-found=true
      exit 1
  fi

  sleep 20
done

# Cleanup test pod
oc delete pod vllm-test-curl -n "$NAMESPACE" --ignore-not-found=true


#========================================
# 7. DEPLOY MOCK SERVERS (JWKS & MCP)
#========================================
echo "===== Deploying Mock Servers ====="

# Navigate to repo root to access server scripts
REPO_ROOT="$(cd "$PIPELINE_DIR/../../.." && pwd)"

# Create ConfigMaps from server scripts
echo "Creating mock server ConfigMaps..."
oc create configmap mock-jwks-script -n "$NAMESPACE" \
    --from-file=server.py="$REPO_ROOT/tests/e2e/mock_jwks_server/server.py" \
    --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -

oc create configmap mock-mcp-script -n "$NAMESPACE" \
    --from-file=server.py="$REPO_ROOT/tests/e2e/mock_mcp_server/server.py" \
    --dry-run=client -o yaml | oc apply -n "$NAMESPACE" -f -

# Deploy mock server pods and services
echo "Deploying mock-jwks..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/mock-jwks.yaml"

echo "Deploying mock-mcp..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/mock-mcp.yaml"

# Wait for mock servers to be ready
echo "Waiting for mock servers to be ready..."
oc wait pod/mock-jwks pod/mock-mcp \
    -n "$NAMESPACE" --for=condition=Ready --timeout=120s || {
    echo "⚠️  Mock servers not ready, checking status..."
    oc get pods -n "$NAMESPACE" | grep -E "mock-jwks|mock-mcp" || true
    oc describe pod mock-jwks -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    oc describe pod mock-mcp -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    echo "❌ Mock servers failed to become ready"
    exit 1
}
echo "✅ Mock servers deployed"

# Deploy OKP Solr server for RAG tests
echo "Deploying OKP Solr server..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/okp-solr.yaml"

# Check if redhat-registry-pull-secret exists before waiting
if oc get secret redhat-registry-pull-secret -n "$NAMESPACE" &>/dev/null; then
    echo "✅ redhat-registry-pull-secret exists"
else
    echo "❌ WARNING: redhat-registry-pull-secret NOT found - image pull will fail"
    echo "Checking for pull secrets in namespace $NAMESPACE:"
    oc get secrets -n "$NAMESPACE" --field-selector type=kubernetes.io/dockerconfigjson -o name 2>/dev/null || \
        echo "No dockerconfigjson secrets found"
fi

# Wait for OKP Solr to be ready
echo "Waiting for OKP Solr to be ready (180s timeout)..."
echo "Initial pod status:"
oc get pod okp-solr-service -n "$NAMESPACE" || true

if ! oc wait pod/okp-solr-service \
    -n "$NAMESPACE" --for=condition=Ready --timeout=180s; then

    echo "=========================================="
    echo "⚠️  OKP Solr not ready - DETAILED DIAGNOSTICS"
    echo "=========================================="

    echo ""
    echo "=== Pod Status ==="
    oc get pod okp-solr-service -n "$NAMESPACE" -o wide || true

    echo ""
    echo "=== Container State ==="
    oc get pod okp-solr-service -n "$NAMESPACE" \
        -o jsonpath='{.status.containerStatuses[*].state}' | jq '.' || echo "No container status available"

    echo ""
    echo "=== Image Pull Status ==="
    oc get pod okp-solr-service -n "$NAMESPACE" \
        -o jsonpath='{.status.containerStatuses[*].image}' && echo "" || true
    oc get pod okp-solr-service -n "$NAMESPACE" \
        -o jsonpath='{.status.containerStatuses[*].imageID}' && echo "" || true

    echo ""
    echo "=== Pod Events (last 30) ==="
    # Use server-side filtering with a limit to avoid unbounded list calls
    oc get events -n "$NAMESPACE" --sort-by='.lastTimestamp' \
        --field-selector involvedObject.name=okp-solr-service \
        --limit=30 2>/dev/null || echo "No events found for okp-solr-service"

    echo ""
    echo "=== Full Pod Description ==="
    oc describe pod okp-solr-service -n "$NAMESPACE" || true

    echo ""
    echo "=== Red Hat Registry Secret Status ==="
    if oc get secret redhat-registry-pull-secret -n "$NAMESPACE" &>/dev/null; then
        oc get secret redhat-registry-pull-secret -n "$NAMESPACE" -o yaml | grep -A 2 "type:"
    else
        echo "❌ redhat-registry-pull-secret NOT FOUND"
    fi

    echo ""
    echo "=========================================="
    echo "❌ OKP Solr failed to become ready within 180s"
    echo "=========================================="
    exit 1
fi

echo "✅ OKP Solr deployed"

#========================================
# 8. BUILD OGX IMAGE
#========================================
echo "===== Building llama-stack image ====="
LLAMA_STACK_IMAGE="image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/llama-stack-e2e:latest"
export LLAMA_STACK_IMAGE

# Create BuildConfig (idempotent)
oc new-build --name=llama-stack-e2e \
  --binary \
  --strategy=docker \
  --to="llama-stack-e2e:latest" \
  -n "$NAMESPACE" 2>/dev/null || echo "BuildConfig llama-stack-e2e already exists"

# Patch BuildConfig to use deploy/ogx/test.containerfile instead of Dockerfile
oc patch bc llama-stack-e2e -n "$NAMESPACE" --type=json \
  -p '[{"op":"replace","path":"/spec/strategy/dockerStrategy/dockerfilePath","value":"deploy/ogx/test.containerfile"}]' 2>/dev/null || true

# Build from repo root
oc start-build llama-stack-e2e \
  --from-dir="$REPO_ROOT" \
  --follow \
  -n "$NAMESPACE" || { echo "❌ llama-stack image build failed"; exit 1; }

echo "✅ llama-stack image built: $LLAMA_STACK_IMAGE"

# Allow default SA to pull from the internal registry
oc policy add-role-to-user system:image-puller \
  system:serviceaccount:${NAMESPACE}:default \
  -n "$NAMESPACE" 2>/dev/null || true

#========================================
# 9. DEPLOY LIGHTSPEED STACK AND OGX
#========================================
echo "===== Deploying Services ====="

create_secret api-url-secret --from-literal=key="$KSVC_URL"
# Llama run.yaml: vLLM layout (not under server-mode). Lightspeed: single source with GitHub E2E server-mode.
oc create configmap llama-stack-config -n "$NAMESPACE" \
  --from-file="$REPO_ROOT/tests/e2e-prow/rhoai/configs/run.yaml"
oc create configmap lightspeed-stack-config -n "$NAMESPACE" \
  --from-file=lightspeed-stack.yaml="$REPO_ROOT/tests/e2e/configuration/server-mode/lightspeed-stack-rhoai.yaml"

# Create RAG data ConfigMap from the e2e test RAG data
echo "Creating RAG data ConfigMap..."
RAG_DB_PATH="$REPO_ROOT/tests/e2e/rag/kv_store.db"
if [ -f "$RAG_DB_PATH" ]; then
    # Extract vector store ID from kv_store.db using Python (sqlite3 CLI may not be available)
    echo "Extracting vector store ID from kv_store.db..."
    # OGX 1.0 FAISS keys use persistence.namespace prefix, e.g.:
    #   vector_io::faiss:vector_stores:v3::vs_xxx
    export FAISS_VECTOR_STORE_ID=$(python3 -c "
import sqlite3
import re
conn = sqlite3.connect('$RAG_DB_PATH')
cursor = conn.cursor()
cursor.execute(\"SELECT key FROM kvstore WHERE key LIKE 'vector_io::faiss:vector_stores:v%::%' LIMIT 1\")
row = cursor.fetchone()
if row:
    # Extract the vs_xxx ID from the key
    match = re.search(r'(vs_[a-f0-9-]+)', row[0])
    if match:
        print(match.group(1))
conn.close()
" 2>/dev/null || echo "")
    
    if [ -n "$FAISS_VECTOR_STORE_ID" ]; then
        echo "✅ Extracted FAISS_VECTOR_STORE_ID: $FAISS_VECTOR_STORE_ID"
        # Create secret for OGX to use
        create_secret faiss-vector-store-secret --from-literal=id="$FAISS_VECTOR_STORE_ID"
    else
        echo "❌ No vector_store found in $RAG_DB_PATH - FAISS tests will fail!"
    fi

    gzip -c "$RAG_DB_PATH" > /tmp/kv_store.db.gz
    oc create configmap rag-data -n "$NAMESPACE" --from-file=kv_store.db.gz=/tmp/kv_store.db.gz
    rm /tmp/kv_store.db.gz
    echo "✅ RAG data ConfigMap created from $RAG_DB_PATH"
else
    echo "⚠️  No kv_store.db found at $RAG_DB_PATH"
fi

# Agent skills E2E: same fixture docker-compose mounts at /app-root/skills
SKILLS_DIR="$REPO_ROOT/tests/e2e/skills"
if [ -d "$SKILLS_DIR" ]; then
  tar czf /tmp/e2e-skills.tgz -C "$SKILLS_DIR" .
  oc create configmap e2e-skills -n "$NAMESPACE" \
    --from-file=skills.tgz=/tmp/e2e-skills.tgz \
    --dry-run=client -o yaml | oc apply -f -
  rm -f /tmp/e2e-skills.tgz
  echo "✅ e2e-skills ConfigMap created from $SKILLS_DIR"
else
  echo "⚠️  No skills directory at $SKILLS_DIR — skills.feature will fail"
fi

./pipeline-services.sh

echo "--> Waiting for both lightspeed-stack-service and llama-stack-service pods (up to 10 min)..."
for i in $(seq 1 60); do
  lcs_ready=$(oc get pod lightspeed-stack-service -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
  llama_ready=$(oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

  if [[ "$lcs_ready" == "True" ]] && [[ "$llama_ready" == "True" ]]; then
    echo "✅ Both service pods are ready after $(( i * 10 ))s"
    break
  fi

  if [ $((i % 6)) -eq 0 ]; then
    lcs_status=$(oc get pod lightspeed-stack-service -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
    llama_status=$(oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
    echo "[$(( i * 10 ))s] lightspeed-stack: $lcs_status ($lcs_ready), llama-stack: $llama_status ($llama_ready)"
  fi

  if [ $i -eq 60 ]; then
    echo ""
    echo "❌ One or both service pods failed to become ready within 600s timeout"
    echo ""
    echo "DEBUG: Pod status:"
    oc get pods -n "$NAMESPACE" -o wide || true
    echo ""
    echo "DEBUG: lightspeed-stack-service description:"
    oc describe pod lightspeed-stack-service -n "$NAMESPACE" || true
    echo ""
    echo "DEBUG: llama-stack-service description:"
    oc describe pod llama-stack-service -n "$NAMESPACE" || true
    echo ""
    echo "DEBUG: lightspeed-stack-service logs:"
    oc logs lightspeed-stack-service -n "$NAMESPACE" --tail=100 || true
    echo ""
    echo "DEBUG: llama-stack-service logs:"
    oc logs llama-stack-service -n "$NAMESPACE" --tail=100 || true
    echo ""
    echo "DEBUG: Recent events in namespace:"
    oc get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -20 || true
    exit 1
  fi
  sleep 10
done

oc get pods -n "$NAMESPACE"

echo "logs lightspeed"
oc logs lightspeed-stack-service -n "$NAMESPACE" || true
echo "logs llama"
oc logs llama-stack-service -n "$NAMESPACE" || true

oc describe pod lightspeed-stack-service -n "$NAMESPACE" || true
oc describe pod llama-stack-service -n "$NAMESPACE" || true


#========================================
# 9. EXPOSE SERVICE & START PORT-FORWARD
#========================================
# Export PID file paths so e2e-ops.sh can find and kill stale port-forwards
# during test-triggered pod restarts (matches pipeline-konflux.sh).
export E2E_LSC_PORT_FORWARD_PID_FILE="${E2E_LSC_PORT_FORWARD_PID_FILE:-/tmp/e2e-lightspeed-port-forward.pid}"
export E2E_LLAMA_PORT_FORWARD_PID_FILE="${E2E_LLAMA_PORT_FORWARD_PID_FILE:-/tmp/e2e-llama-port-forward.pid}"
export E2E_JWKS_PORT_FORWARD_PID_FILE="${E2E_JWKS_PORT_FORWARD_PID_FILE:-/tmp/e2e-jwks-port-forward.pid}"
export E2E_OKP_PORT_FORWARD_PID_FILE="${E2E_OKP_PORT_FORWARD_PID_FILE:-/tmp/e2e-okp-port-forward.pid}"
rm -f "$E2E_LSC_PORT_FORWARD_PID_FILE"
rm -f "$E2E_LLAMA_PORT_FORWARD_PID_FILE"
rm -f "$E2E_JWKS_PORT_FORWARD_PID_FILE"
rm -f "$E2E_OKP_PORT_FORWARD_PID_FILE"

oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n $NAMESPACE

oc expose pod lightspeed-stack-service \
  --name=lightspeed-stack-service-svc \
  --port=8080 \
  --type=ClusterIP \
  -n $NAMESPACE

# Kill any existing processes on ports 8080, 8000, 8321, and 8081 (lsof may be missing in minimal images)
echo "Checking for existing processes on ports 8080, 8000, 8321, and 8081..."
if command -v lsof >/dev/null 2>&1; then
    lsof -ti:8080 | xargs kill -9 2>/dev/null || true
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:8321 | xargs kill -9 2>/dev/null || true
    lsof -ti:8081 | xargs kill -9 2>/dev/null || true
elif command -v fuser >/dev/null 2>&1; then
    fuser -k 8080/tcp 2>/dev/null || true
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 8321/tcp 2>/dev/null || true
    fuser -k 8081/tcp 2>/dev/null || true
fi

# Start port-forward for lightspeed-stack
echo "Starting port-forward for lightspeed-stack..."
oc port-forward svc/lightspeed-stack-service-svc 8080:8080 -n $NAMESPACE &
PF_LCS_PID=$!
echo "$PF_LCS_PID" >"$E2E_LSC_PORT_FORWARD_PID_FILE"

# Start port-forward for mock-jwks (needed for RBAC tests to get tokens)
echo "Starting port-forward for mock-jwks..."
oc port-forward svc/mock-jwks 8000:8000 -n $NAMESPACE &
PF_JWKS_PID=$!
echo "$PF_JWKS_PID" >"$E2E_JWKS_PORT_FORWARD_PID_FILE"

# Behave steps that call OGX directly (MCP toolgroups, shields, disrupt/restore)
# need localhost:8321. Without this forward those tests hit "Connection refused".
echo "Starting port-forward for llama-stack..."
oc port-forward svc/llama-stack-service-svc 8321:8321 -n $NAMESPACE &
PF_LLAMA_PID=$!
echo "$PF_LLAMA_PID" >"$E2E_LLAMA_PORT_FORWARD_PID_FILE"

# Start port-forward for OKP Solr (RAG tests)
echo "Starting port-forward for OKP Solr..."
oc port-forward svc/okp-solr-service-svc 8081:8080 -n $NAMESPACE &
PF_OKP_PID=$!
echo "$PF_OKP_PID" >"$E2E_OKP_PORT_FORWARD_PID_FILE"

# Wait for port-forward to be usable (app may not be listening immediately; port-forward can drop)
echo "Waiting for port-forward to lightspeed-stack to be ready..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
    echo "✅ Port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to lightspeed-stack never became ready (3 min)"
    echo ""
    echo "DEBUG: lightspeed-stack-service logs:"
    oc logs lightspeed-stack-service -n "$NAMESPACE" --tail=100 || true
    echo ""
    echo "DEBUG: llama-stack-service logs:"
    oc logs llama-stack-service -n "$NAMESPACE" --tail=100 || true
    echo ""
    echo "DEBUG: Pod status:"
    oc get pods -n "$NAMESPACE" -o wide || true
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    kill $PF_OKP_PID 2>/dev/null || true
    exit 1
  fi
  # If port-forward process died, restart it (e.g. "connection refused" / "lost connection to pod")
  if ! kill -0 $PF_LCS_PID 2>/dev/null; then
    echo "Port-forward died, restarting (attempt $i)..."
    oc port-forward svc/lightspeed-stack-service-svc 8080:8080 -n $NAMESPACE &
    PF_LCS_PID=$!
    echo "$PF_LCS_PID" >"$E2E_LSC_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

# Wait for OGX port-forward to be usable
echo "Waiting for OGX port-forward (localhost:8321 /v1/health)..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8321/v1/health > /dev/null 2>&1; then
    echo "✅ OGX port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to llama-stack never became healthy (3 min)"
    oc logs llama-stack-service -n "$NAMESPACE" --tail=100 || true
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    kill $PF_OKP_PID 2>/dev/null || true
    exit 1
  fi
  if ! kill -0 $PF_LLAMA_PID 2>/dev/null; then
    echo "Llama port-forward died, restarting (attempt $i)..."
    oc port-forward svc/llama-stack-service-svc 8321:8321 -n $NAMESPACE &
    PF_LLAMA_PID=$!
    echo "$PF_LLAMA_PID" >"$E2E_LLAMA_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

# Wait for OKP Solr port-forward to be usable (non-fatal - OKP is optional)
echo "Waiting for OKP Solr port-forward (localhost:8081 /solr)..."
for i in $(seq 1 24); do
  if curl -sf --max-time 5 http://localhost:8081/solr > /dev/null 2>&1; then
    echo "✅ OKP Solr port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 24 ]; then
    echo "⚠️  Port-forward to OKP Solr never became healthy (2 min) - OKP RAG tests may fail"
    # Don't exit - OKP is optional, other tests can still run
  fi
  if ! kill -0 $PF_OKP_PID 2>/dev/null; then
    echo "OKP port-forward died, restarting (attempt $i)..."
    oc port-forward svc/okp-solr-service-svc 8081:8080 -n $NAMESPACE &
    PF_OKP_PID=$!
    echo "$PF_OKP_PID" >"$E2E_OKP_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

export E2E_LSC_HOSTNAME="localhost"
export E2E_JWKS_HOSTNAME="localhost"
export E2E_DEFAULT_MODEL_OVERRIDE="$MODEL_NAME"
export E2E_DEFAULT_PROVIDER_OVERRIDE="vllm"
export E2E_OKP_URL="http://localhost:8081"
echo "LCS accessible at: http://$E2E_LSC_HOSTNAME:8080"
echo "Mock JWKS accessible at: http://$E2E_JWKS_HOSTNAME:8000"
echo "OGX accessible at: http://localhost:8321"
echo "OKP Solr (RAG tests) at: $E2E_OKP_URL"



#========================================
# 10. RUN TESTS
#========================================
echo "===== Running E2E tests ====="

# Ensure run-tests.sh is executable
chmod +x ./run-tests.sh

# Run tests and cleanup port-forwards. Disable ERR trap so we can capture test exit code and reap
# killed port-forwards without the trap firing (ERR fires on any non-zero exit, not only when set -e would exit).
trap - ERR
set +e
export E2E_EXIT_CODE_FILE="${PIPELINE_DIR}/.e2e_exit_code"
./run-tests.sh
# Read exit code from file so we get the real test result (shell can overwrite $? with "PID Killed" before we use it)
TEST_EXIT_CODE=$(cat "$E2E_EXIT_CODE_FILE" 2>/dev/null || echo 1)
# Kill first so wait doesn't block (if a port-forward is still running, wait would hang)
kill $PF_LCS_PID 2>/dev/null || true
kill $PF_JWKS_PID 2>/dev/null || true
kill $PF_LLAMA_PID 2>/dev/null || true
kill $PF_OKP_PID 2>/dev/null || true
wait $PF_LCS_PID 2>/dev/null || true
wait $PF_JWKS_PID 2>/dev/null || true
wait $PF_LLAMA_PID 2>/dev/null || true
wait $PF_OKP_PID 2>/dev/null || true
rm -f "$E2E_LSC_PORT_FORWARD_PID_FILE" "$E2E_LLAMA_PORT_FORWARD_PID_FILE" "$E2E_JWKS_PORT_FORWARD_PID_FILE" "$E2E_OKP_PORT_FORWARD_PID_FILE"
set -e
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

echo "===== E2E COMPLETE ====="

if [ "${TEST_EXIT_CODE:-1}" -ne 0 ]; then
    echo "❌ E2E tests failed with exit code $TEST_EXIT_CODE"
else
    echo "✅ E2E tests succeeded"
fi

exit $TEST_EXIT_CODE