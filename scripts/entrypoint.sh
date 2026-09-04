#!/bin/bash
set -e

# Copy read-only e2e FAISS fixtures to a writable work path (OGX writes on register).
# cp preserves source mode, so chmod so the work copy stays owner-writable.
RAG_SEED_DIR="${RAG_SEED_DIR:-/opt/app-root/src/.llama/storage/.e2e-rag-seed}"
KV_RAG_PATH="${KV_RAG_PATH:-/tmp/e2e-rag-work/kv_store.db}"
PDF_KV_RAG_PATH="${PDF_KV_RAG_PATH:-/tmp/e2e-rag-work/pdf_kv_store.db}"

if [ -d "$RAG_SEED_DIR" ]; then
    mkdir -p "$(dirname "$KV_RAG_PATH")" "$(dirname "$PDF_KV_RAG_PATH")"
    if [ -f "$RAG_SEED_DIR/kv_store.db" ]; then
        cp -f "$RAG_SEED_DIR/kv_store.db" "$KV_RAG_PATH"
        chmod u+w "$KV_RAG_PATH"
    fi
    if [ -f "$RAG_SEED_DIR/pdf_kv_store.db" ]; then
        cp -f "$RAG_SEED_DIR/pdf_kv_store.db" "$PDF_KV_RAG_PATH"
        chmod u+w "$PDF_KV_RAG_PATH"
    fi
fi

# Only use OpenTelemetry instrumentation if explicitly enabled
# Use explicit venv paths to ensure dependencies are found
if [ "${OTEL_SDK_DISABLED:-true}" = "false" ]; then
    exec /app-root/.venv/bin/opentelemetry-instrument /app-root/.venv/bin/python src/lightspeed_stack.py "$@"
else
    exec /app-root/.venv/bin/python src/lightspeed_stack.py "$@"
fi
