#!/bin/bash
# Konflux / OpenAI integration E2E: Llama Stack run-from-source + tests/e2e/configs/run-ci.yaml.
# Prow (vLLM) workflow uses pipeline.sh unchanged.
set -euo pipefail
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

# Signal to e2e tests that we're running in Prow/OpenShift
export RUNNING_PROW=true
export E2E_KONFLUX_E2E=1

#========================================
# 1. GLOBAL CONFIG
#========================================
QUIET="${QUIET:-0}"
NAMESPACE="${NAMESPACE:-e2e-rhoai-dsc}"
export NAMESPACE
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$PIPELINE_DIR/../../.." && pwd)"
log() { [ "$QUIET" != "1" ] && echo "$@"; }
# Always print progress so Konflux UI shows where we are (short one-liners)
progress() { echo "[e2e] $*"; }

# Lightspeed-stack image (from Konflux SNAPSHOT or default). Llama Stack runs from source in-pod (no image).
LIGHTSPEED_STACK_IMAGE="${LIGHTSPEED_STACK_IMAGE:-quay.io/lightspeed-core/lightspeed-stack:dev-latest}"
log "Using lightspeed-stack image: $LIGHTSPEED_STACK_IMAGE"
export LIGHTSPEED_STACK_IMAGE

#========================================
# 2. ENVIRONMENT SETUP
#========================================
log "===== Setting up environment variables ====="
# Konflux/Tekton: credentials from mounted volumes (paths match .tekton integration pipeline)
if [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -r /var/run/openai/openai-api-key ]]; then
  export OPENAI_API_KEY="$(cat /var/run/openai/openai-api-key)"
fi
if [[ -z "${QUAY_ROBOT_NAME:-}" && -d /var/run/quay-aipcc-name ]]; then
  shopt -s nullglob
  for _f in /var/run/quay-aipcc-name/*; do
    [[ -f "$_f" ]] && export QUAY_ROBOT_NAME="$(cat "$_f")" && break
  done
  shopt -u nullglob
fi
if [[ -z "${QUAY_ROBOT_PASSWORD:-}" && -d /var/run/quay-aipcc-password ]]; then
  shopt -s nullglob
  for _f in /var/run/quay-aipcc-password/*; do
    [[ -f "$_f" ]] && export QUAY_ROBOT_PASSWORD="$(cat "$_f")" && break
  done
  shopt -u nullglob
fi

[[ -n "$QUAY_ROBOT_NAME" ]] && log "✅ QUAY_ROBOT_NAME is set" || { echo "❌ Missing QUAY_ROBOT_NAME"; exit 1; }
[[ -n "$QUAY_ROBOT_PASSWORD" ]] && log "✅ QUAY_ROBOT_PASSWORD is set" || { echo "❌ Missing QUAY_ROBOT_PASSWORD"; exit 1; }
[[ -n "$OPENAI_API_KEY" ]] && log "✅ OPENAI_API_KEY is set" || { echo "❌ Missing OPENAI_API_KEY"; exit 1; }

# Basic info (skip when QUIET to keep Konflux UI focused on test logs)
if [ "$QUIET" != "1" ]; then ls -A || true; oc version; oc whoami; fi

#========================================
# 3. CREATE NAMESPACE & SECRETS
#========================================
progress "Creating namespace and secrets"
oc get ns "$NAMESPACE" >/dev/null 2>&1 || oc create namespace "$NAMESPACE"

create_secret() {
    local name=$1; shift
    log "Creating secret $name..."
    oc create secret generic "$name" "$@" -n "$NAMESPACE" 2>/dev/null || log "Secret $name exists"
}

create_secret openai-api-key-secret --from-literal=key="$OPENAI_API_KEY"

# MCPFileAuth E2E: file at /tmp/mcp-secret-token in LCS pod (docker-compose mounts tests/e2e/secrets/mcp-token)
if [ -f "$REPO_ROOT/tests/e2e/secrets/mcp-token" ]; then
  oc create secret generic mcp-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/mcp-token" \
    --dry-run=client -o yaml | oc apply -f -
  log "✅ mcp-file-auth-token secret applied (MCPFileAuth)"
else
  log "⚠️  $REPO_ROOT/tests/e2e/secrets/mcp-token missing — MCPFileAuth may fail"
fi

if [ -f "$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" ]; then
  oc create secret generic mcp-invalid-file-auth-token -n "$NAMESPACE" \
    --from-file=token="$REPO_ROOT/tests/e2e/secrets/invalid-mcp-token" \
    --dry-run=client -o yaml | oc apply -f -
  log "✅ mcp-invalid-file-auth-token secret applied (InvalidMCPFileAuthConfig)"
else
  log "⚠️  $REPO_ROOT/tests/e2e/secrets/invalid-mcp-token missing — InvalidMCPFileAuth E2E may fail"
fi

# Create Quay pull secret for llama-stack images
log "Creating Quay pull secret..."
oc create secret docker-registry quay-lightspeed-pull-secret \
  --docker-server=quay.io \
  --docker-username="$QUAY_ROBOT_NAME" \
  --docker-password="$QUAY_ROBOT_PASSWORD" \
  -n "$NAMESPACE" 2>/dev/null && log "✅ Quay pull secret created" || log "⚠️  Secret exists or creation failed"

# Link the secret to default service account for image pulls
oc secrets link default quay-lightspeed-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"


#========================================
# 4. DEPLOY MOCK SERVERS (JWKS & MCP)
#========================================
progress "Deploying mock servers (JWKS, MCP)"

# Create ConfigMaps from server scripts (REPO_ROOT set in global config)
log "Creating mock server ConfigMaps..."
oc create configmap mock-jwks-script -n "$NAMESPACE" \
    --from-file=server.py="$REPO_ROOT/tests/e2e/mock_jwks_server/server.py" \
    --dry-run=client -o yaml | oc apply -f -

oc create configmap mock-mcp-script -n "$NAMESPACE" \
    --from-file=server.py="$REPO_ROOT/tests/e2e/mock_mcp_server/server.py" \
    --dry-run=client -o yaml | oc apply -f -

# Deploy mock server pods and services
log "Deploying mock-jwks..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/mock-jwks.yaml"

log "Deploying mock-mcp..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/mock-mcp.yaml"

# Wait for mock servers to be ready
log "Waiting for mock servers to be ready..."
oc wait pod/mock-jwks pod/mock-mcp \
    -n "$NAMESPACE" --for=condition=Ready --timeout=120s || {
    echo "⚠️  Mock servers not ready, checking status..."
    oc get pods -n "$NAMESPACE" | grep -E "mock-jwks|mock-mcp" || true
    oc describe pod mock-jwks -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    oc describe pod mock-mcp -n "$NAMESPACE" 2>/dev/null | tail -20 || true
    echo "❌ Mock servers failed to become ready"
    exit 1
}
log "✅ Mock servers deployed"

#========================================
# 5. DEPLOY LIGHTSPEED STACK AND LLAMA STACK
#========================================
progress "Deploying lightspeed-stack and llama-stack"

# Llama run config: single source with GitHub E2E (tests/e2e/configs/run-ci.yaml).
# Lightspeed stack: same tree as local/docker E2E (tests/e2e/configuration/server-mode).
oc create configmap llama-stack-config -n "$NAMESPACE" \
  --from-file=run.yaml="$REPO_ROOT/tests/e2e/configs/run-ci.yaml" \
  --dry-run=client -o yaml | oc apply -f -
oc create configmap lightspeed-stack-config -n "$NAMESPACE" \
  --from-file=lightspeed-stack.yaml="$REPO_ROOT/tests/e2e/configuration/server-mode/lightspeed-stack.yaml" \
  --dry-run=client -o yaml | oc apply -f -

# Create RAG data ConfigMap from the e2e test RAG data
log "Creating RAG data ConfigMap..."
RAG_DB_PATH="$REPO_ROOT/tests/e2e/rag/kv_store.db"
if [ -f "$RAG_DB_PATH" ]; then
    # Extract vector store ID from kv_store.db using Python (sqlite3 CLI may not be available)
    log "Extracting vector store ID from kv_store.db..."
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
        log "✅ Extracted FAISS_VECTOR_STORE_ID: $FAISS_VECTOR_STORE_ID"
        # Create secret for llama-stack to use
        create_secret faiss-vector-store-secret --from-literal=id="$FAISS_VECTOR_STORE_ID"
    else
        echo "❌ No vector_store found in $RAG_DB_PATH - FAISS tests will fail!"
    fi

    gzip -c "$RAG_DB_PATH" > /tmp/kv_store.db.gz
    oc create configmap rag-data -n "$NAMESPACE" --from-file=kv_store.db.gz=/tmp/kv_store.db.gz
    rm /tmp/kv_store.db.gz
    log "✅ RAG data ConfigMap created from $RAG_DB_PATH"
else
    log "⚠️  No kv_store.db found at $RAG_DB_PATH"
fi

# ConfigMap for Llama Stack run-from-source (init container clones this repo @ this revision)
REPO_URL="${REPO_URL:-$(cd "$REPO_ROOT" && git config --get remote.origin.url 2>/dev/null)}"
REPO_REVISION="${REPO_REVISION:-$(cd "$REPO_ROOT" && git rev-parse HEAD 2>/dev/null)}"
[[ -z "$REPO_URL" ]] && REPO_URL='https://github.com/lightspeed-core/lightspeed-stack.git'
[[ -z "$REPO_REVISION" ]] && REPO_REVISION='main'
oc create configmap llama-stack-source -n "$NAMESPACE" \
  --from-literal=repo_url="$REPO_URL" \
  --from-literal=repo_revision="$REPO_REVISION" \
  --dry-run=client -o yaml | oc apply -f -
log "llama-stack-source ConfigMap: repo @ ${REPO_REVISION}"

"$PIPELINE_DIR/pipeline-services-konflux.sh"

progress "Waiting for lightspeed-stack and llama-stack pods"
if ! oc wait pod/lightspeed-stack-service pod/llama-stack-service \
    -n "$NAMESPACE" --for=condition=Ready --timeout=600s; then
  progress "❌ One or both service pods failed to become ready within timeout"
  exit 1
fi
log "✅ Both service pods are ready"

# Print pod logs with echo so CI/Konflux log capture shows each line (especially when QUIET=1)
e2e_echo_pod_logs() {
  local n="${1:-120}"
  echo "[e2e] ========== lightspeed-stack-service logs (tail $n) =========="
  while IFS= read -r line || [[ -n "$line" ]]; do
    echo "[e2e] $line"
  done < <(oc logs lightspeed-stack-service -n "$NAMESPACE" --tail="$n" 2>&1) || true
  echo "[e2e] ========== llama-stack-service logs (tail $n) =========="
  while IFS= read -r line || [[ -n "$line" ]]; do
    echo "[e2e] $line"
  done < <(oc logs llama-stack-service -n "$NAMESPACE" --tail="$n" 2>&1) || true
}

if [ "$QUIET" = "1" ]; then
  e2e_echo_pod_logs 80
else
  oc get pods -n "$NAMESPACE"
  e2e_echo_pod_logs 200
  echo "[e2e] ========== oc describe lightspeed-stack-service =========="
  oc describe pod lightspeed-stack-service -n "$NAMESPACE" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do echo "[e2e] $line"; done || true
  echo "[e2e] ========== oc describe llama-stack-service =========="
  oc describe pod llama-stack-service -n "$NAMESPACE" 2>&1 | while IFS= read -r line || [[ -n "$line" ]]; do echo "[e2e] $line"; done || true
fi


#========================================
# 6. EXPOSE SERVICE & START PORT-FORWARD
#========================================
# So behave/e2e-ops can kill this listener before rebinding 8080 (restart-lightspeed hooks).
# Debug hook/port churn: export E2E_OPS_VERBOSE=1 before running pipeline.sh
export E2E_LSC_PORT_FORWARD_PID_FILE="${E2E_LSC_PORT_FORWARD_PID_FILE:-/tmp/e2e-lightspeed-port-forward.pid}"
export E2E_LLAMA_PORT_FORWARD_PID_FILE="${E2E_LLAMA_PORT_FORWARD_PID_FILE:-/tmp/e2e-llama-port-forward.pid}"
rm -f "$E2E_LSC_PORT_FORWARD_PID_FILE"
rm -f "$E2E_LLAMA_PORT_FORWARD_PID_FILE"

oc label pod lightspeed-stack-service pod=lightspeed-stack-service -n $NAMESPACE

oc expose pod lightspeed-stack-service \
  --name=lightspeed-stack-service-svc \
  --port=8080 \
  --type=ClusterIP \
  -n $NAMESPACE

# Kill any existing processes on ports 8080 and 8000 (lsof often missing in minimal images)
kill_listeners_on_ports() {
  local p
  for p in "$@"; do
    if command -v lsof >/dev/null 2>&1; then
      lsof -ti:"$p" | xargs kill -9 2>/dev/null || true
    elif command -v fuser >/dev/null 2>&1; then
      fuser -k "${p}/tcp" 2>/dev/null || true
    fi
  done
}
kill_listeners_on_ports 8080 8000 8321

# Start port-forward for lightspeed-stack
progress "Starting port-forward, then E2E tests"
oc port-forward svc/lightspeed-stack-service-svc 8080:8080 -n $NAMESPACE &
PF_LCS_PID=$!
echo "$PF_LCS_PID" >"$E2E_LSC_PORT_FORWARD_PID_FILE"

# Start port-forward for mock-jwks (needed for RBAC tests to get tokens)
log "Starting port-forward for mock-jwks..."
oc port-forward svc/mock-jwks 8000:8000 -n $NAMESPACE &
PF_JWKS_PID=$!

# Behave runs in this shell; pipeline-services-konflux.sh cannot export here. MCP hooks call
# Llama Stack directly — mirror LCS and forward llama-stack-service-svc to localhost:8321.
log "Starting port-forward for llama-stack (MCP / llama_stack_client hooks)..."
oc port-forward svc/llama-stack-service-svc 8321:8321 -n $NAMESPACE &
PF_LLAMA_PID=$!
echo "$PF_LLAMA_PID" >"$E2E_LLAMA_PORT_FORWARD_PID_FILE"

# Wait for port-forward to be usable (app may not be listening immediately; port-forward can drop)
log "Waiting for port-forward to lightspeed-stack to be ready..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
    log "✅ Port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to lightspeed-stack never became ready (3 min)"
    echo "[e2e] ========== diagnostics: pod logs after port-forward timeout =========="
    e2e_echo_pod_logs 250
    echo "[e2e] ========== diagnostics: recent events =========="
    while IFS= read -r line || [[ -n "$line" ]]; do
      echo "[e2e] $line"
    done < <(oc get events -n "$NAMESPACE" --sort-by='.lastTimestamp' 2>&1 | tail -40) || true
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    exit 1
  fi
  # If port-forward process died, restart it (e.g. "connection refused" / "lost connection to pod")
  if ! kill -0 $PF_LCS_PID 2>/dev/null; then
    log "Port-forward died, restarting (attempt $i)..."
    oc port-forward svc/lightspeed-stack-service-svc 8080:8080 -n $NAMESPACE &
    PF_LCS_PID=$!
    echo "$PF_LCS_PID" >"$E2E_LSC_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

log "Waiting for Llama Stack port-forward (localhost:8321 /v1/health)..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8321/v1/health > /dev/null 2>&1; then
    log "✅ Llama Stack port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to llama-stack never became healthy (3 min)"
    e2e_echo_pod_logs 200
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    exit 1
  fi
  if ! kill -0 $PF_LLAMA_PID 2>/dev/null; then
    log "Llama port-forward died, restarting (attempt $i)..."
    oc port-forward svc/llama-stack-service-svc 8321:8321 -n $NAMESPACE &
    PF_LLAMA_PID=$!
    echo "$PF_LLAMA_PID" >"$E2E_LLAMA_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

export E2E_LSC_HOSTNAME="localhost"
export E2E_JWKS_HOSTNAME="localhost"
export E2E_LLAMA_HOSTNAME="localhost"
export E2E_LLAMA_PORT="8321"
log "LCS accessible at: http://$E2E_LSC_HOSTNAME:8080"
log "Mock JWKS accessible at: http://$E2E_JWKS_HOSTNAME:8000"
log "Llama Stack (e2e client hooks) at: http://$E2E_LLAMA_HOSTNAME:$E2E_LLAMA_PORT"



#========================================
# 7. RUN TESTS
#========================================
progress "Running E2E tests"

cd "$PIPELINE_DIR"
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
# Kill first so wait doesn't block (if a port-forward is still running, wait would hang).
# Prefer PID file: hooks may have replaced the LCS forward with a new oc PID.
if [[ -n "${E2E_LSC_PORT_FORWARD_PID_FILE:-}" && -f "$E2E_LSC_PORT_FORWARD_PID_FILE" ]]; then
  read -r _lcs_pf <"$E2E_LSC_PORT_FORWARD_PID_FILE" 2>/dev/null || true
  if [[ "${_lcs_pf:-}" =~ ^[0-9]+$ ]]; then
    kill -9 "$_lcs_pf" 2>/dev/null || true
  fi
  rm -f "$E2E_LSC_PORT_FORWARD_PID_FILE"
fi
if [[ -n "${E2E_LLAMA_PORT_FORWARD_PID_FILE:-}" && -f "$E2E_LLAMA_PORT_FORWARD_PID_FILE" ]]; then
  read -r _ll_pf <"$E2E_LLAMA_PORT_FORWARD_PID_FILE" 2>/dev/null || true
  if [[ "${_ll_pf:-}" =~ ^[0-9]+$ ]]; then
    kill -9 "$_ll_pf" 2>/dev/null || true
  fi
  rm -f "$E2E_LLAMA_PORT_FORWARD_PID_FILE"
fi
kill $PF_LCS_PID 2>/dev/null || true
kill $PF_JWKS_PID 2>/dev/null || true
kill $PF_LLAMA_PID 2>/dev/null || true
wait $PF_LCS_PID 2>/dev/null || true
wait $PF_JWKS_PID 2>/dev/null || true
wait $PF_LLAMA_PID 2>/dev/null || true
set -e
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

progress "E2E complete"
if [ "${TEST_EXIT_CODE:-1}" -ne 0 ]; then
    echo "[e2e] ❌ FAILED (exit code $TEST_EXIT_CODE)"
else
    echo "[e2e] ✅ SUCCESS"
fi

exit $TEST_EXIT_CODE
