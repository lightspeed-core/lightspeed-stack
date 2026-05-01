#!/bin/bash
# Entrypoint for llama-stack container.
# Produces the run.yaml from lightspeed-stack.yaml then starts llama-stack.
#
# Two modes, auto-detected by the Python CLI (llama_stack_configuration.py):
# - Unified (LCORE-836): `llama_stack.config` present in lightspeed-stack.yaml.
#   The full run.yaml is SYNTHESIZED from the unified block; -i is ignored.
# - Legacy: `run.yaml` is mounted separately and ENRICHED with BYOK RAG / Solr /
#   Azure Entra ID values from lightspeed-stack.yaml.

set -e

INPUT_CONFIG="${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}"
ENRICHED_CONFIG="/opt/app-root/run.yaml"
LIGHTSPEED_CONFIG="${LIGHTSPEED_CONFIG:-/opt/app-root/lightspeed-stack.yaml}"
ENV_FILE="/opt/app-root/.env"

# Run the config producer if lightspeed config exists
if [ -f "$LIGHTSPEED_CONFIG" ]; then
    echo "Preparing llama-stack config from $LIGHTSPEED_CONFIG ..."
    ENRICHMENT_FAILED=0
    python3 /opt/app-root/llama_stack_configuration.py \
        -c "$LIGHTSPEED_CONFIG" \
        -i "$INPUT_CONFIG" \
        -o "$ENRICHED_CONFIG" \
        -e "$ENV_FILE" 2>&1 || ENRICHMENT_FAILED=1

    # Source .env if generated (contains AZURE_API_KEY)
    if [ -f "$ENV_FILE" ]; then
        # shellcheck source=/dev/null
        set -a && . "$ENV_FILE" && set +a
    fi

    if [ -f "$ENRICHED_CONFIG" ] && [ "$ENRICHMENT_FAILED" -eq 0 ]; then
        echo "Using enriched config: $ENRICHED_CONFIG"
        exec llama stack run "$ENRICHED_CONFIG"
    fi
fi

echo "Using original config: $INPUT_CONFIG"
exec llama stack run "$INPUT_CONFIG"
