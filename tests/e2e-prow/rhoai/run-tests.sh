#!/bin/bash
set -e

# Go to repo root (run-tests.sh is in tests/e2e-prow/rhoai/)
cd "$(dirname "$0")/../../.."

# Timestamps to pinpoint where time is spent (e.g. if Prow 2h timeout is hit)
ts() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# Konflux library mode: behave + ConfigMap updates use library-mode YAMLs.
if [[ "${E2E_KONFLUX_E2E:-0}" == "1" ]]; then
  export E2E_DEPLOYMENT_MODE="${E2E_DEPLOYMENT_MODE:-library}"
  export E2E_LIGHTSPEED_CONFIG_DIR="${E2E_LIGHTSPEED_CONFIG_DIR:-tests/e2e/configuration/library-mode}"
fi

# FAISS_VECTOR_STORE_ID should be exported by pipeline.sh or pipeline-konflux.sh
if [ -z "$FAISS_VECTOR_STORE_ID" ]; then
    echo "❌ FAISS_VECTOR_STORE_ID is not set - should be exported by the OpenShift E2E pipeline"
    exit 1
fi

ts "Start run-tests.sh"
echo "Running tests from: $(pwd)"
echo "E2E_LSC_HOSTNAME: $E2E_LSC_HOSTNAME"
echo "E2E_DEPLOYMENT_MODE: ${E2E_DEPLOYMENT_MODE:-server}"
echo "FAISS_VECTOR_STORE_ID: $FAISS_VECTOR_STORE_ID"

# Wait for service to be ready (retry up to 60 seconds)
ts "Start: wait for service"
echo "Waiting for service to be ready..."
for i in $(seq 1 12); do
    if curl -sf http://$E2E_LSC_HOSTNAME:8080/v1/models > /dev/null 2>&1; then
        echo "✅ Service is responding"
        break
    fi
    if [ $i -eq 12 ]; then
        echo "❌ Basic connectivity failed after 60 seconds"
        exit 1
    fi
    echo "  Attempt $i/12 - service not ready, waiting 5s..."
    sleep 5
done
ts "End: wait for service"

ts "Start: ensure uv is available"
echo "Installing test dependencies..."
if command -v uv >/dev/null 2>&1; then
  echo "uv already on PATH"
elif command -v pip >/dev/null 2>&1; then
  pip install uv
elif command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install --user uv
  export PATH="${HOME}/.local/bin:${PATH}"
else
  echo "Installing uv via astral.sh (no pip in image)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi
command -v uv >/dev/null 2>&1 || { echo "❌ uv not available after install"; exit 1; }
ts "End: ensure uv is available"

ts "Start: uv sync"
# dev group provides behave (Makefile test-e2e uses uv run behave)
uv sync --group dev
ts "End: uv sync"

ts "Start: e2e test-e2e"
echo "Running e2e test suite..."
set +e
# Makefile target is: uv run behave ... (Konflux/ubi-minimal often has no make)
if command -v make >/dev/null 2>&1; then
  make test-e2e
else
  uv run behave --color --format pretty --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt
fi
BEHAVE_RC=$?
set -e
ts "End: e2e test-e2e"
if [[ -n "${E2E_EXIT_CODE_FILE:-}" ]]; then
  echo "$BEHAVE_RC" >"$E2E_EXIT_CODE_FILE"
fi
exit "$BEHAVE_RC"
