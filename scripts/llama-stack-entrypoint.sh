#!/bin/bash
# Entrypoint for llama-stack container.
# Enriches config with lightspeed dynamic values, then starts llama-stack.

set -e

INPUT_CONFIG="${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}"
ENRICHED_CONFIG="/tmp/enriched-run.yaml"
LIGHTSPEED_CONFIG="${LIGHTSPEED_CONFIG:-/opt/app-root/lightspeed-stack.yaml}"

# Seed the RAG kvstore into the writable storage volume.
#
# The seed db is mounted read-only from the host (owned by the host user), but
# llama-stack runs as a non-root user and must write to this kvstore at startup
# (the resource registry shares it). Copying it into the storage volume makes
# the runtime db owned by the container user, so it is writable regardless of
# the host UID. See run.yaml -> storage.backends.kv_default.
RAG_SEED_DIR="${RAG_SEED_DIR:-/opt/app-root/rag-seed}"
STORAGE_RAG_DIR="${STORAGE_RAG_DIR:-/opt/app-root/src/.llama/storage/rag}"
if [ -d "$RAG_SEED_DIR" ]; then
    echo "Seeding RAG kvstore from $RAG_SEED_DIR into $STORAGE_RAG_DIR..."
    mkdir -p "$STORAGE_RAG_DIR"
    cp -f "$RAG_SEED_DIR"/*.db "$STORAGE_RAG_DIR"/
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
        exec llama stack run "$ENRICHED_CONFIG"
    fi
fi

echo "Using original config: $INPUT_CONFIG"
exec llama stack run "$INPUT_CONFIG"
