#!/bin/bash
# Entrypoint for OGX container.
#
# Generates the run configuration from the mounted lightspeed-stack.yaml and
# starts OGX. The Python CLI (ogx_configuration.py) auto-detects the
# configuration shape:
#   - unified mode: the lightspeed config carries a synthesis input (a
#     non-empty inference.providers or vector_store.providers, or a
#     llama_stack.config / ogx.config block). The full run.yaml is synthesized
#     from it — no external run.yaml mount is needed, and $OGX_CONFIG /
#     $LLAMA_STACK_CONFIG is ignored. The shipped default baseline is read from
#     /opt/app-root/data/default_run.yaml.
#   - legacy mode: the mounted run.yaml ($OGX_CONFIG, falling back to
#     $LLAMA_STACK_CONFIG) is enriched with lightspeed dynamic values
#     (BYOK RAG, Solr/OKP, Azure Entra ID).

set -e

INPUT_CONFIG="${OGX_CONFIG:-${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}}"
GENERATED_CONFIG="/tmp/generated-run.yaml"
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

# Generate config (synthesis or enrichment) if lightspeed config exists
if [ -f "$LIGHTSPEED_CONFIG" ]; then
    echo "Generating OGX config from $LIGHTSPEED_CONFIG (mode auto-detected)..."
    GENERATION_FAILED=0
    /opt/app-root/.venv/bin/python3 /opt/app-root/ogx_configuration.py \
        -c "$LIGHTSPEED_CONFIG" \
        -i "$INPUT_CONFIG" \
        -o "$GENERATED_CONFIG" 2>&1 || GENERATION_FAILED=1

    if [ -f "$GENERATED_CONFIG" ] && [ "$GENERATION_FAILED" -eq 0 ]; then
        echo "Using generated config: $GENERATED_CONFIG"
        # OGX 1.3+ requires TLS unless --insecure is set (e2e/local HTTP).
        exec ogx stack run --insecure "$GENERATED_CONFIG"
    fi
fi

# Fallback: run the mounted run.yaml directly. In unified mode there may be
# no run.yaml at all — fail with a clear message instead of a confusing
# file-not-found error.
if [ ! -f "$INPUT_CONFIG" ]; then
    echo "ERROR: config generation failed and no fallback run.yaml exists at $INPUT_CONFIG" >&2
    exit 1
fi

echo "Using original config: $INPUT_CONFIG"
exec ogx stack run --insecure "$INPUT_CONFIG"
