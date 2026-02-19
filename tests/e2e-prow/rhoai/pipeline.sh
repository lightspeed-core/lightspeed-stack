#!/bin/bash
set -euo pipefail
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

# Signal to e2e tests that we're running in Prow/OpenShift
export RUNNING_PROW=true

#========================================
# 1. GLOBAL CONFIG
#========================================
NAMESPACE="e2e-rhoai-dsc"
MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# RHOAI llama-stack image
LLAMA_STACK_IMAGE="${LLAMA_STACK_IMAGE:-quay.io/rhoai/odh-llama-stack-core-rhel9:rhoai-3.3}"
echo "Using llama-stack image: $LLAMA_STACK_IMAGE"
export LLAMA_STACK_IMAGE

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
# 3. CREATE NAMESPACE & SECRETS
#========================================
echo "===== Creating namespace & secrets ====="
oc get ns "$NAMESPACE" >/dev/null 2>&1 || oc create namespace "$NAMESPACE"

# Create NFD and NVIDIA namespaces
oc apply -f "$PIPELINE_DIR/manifests/namespaces/nfd.yaml"
oc apply -f "$PIPELINE_DIR/manifests/namespaces/nvidia-operator.yaml"


create_secret() {
    local name=$1; shift
    echo "Creating secret $name..."
    oc create secret generic "$name" "$@" -n "$NAMESPACE" 2>/dev/null || echo "Secret $name exists"
}

create_secret hf-token-secret --from-literal=token="$HUGGING_FACE_HUB_TOKEN"
create_secret vllm-api-key-secret --from-literal=key="$VLLM_API_KEY"

# Create Quay pull secret for llama-stack images
echo "Creating Quay pull secret..."
oc create secret docker-registry quay-lightspeed-pull-secret \
  --docker-server=quay.io \
  --docker-username="$QUAY_ROBOT_NAME" \
  --docker-password="$QUAY_ROBOT_PASSWORD" \
  -n "$NAMESPACE" 2>/dev/null && echo "✅ Quay pull secret created" || echo "⚠️  Secret exists or creation failed"

# Link the secret to default service account for image pulls
oc secrets link default quay-lightspeed-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"


#========================================
# 4. CONFIGMAPS
#========================================
echo "===== Setting up configmaps ====="

curl -sL -o tool_chat_template_llama3.1_json.jinja \
    https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_llama3.1_json.jinja \
    || { echo "❌ Failed to download jinja template"; exit 1; }

oc create configmap vllm-chat-template -n "$NAMESPACE" \
    --from-file=tool_chat_template_llama3.1_json.jinja --dry-run=client -o yaml | oc apply -f -


#========================================
# 5. DEPLOY vLLM
#========================================
echo "===== Deploying vLLM ====="
./pipeline-vllm.sh
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
    --dry-run=client -o yaml | oc apply -f -

oc create configmap mcp-mock-server-script -n "$NAMESPACE" \
    --from-file=server.py="$REPO_ROOT/dev-tools/mcp-mock-server/server.py" \
    --dry-run=client -o yaml | oc apply -f -

# Deploy mock server pods and services
echo "Deploying mock-jwks..."
oc apply -f "$PIPELINE_DIR/manifests/lightspeed/mock-jwks.yaml"

echo "Deploying mcp-mock-server..."
oc apply -f "$PIPELINE_DIR/manifests/lightspeed/mcp-mock-server.yaml"

# Wait for mock servers to be ready
echo "Waiting for mock servers to be ready..."
oc wait pod/mock-jwks pod/mcp-mock-server \
    -n "$NAMESPACE" --for=condition=Ready --timeout=120s || {
    echo "⚠️  Mock servers not ready, checking status..."
    oc get pods -n "$NAMESPACE" | grep -E "mock-jwks|mcp-mock" || true
    oc describe pod mock-jwks -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    oc describe pod mcp-mock-server -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    echo "❌ Mock servers failed to become ready"
    exit 1
}
echo "✅ Mock servers deployed"

#========================================
# 8. DEPLOY LIGHTSPEED STACK AND LLAMA STACK
#========================================
echo "===== Deploying Services ====="

create_secret api-url-secret --from-literal=key="$KSVC_URL"
oc create configmap llama-stack-config -n "$NAMESPACE" --from-file=configs/run.yaml
oc create configmap lightspeed-stack-config -n "$NAMESPACE" --from-file=configs/lightspeed-stack.yaml

# Create RAG data ConfigMap from the e2e test RAG data
echo "Creating RAG data ConfigMap..."
RAG_DB_PATH="$REPO_ROOT/tests/e2e/rag/kv_store.db"
if [ -f "$RAG_DB_PATH" ]; then
    # Extract vector store ID from kv_store.db using Python (sqlite3 CLI may not be available)
    echo "Extracting vector store ID from kv_store.db..."
    # Key format is: vector_stores:v3::vs_xxx or openai_vector_stores:v3::vs_xxx
    export FAISS_VECTOR_STORE_ID=$(python3 -c "
import sqlite3
import re
conn = sqlite3.connect('$RAG_DB_PATH')
cursor = conn.cursor()
cursor.execute(\"SELECT key FROM kvstore WHERE key LIKE 'vector_stores:v%::%' LIMIT 1\")
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
        # Create secret for llama-stack to use
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

./pipeline-services.sh

echo "--> Final wait for both lightspeed-stack-service and llama-stack-service pods..."
if ! oc wait pod/lightspeed-stack-service pod/llama-stack-service \
    -n "$NAMESPACE" --for=condition=Ready --timeout=600s; then
  echo ""
  echo "❌ One or both service pods failed to become ready within timeout"
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
echo "✅ Both service pods are ready"

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
oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n $NAMESPACE

oc expose pod lightspeed-stack-service \
  --name=lightspeed-stack-service-svc \
  --port=8080 \
  --type=ClusterIP \
  -n $NAMESPACE

# Kill any existing processes on ports 8080 and 8000
echo "Checking for existing processes on ports 8080 and 8000..."
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Start port-forward for lightspeed-stack
echo "Starting port-forward for lightspeed-stack..."
oc port-forward svc/lightspeed-stack-service-svc 8080:8080 -n $NAMESPACE &
PF_LCS_PID=$!

# Start port-forward for mock-jwks (needed for RBAC tests to get tokens)
echo "Starting port-forward for mock-jwks..."
oc port-forward svc/mock-jwks 8000:8000 -n $NAMESPACE &
PF_JWKS_PID=$!

sleep 10

export E2E_LSC_HOSTNAME="localhost"
export E2E_JWKS_HOSTNAME="localhost"
echo "LCS accessible at: http://$E2E_LSC_HOSTNAME:8080"
echo "Mock JWKS accessible at: http://$E2E_JWKS_HOSTNAME:8000"



#========================================
# 10. RUN TESTS
#========================================
echo "===== Running E2E tests ====="

# Ensure run-tests.sh is executable
chmod +x ./run-tests.sh

# Disable exit on error to capture test exit code
set +e
./run-tests.sh
TEST_EXIT_CODE=$?
set -e

# Cleanup port-forwards
kill $PF_LCS_PID 2>/dev/null || true
kill $PF_JWKS_PID 2>/dev/null || true

echo "===== E2E COMPLETE ====="

if [ "${TEST_EXIT_CODE:-1}" -ne 0 ]; then
    echo "❌ E2E tests failed with exit code $TEST_EXIT_CODE"
else
    echo "✅ E2E tests succeeded"
fi

exit $TEST_EXIT_CODE