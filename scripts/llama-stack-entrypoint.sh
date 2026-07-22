#!/bin/bash
# Entrypoint for llama-stack container.
# Enriches config with lightspeed dynamic values, then starts llama-stack.

set -e

INPUT_CONFIG="${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}"
ENRICHED_CONFIG="/tmp/enriched-run.yaml"
LIGHTSPEED_CONFIG="${LIGHTSPEED_CONFIG:-/opt/app-root/lightspeed-stack.yaml}"

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
        exec ogx stack run "$ENRICHED_CONFIG"
    fi
fi

echo "Using original config: $INPUT_CONFIG"
exec ogx stack run "$INPUT_CONFIG"
