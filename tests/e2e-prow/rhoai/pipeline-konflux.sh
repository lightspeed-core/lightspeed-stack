#!/bin/bash
# Konflux integration E2E: OGX run-from-source + configurable inference provider.
# Default: OpenAI (run-ci.yaml). For RHEL AI vLLM: set LLAMA_STACK_CONFIG and LCS_CONFIG env vars.
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

# Lightspeed-stack image (from Konflux SNAPSHOT or default). OGX runs from source in-pod (no image).
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
[[ -n "${OPENAI_API_KEY:-}" ]] && log "✅ OPENAI_API_KEY is set" || { echo "❌ Missing OPENAI_API_KEY"; exit 1; }
if [[ -n "${VLLM_URL:-}" ]]; then
  log "✅ VLLM_URL is set: $VLLM_URL (RHEL AI mode)"
fi

# Basic info (skip when QUIET to keep Konflux UI focused on test logs)
if [ "$QUIET" != "1" ]; then ls -A || true; oc version; oc whoami; fi

#========================================
# 3. CREATE NAMESPACE & SECRETS
#========================================
progress "Creating namespace and secrets"
oc get ns "$NAMESPACE" >/dev/null 2>&1 || oc create namespace "$NAMESPACE"

create_secret() {
    local name=$1; shift
    log "Creating/updating secret $name..."
    # Upsert: a stale FAISS_VECTOR_STORE_ID from a prior run in this namespace
    # would otherwise leave registration/search pointing at the wrong store.
    oc create secret generic "$name" "$@" -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -
}

create_secret openai-api-key-secret --from-literal=key="$OPENAI_API_KEY"
if [[ -n "${VLLM_URL:-}" ]]; then
  create_secret vllm-url-secret --from-literal=key="$VLLM_URL"
  create_secret vllm-api-key-secret --from-literal=key="${VLLM_API_KEY:-}"
  create_secret vllm-model-secret --from-literal=key="${VLLM_MODEL:-meta-llama/Llama-3.2-1B-Instruct}"
fi

# MCPFileAuth E2E: secret mounted at /tmp/mcp-token in LCS pod (same as docker-compose)
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

# Create Quay pull secret for OGX images
log "Creating Quay pull secret..."
oc create secret docker-registry quay-lightspeed-pull-secret \
  --docker-server=quay.io \
  --docker-username="$QUAY_ROBOT_NAME" \
  --docker-password="$QUAY_ROBOT_PASSWORD" \
  -n "$NAMESPACE" 2>/dev/null && log "✅ Quay pull secret created" || log "⚠️  Secret exists or creation failed"

# Link the secret to default service account for image pulls
oc secrets link default quay-lightspeed-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"

# Create Red Hat registry pull secret for OKP images
# Option 1: Use mounted docker-registry secret (preferred - simpler)
if [[ -f /var/run/redhat-registry-pull-secret/.dockerconfigjson ]]; then
  log "Creating Red Hat registry pull secret from mounted docker-registry secret..."

  DOCKERCONFIG_BASE64=$(cat /var/run/redhat-registry-pull-secret/.dockerconfigjson | base64 -w0)

  # Use PipelineRun metadata for ownerReference (provided by Tekton context)
  # This ensures automatic cleanup when the PipelineRun completes
  if [[ -n "${TEKTON_PIPELINERUN_NAME:-}" && -n "${TEKTON_PIPELINERUN_UID:-}" ]]; then
    log "Setting ownerReference to PipelineRun: $TEKTON_PIPELINERUN_NAME (UID: ${TEKTON_PIPELINERUN_UID:0:8}...)"

    # Create secret with ownerReference using YAML (ensures automatic cleanup)
    cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: redhat-registry-pull-secret
  namespace: $NAMESPACE
  ownerReferences:
  - apiVersion: tekton.dev/v1beta1
    kind: PipelineRun
    name: $TEKTON_PIPELINERUN_NAME
    uid: $TEKTON_PIPELINERUN_UID
    controller: false
    blockOwnerDeletion: false
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: $DOCKERCONFIG_BASE64
EOF
    log "✅ Red Hat registry pull secret created with ownerReference"

    # Link to default service account
    oc secrets link default redhat-registry-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"
  else
    # Fallback: create without ownerReference (requires manual cleanup)
    log "⚠️  TEKTON_PIPELINERUN_NAME/UID not set - creating secret without ownerReference"
    log "⚠️  Manual cleanup required after test completion"

    cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: redhat-registry-pull-secret
  namespace: $NAMESPACE
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: $DOCKERCONFIG_BASE64
EOF
    log "✅ Red Hat registry pull secret created (without ownerReference)"
    oc secrets link default redhat-registry-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"
  fi

# Option 2: Fallback to username/password mounted separately (legacy approach)
elif [[ -d /var/run/redhat-registry-username ]] && [[ -d /var/run/redhat-registry-password ]]; then
  log "Creating Red Hat registry pull secret from username/password..."
  REDHAT_USERNAME=""
  REDHAT_PASSWORD=""

  # Read username
  shopt -s nullglob
  for _f in /var/run/redhat-registry-username/*; do
    [[ -f "$_f" ]] && REDHAT_USERNAME="$(cat "$_f")" && break
  done

  # Read password
  for _f in /var/run/redhat-registry-password/*; do
    [[ -f "$_f" ]] && REDHAT_PASSWORD="$(cat "$_f")" && break
  done
  shopt -u nullglob

  if [[ -n "$REDHAT_USERNAME" ]] && [[ -n "$REDHAT_PASSWORD" ]]; then
    # Use PipelineRun metadata for ownerReference (provided by Tekton context)
    if [[ -n "${TEKTON_PIPELINERUN_NAME:-}" && -n "${TEKTON_PIPELINERUN_UID:-}" ]]; then
      log "Setting ownerReference to PipelineRun: $TEKTON_PIPELINERUN_NAME (UID: ${TEKTON_PIPELINERUN_UID:0:8}...)"

      # Create secret with ownerReference (oc handles JSON encoding safely)
      oc create secret docker-registry redhat-registry-pull-secret \
        --docker-server=registry.redhat.io \
        --docker-username="$REDHAT_USERNAME" \
        --docker-password="$REDHAT_PASSWORD" \
        -n "$NAMESPACE" \
        --dry-run=client -o json | \
      jq --arg name "$TEKTON_PIPELINERUN_NAME" --arg uid "$TEKTON_PIPELINERUN_UID" \
        '.metadata.ownerReferences = [{"apiVersion":"tekton.dev/v1beta1","kind":"PipelineRun","name":$name,"uid":$uid,"controller":false,"blockOwnerDeletion":false}]' | \
      oc apply -f -
      log "✅ Red Hat registry pull secret created with ownerReference"
    else
      # Fallback: create without ownerReference
      log "⚠️  TEKTON_PIPELINERUN_NAME/UID not set - creating secret without ownerReference"
      log "⚠️  Manual cleanup required after test completion"

      oc create secret docker-registry redhat-registry-pull-secret \
        --docker-server=registry.redhat.io \
        --docker-username="$REDHAT_USERNAME" \
        --docker-password="$REDHAT_PASSWORD" \
        -n "$NAMESPACE" 2>/dev/null && log "✅ Red Hat registry pull secret created" || log "⚠️  Secret exists or creation failed"
    fi

    # Link to default service account
    oc secrets link default redhat-registry-pull-secret --for=pull -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Secret already linked to default SA"
  else
    log "⚠️  Red Hat registry credentials not found in /var/run - OKP image pull may fail"
  fi
else
  log "⚠️  Red Hat registry credential mounts not found - OKP image pull may fail"
  log "   (This is OK if not testing OKP features)"
fi


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

# Deploy OKP Solr server for RAG tests
log "Deploying OKP Solr server..."
oc apply -n "$NAMESPACE" -f "$PIPELINE_DIR/manifests/lightspeed/okp-solr.yaml"

# Check if redhat-registry-pull-secret exists before waiting
if oc get secret redhat-registry-pull-secret -n "$NAMESPACE" &>/dev/null; then
    log "✅ redhat-registry-pull-secret exists"
else
    echo "❌ WARNING: redhat-registry-pull-secret NOT found - image pull will fail"
    echo "Checking for pull secrets in namespace $NAMESPACE:"
    oc get secrets -n "$NAMESPACE" --field-selector type=kubernetes.io/dockerconfigjson -o name 2>/dev/null || \
        echo "No dockerconfigjson secrets found"
fi

# Wait for OKP Solr to be ready
# Large image (7GB) requires extended timeout for first pull (10-15 min typical)
log "Waiting for OKP Solr to be ready (900s timeout for 7GB image pull)..."
log "Initial pod status:"
oc get pod okp-solr-service -n "$NAMESPACE" || true

if ! oc wait pod/okp-solr-service \
    -n "$NAMESPACE" --for=condition=Ready --timeout=900s; then

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
    echo "❌ OKP Solr failed to become ready within 900s"
    echo "   (7GB image - check node network to registry.redhat.io)"
    echo "=========================================="
    exit 1
fi

log "✅ OKP Solr deployed"

# e2e-tunnel-proxy and e2e-interception-proxy are deployed from proxy.feature steps
# (see tests/e2e/features/steps/proxy.py + e2e-ops deploy-e2e-*-proxy).

#========================================
# 5. DEPLOY LIGHTSPEED STACK AND OGX
#========================================
progress "Deploying lightspeed-stack and llama-stack"

# PVC for OGX app-root: caches dnf/uv/git install so TLS per-scenario pod
# recreates skip the expensive init (~6-15 min → ~1-2 min). Delete first to guarantee
# a fresh checkout for this pipeline revision; re-create immediately so the pod can bind.
log "Recreating llama-stack-app-root PVC (fresh per pipeline run)..."
oc delete pvc llama-stack-app-root -n "$NAMESPACE" --ignore-not-found=true 2>/dev/null || true
cat <<'EOF' | oc apply -n "$NAMESPACE" -f -
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
EOF
log "✅ llama-stack-app-root PVC created"

# Configurable config paths: default to OpenAI, override for RHEL AI / vLLM.
LLAMA_STACK_CONFIG="${LLAMA_STACK_CONFIG:-$REPO_ROOT/tests/e2e/configs/run-ci.yaml}"
LCS_CONFIG="${LCS_CONFIG:-$REPO_ROOT/tests/e2e/configuration/server-mode/lightspeed-stack.yaml}"
log "OGX config: $LLAMA_STACK_CONFIG"
log "LCS config: $LCS_CONFIG"
oc create configmap llama-stack-config -n "$NAMESPACE" \
  --from-file=run.yaml="$LLAMA_STACK_CONFIG" \
  --dry-run=client -o yaml | oc apply -f -
oc create configmap lightspeed-stack-config -n "$NAMESPACE" \
  --from-file=lightspeed-stack.yaml="$LCS_CONFIG" \
  --dry-run=client -o yaml | oc apply -f -

# Create RAG data ConfigMap from the e2e test RAG data
log "Creating RAG data ConfigMap..."
RAG_DB_PATH="$REPO_ROOT/tests/e2e/rag/kv_store.db"
if [ -f "$RAG_DB_PATH" ]; then
    # Extract vector store ID from kv_store.db using Python (sqlite3 CLI may not be available)
    log "Extracting vector store ID from kv_store.db..."
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
        log "✅ Extracted FAISS_VECTOR_STORE_ID: $FAISS_VECTOR_STORE_ID"
        # Create secret for OGX to use
        create_secret faiss-vector-store-secret --from-literal=id="$FAISS_VECTOR_STORE_ID"
    else
        echo "❌ No vector_store found in $RAG_DB_PATH - FAISS tests will fail!"
    fi

    gzip -c "$RAG_DB_PATH" > /tmp/kv_store.db.gz
    # Do not use `oc apply` here: client-side apply stores the full object in
    # metadata.annotations.kubectl.kubernetes.io/last-applied-configuration
    # (256KiB limit). The gzipped FAISS fixture (~800KiB+) overflows that.
    oc delete configmap rag-data -n "$NAMESPACE" --ignore-not-found
    oc create configmap rag-data -n "$NAMESPACE" \
      --from-file=kv_store.db.gz=/tmp/kv_store.db.gz
    rm /tmp/kv_store.db.gz
    log "✅ RAG data ConfigMap created from $RAG_DB_PATH"
else
    log "⚠️  No kv_store.db found at $RAG_DB_PATH"
fi

# Agent skills E2E: same fixture docker-compose mounts at /app-root/skills
SKILLS_DIR="$REPO_ROOT/tests/e2e/skills"
if [ -d "$SKILLS_DIR" ]; then
  tar czf /tmp/e2e-skills.tgz -C "$SKILLS_DIR" .
  oc create configmap e2e-skills -n "$NAMESPACE" \
    --from-file=skills.tgz=/tmp/e2e-skills.tgz \
    --dry-run=client -o yaml | oc apply -f -
  rm -f /tmp/e2e-skills.tgz
  log "✅ e2e-skills ConfigMap created from $SKILLS_DIR"
else
  log "⚠️  No skills directory at $SKILLS_DIR — skills.feature will fail"
fi


# ConfigMap for OGX run-from-source (init container clones this repo @ this revision)
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

progress "Waiting for lightspeed-stack and llama-stack pods (up to 10 min)"
for i in $(seq 1 60); do
  lcs_ready=$(oc get pod lightspeed-stack-service -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
  llama_ready=$(oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")

  if [[ "$lcs_ready" == "True" ]] && [[ "$llama_ready" == "True" ]]; then
    log "✅ Both service pods are ready after $(( i * 10 ))s"
    break
  fi

  if [ $((i % 6)) -eq 0 ]; then
    lcs_status=$(oc get pod lightspeed-stack-service -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
    llama_status=$(oc get pod llama-stack-service -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
    progress "[$(( i * 10 ))s] lightspeed-stack: $lcs_status ($lcs_ready), llama-stack: $llama_status ($llama_ready)"
  fi

  if [ $i -eq 60 ]; then
    progress "❌ One or both service pods failed to become ready within 600s timeout"
    e2e_echo_pod_logs 200
    exit 1
  fi
  sleep 10
done

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
export E2E_OKP_PORT_FORWARD_PID_FILE="${E2E_OKP_PORT_FORWARD_PID_FILE:-/tmp/e2e-okp-port-forward.pid}"
rm -f "$E2E_LSC_PORT_FORWARD_PID_FILE"
rm -f "$E2E_LLAMA_PORT_FORWARD_PID_FILE"
rm -f "$E2E_OKP_PORT_FORWARD_PID_FILE"

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
kill_listeners_on_ports 8080 8000 8321 8081

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
# OGX directly — mirror LCS and forward llama-stack-service-svc to localhost:8321.
log "Starting port-forward for llama-stack (MCP / ogx_client hooks)..."
oc port-forward svc/llama-stack-service-svc 8321:8321 -n $NAMESPACE &
PF_LLAMA_PID=$!
echo "$PF_LLAMA_PID" >"$E2E_LLAMA_PORT_FORWARD_PID_FILE"

# Start port-forward for OKP Solr (RAG tests)
log "Starting port-forward for OKP Solr..."
oc port-forward svc/okp-solr-service-svc 8081:8080 -n $NAMESPACE &
PF_OKP_PID=$!
echo "$PF_OKP_PID" >"$E2E_OKP_PORT_FORWARD_PID_FILE"

# Wait for port-forward to be usable (app may not be listening immediately; port-forward can drop)
log "Waiting for port-forward to lightspeed-stack to be ready..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
    log "✅ Port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to lightspeed-stack never became ready (3 min)" | tee /dev/stderr
    echo "[e2e] ========== diagnostics: pod logs after port-forward timeout ==========" | tee /dev/stderr
    trap - ERR
    set +e
    e2e_echo_pod_logs 250
    echo "[e2e] ========== diagnostics: recent events =========="
    while IFS= read -r line || [[ -n "$line" ]]; do
      echo "[e2e] $line"
    done < <(oc get events -n "$NAMESPACE" --sort-by='.lastTimestamp' 2>&1 | tail -40) || true
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    kill $PF_OKP_PID 2>/dev/null || true
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

log "Waiting for OGX port-forward (localhost:8321 /v1/health)..."
for i in $(seq 1 36); do
  if curl -sf http://localhost:8321/v1/health > /dev/null 2>&1; then
    log "✅ OGX port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 36 ]; then
    echo "❌ Port-forward to llama-stack never became healthy (3 min)" | tee /dev/stderr
    trap - ERR
    set +e
    e2e_echo_pod_logs 250
    kill $PF_LCS_PID 2>/dev/null || true
    kill $PF_JWKS_PID 2>/dev/null || true
    kill $PF_LLAMA_PID 2>/dev/null || true
    kill $PF_OKP_PID 2>/dev/null || true
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

log "Waiting for OKP Solr port-forward (localhost:8081 /solr)..."
for i in $(seq 1 24); do
  if curl -sf --max-time 5 http://localhost:8081/solr > /dev/null 2>&1; then
    log "✅ OKP Solr port-forward ready after $(( i * 5 ))s"
    break
  fi
  if [ $i -eq 24 ]; then
    echo "⚠️  Port-forward to OKP Solr never became healthy (2 min) - OKP RAG tests may fail" | tee /dev/stderr
    # Don't exit - OKP is optional, other tests can still run
  fi
  if ! kill -0 $PF_OKP_PID 2>/dev/null; then
    log "OKP port-forward died, restarting (attempt $i)..."
    oc port-forward svc/okp-solr-service-svc 8081:8080 -n $NAMESPACE &
    PF_OKP_PID=$!
    echo "$PF_OKP_PID" >"$E2E_OKP_PORT_FORWARD_PID_FILE"
  fi
  sleep 5
done

export E2E_LSC_HOSTNAME="localhost"
export E2E_JWKS_HOSTNAME="localhost"
export E2E_LLAMA_HOSTNAME="localhost"
export E2E_LLAMA_PORT="8321"
export E2E_OKP_URL="http://localhost:8081"
# Same pattern as tests/e2e-prow/rhoai/pipeline.sh and .github/workflows/e2e_tests_*.yaml:
# Behave {MODEL}/{PROVIDER} use these when set; avoids wrong fallbacks if /v1/models
# discovery in before_all is empty (matches run-ci.yaml openai + E2E_OPENAI_MODEL).
if [[ -n "${VLLM_URL:-}" ]]; then
  : "${E2E_DEFAULT_PROVIDER_OVERRIDE:=vllm}"
  : "${E2E_DEFAULT_MODEL_OVERRIDE:=${VLLM_MODEL:-meta-llama/Llama-3.2-1B-Instruct}}"
else
  : "${E2E_DEFAULT_PROVIDER_OVERRIDE:=openai}"
  : "${E2E_DEFAULT_MODEL_OVERRIDE:=${E2E_OPENAI_MODEL:-gpt-4o-mini}}"
fi
export E2E_DEFAULT_PROVIDER_OVERRIDE E2E_DEFAULT_MODEL_OVERRIDE
log "LCS accessible at: http://$E2E_LSC_HOSTNAME:8080"
log "Mock JWKS accessible at: http://$E2E_JWKS_HOSTNAME:8000"
log "OGX (e2e client hooks) at: http://$E2E_LLAMA_HOSTNAME:$E2E_LLAMA_PORT"
log "OKP Solr (RAG tests) at: $E2E_OKP_URL"

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
if [[ -n "${E2E_OKP_PORT_FORWARD_PID_FILE:-}" && -f "$E2E_OKP_PORT_FORWARD_PID_FILE" ]]; then
  read -r _okp_pf <"$E2E_OKP_PORT_FORWARD_PID_FILE" 2>/dev/null || true
  if [[ "${_okp_pf:-}" =~ ^[0-9]+$ ]]; then
    kill -9 "$_okp_pf" 2>/dev/null || true
  fi
  rm -f "$E2E_OKP_PORT_FORWARD_PID_FILE"
fi

kill $PF_LCS_PID 2>/dev/null || true
kill $PF_JWKS_PID 2>/dev/null || true
kill $PF_LLAMA_PID 2>/dev/null || true
kill $PF_OKP_PID 2>/dev/null || true
wait $PF_LCS_PID 2>/dev/null || true
wait $PF_JWKS_PID 2>/dev/null || true
wait $PF_LLAMA_PID 2>/dev/null || true
wait $PF_OKP_PID 2>/dev/null || true
set -e
trap 'echo "❌ Pipeline failed at line $LINENO"; exit 1' ERR

progress "E2E complete"
if [ "${TEST_EXIT_CODE:-1}" -ne 0 ]; then
    echo "[e2e] ❌ FAILED (exit code $TEST_EXIT_CODE)"
else
    echo "[e2e] ✅ SUCCESS"
fi

exit $TEST_EXIT_CODE
