#!/bin/bash
# Entrypoint for OGX container.
#
# Generates the run configuration from the mounted lightspeed-stack.yaml and
# starts OGX. The Python CLI (llama_stack_configuration.py) auto-detects the
# configuration shape:
#   - unified mode: the lightspeed config carries a synthesis input (a
#     non-empty inference.providers or vector_store.providers, or a
#     llama_stack.config block). The full run.yaml is synthesized from it —
#     no external run.yaml mount is needed, and $LLAMA_STACK_CONFIG is
#     ignored. The shipped default baseline is read from
#     /opt/app-root/data/default_run.yaml.
#   - legacy mode: the mounted run.yaml ($LLAMA_STACK_CONFIG) is enriched
#     with lightspeed dynamic values (BYOK RAG, Solr/OKP, Azure Entra ID).

set -e

INPUT_CONFIG="${LLAMA_STACK_CONFIG:-/opt/app-root/run.yaml}"
GENERATED_CONFIG="/tmp/generated-run.yaml"
LIGHTSPEED_CONFIG="${LIGHTSPEED_CONFIG:-/opt/app-root/lightspeed-stack.yaml}"

# Generate config (synthesis or enrichment) if lightspeed config exists
if [ -f "$LIGHTSPEED_CONFIG" ]; then
    echo "Generating llama-stack config from $LIGHTSPEED_CONFIG (mode auto-detected)..."
    GENERATION_FAILED=0
    /opt/app-root/.venv/bin/python3 /opt/app-root/llama_stack_configuration.py \
        -c "$LIGHTSPEED_CONFIG" \
        -i "$INPUT_CONFIG" \
        -o "$GENERATED_CONFIG" 2>&1 || GENERATION_FAILED=1

    if [ -f "$GENERATED_CONFIG" ] && [ "$GENERATION_FAILED" -eq 0 ]; then
        echo "Using generated config: $GENERATED_CONFIG"
        exec ogx stack run "$GENERATED_CONFIG"
    fi
fi

# Fallback: run the mounted run.yaml directly. In unified mode there may be
# no run.yaml at all — fail with a clear message instead of a confusing
# llama-stack file-not-found error.
if [ ! -f "$INPUT_CONFIG" ]; then
    echo "ERROR: config generation failed and no fallback run.yaml exists at $INPUT_CONFIG" >&2
    exit 1
fi

echo "Using original config: $INPUT_CONFIG"
exec ogx stack run "$INPUT_CONFIG"
