#!/bin/bash
set -e

# Go to repo root (run-tests.sh is in tests/e2e-prow/rhoai/)
cd "$(dirname "$0")/../../.."

# Timestamps to pinpoint where time is spent (e.g. if Prow 2h timeout is hit)
ts() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# FAISS_VECTOR_STORE_ID should be exported by pipeline.sh
if [ -z "$FAISS_VECTOR_STORE_ID" ]; then
    echo "❌ FAISS_VECTOR_STORE_ID is not set - should be exported by pipeline.sh"
    exit 1
fi

ts "Start run-tests.sh"
echo "Running tests from: $(pwd)"
echo "E2E_LSC_HOSTNAME: $E2E_LSC_HOSTNAME"
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

ts "Start: pip install uv"
echo "Installing test dependencies..."
pip install uv
ts "End: pip install uv"

ts "Start: uv sync"
uv sync
ts "End: uv sync"

ts "Start: make test-e2e"
echo "Running e2e test suite..."
make test-e2e
ts "End: make test-e2e"
