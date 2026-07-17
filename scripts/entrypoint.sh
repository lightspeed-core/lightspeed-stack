#!/bin/bash
set -e

# Only use OpenTelemetry instrumentation if explicitly enabled
# Use explicit venv paths to ensure dependencies are found
if [ "${OTEL_SDK_DISABLED:-true}" = "false" ]; then
    exec /app-root/.venv/bin/opentelemetry-instrument /app-root/.venv/bin/lightspeed_stack "$@"
else
    exec /app-root/.venv/bin/lightspeed-stack "$@"
fi
