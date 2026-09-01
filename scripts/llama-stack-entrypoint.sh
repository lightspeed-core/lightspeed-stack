#!/bin/bash
# Entrypoint for llama-stack container.
# Enriches config with lightspeed dynamic values, then starts llama-stack.

set -e

INPUT_CONFIG="${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}"
ENRICHED_CONFIG="/tmp/enriched-run.yaml"
LIGHTSPEED_CONFIG="${LIGHTSPEED_CONFIG:-/opt/app-root/lightspeed-stack.yaml}"

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

# Enrich config if lightspeed config exists
if [ -f "$LIGHTSPEED_CONFIG" ]; then
    echo "Enriching llama-stack config..."
    ENRICHMENT_FAILED=0
    /opt/app-root/.venv/bin/python3 /opt/app-root/llama_stack_configuration.py \
        -c "$LIGHTSPEED_CONFIG" \
        -i "$INPUT_CONFIG" \
        -o "$ENRICHED_CONFIG" 2>&1 || ENRICHMENT_FAILED=1

    if [ -f "$ENRICHED_CONFIG" ] && [ "$ENRICHMENT_FAILED" -eq 0 ]; then
        echo "Using enriched config: $ENRICHED_CONFIG"
        # OGX 1.3+ requires TLS unless --insecure is set (e2e/local HTTP).
        exec ogx stack run --insecure "$ENRICHED_CONFIG"
    fi
fi

echo "Using original config: $INPUT_CONFIG"
exec ogx stack run --insecure "$INPUT_CONFIG"
