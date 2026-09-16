# OpenTelemetry Tracing

LCORE can export request traces to an OTLP endpoint (collector or backend) using the standard OpenTelemetry Python SDK. Tracing is **optional** and **off by default**.

This guide covers how to enable tracing, inspect the effective configuration at runtime, and verify that spans reach your OTLP backend. For architecture, span design, and collector deployment options, see the [OpenTelemetry tracing design](../design/observability-opentelemetry/observability-opentelemetry-design.md).

## Prerequisites

- LCORE runs under **`opentelemetry-instrument`**. The official container image starts the process this way so the SDK initializes from environment variables before application code loads and supported libraries (for example FastAPI) are auto-instrumented.
- Tracing stays **disabled until you set exporter `OTEL_*` variables** at deploy time. Without a coherent exporter configuration, LCORE starts and serves traffic normally; no spans are exported.
- You need a reachable **OTLP endpoint** (OpenTelemetry Collector, Jaeger, Grafana Tempo, vendor backend, or similar). Deploying and operating that endpoint is outside this guide.

## How configuration works

OpenTelemetry is **not configured in LCORE YAML** (`lightspeed-stack.yaml`). There is no `opentelemetry` or `observability` tracing section in the configuration file.

All tracing settings come from standard **`OTEL_*` environment variables** set when the process starts. The SDK reads them at launch; changes require a process restart.

To confirm what the running instance is using, call **`GET /v1/config`**. The response includes an **`observability.otel`** object with the effective `OTEL_*` values scraped from the process environment (secret-bearing values are wrapped in `SecretStr` and appear as `**********`).

## Required environment variables

Set these at minimum to export traces:

| Variable | Description |
|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP receiver URL (for example `http://otel-collector:4318` for HTTP or `http://otel-collector:4317` for gRPC). |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Export protocol. Common values: `http/protobuf` (HTTP, port 4318) or `grpc` (gRPC, port 4317). Must match your collector or backend. |
| `OTEL_SERVICE_NAME` | Service name attached to exported traces (for example `lightspeed-core`). |

## Common optional environment variables

| Variable | Description |
|----------|-------------|
| `OTEL_SDK_DISABLED` | Global kill switch. Set to `true` to disable the SDK and stop export without removing other `OTEL_*` variables. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Comma-separated `key=value` headers for authenticated OTLP export (for example `Authorization=Bearer <token>`). **Treat as a secret**; wrapped as `SecretStr` and shown as `**********` in `/v1/config`. |
| `OTEL_PROPAGATORS` | W3C trace context propagators. Default continues upstream traces via `traceparent`. Set to `none` for standalone LCORE traces that ignore inbound `traceparent`. |
| `OTEL_TRACES_SAMPLER` | Sampling strategy (for example `parentbased_traceidratio`, `always_on`, `always_off`). |
| `OTEL_TRACES_SAMPLER_ARG` | Argument for the chosen sampler (for example `0.1` for 10% sampling with `traceidratio`). |
| `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` | Comma-separated URL patterns to exclude from FastAPI auto-instrumentation (for example `/liveness,/readiness,/metrics`). Reduces noise from health and metrics traffic. |

For the full upstream reference, see the [OpenTelemetry SDK environment variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) documentation.

## Deployment examples

### Docker Compose

Add the required variables to the `lightspeed-stack` service `environment` block (or an `env_file` referenced by the service):

```yaml
services:
  lightspeed-stack:
    image: lightspeed-stack:local
    ports:
      - "8080:8080"
    volumes:
      - ./lightspeed-stack.yaml:/app-root/lightspeed-stack.yaml:ro
    environment:
      # ... existing LCORE variables ...
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"
      OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
      OTEL_SERVICE_NAME: "lightspeed-core"
      # Optional:
      # OTEL_PROPAGATORS: "tracecontext,baggage"
      # OTEL_PYTHON_FASTAPI_EXCLUDED_URLS: "/liveness,/readiness,/metrics"
      # OTEL_EXPORTER_OTLP_HEADERS: "Authorization=Bearer ${OTEL_AUTH_TOKEN}"
```

Restart the service after changing `OTEL_*` values.

## Runtime inspection

`GET /v1/config` requires authentication and the `GET_CONFIG` authorization action in secured deployments. With credentials configured for your environment:

```bash
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "http://localhost:8080/v1/config"
```

The `otel` object is one section inside the full `configuration` payload returned by `/v1/config`. Outline when tracing is enabled:

```json
{
  "configuration": {
    "name": "lightspeed-stack",
    "service": { "..." },
    "ogx": { "..." },
    "authentication": { "..." },
    "authorization": { "..." },
    "inference": { "..." },
    "observability": {
      "otel": {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4318",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_SERVICE_NAME": "lightspeed-core",
        "OTEL_PROPAGATORS": "tracecontext,baggage",
        "OTEL_EXPORTER_OTLP_HEADERS": "**********"
      }
    }
  }
}
```

## Verification

1. **Set `OTEL_*` variables** on the LCORE deployment (required exporter variables at minimum) and **start or restart** LCORE so the process picks them up under `opentelemetry-instrument`.
2. **Confirm configuration** — call `GET /v1/config` and verify `configuration.observability.otel` shows the expected endpoint, protocol, and service name. Confirm sensitive headers appear as `**********` when set (secret values are wrapped in `SecretStr`).
3. **Generate trace traffic** — send an authenticated API request that exercises request handling, for example `POST /v1/query` with a test query.
   Health endpoints (`/liveness`, `/readiness`) also produce automatic FastAPI spans unless excluded via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`.
4. **Confirm export** — in your OTLP collector or trace backend UI, look for spans with `service.name` matching `OTEL_SERVICE_NAME` and a recent timestamp from the test request. Filter by HTTP route or trace ID if your backend supports it.

If steps 1–2 succeed but no spans appear in step 4, check network reachability to `OTEL_EXPORTER_OTLP_ENDPOINT`, protocol/port alignment, collector logs, and any authentication headers.

## Expected behavior and limits

- **Missing or invalid exporter configuration does not block startup.** LCORE starts normally; spans are simply not exported until a valid OTLP configuration is in place.
- **Tracing failures do not change HTTP responses.** Export errors are handled on the observability path and do not alter status codes or response bodies for API clients.
- **LCORE does not propagate trace context to external backends** Inbound W3C `traceparent` continuation is configurable via `OTEL_PROPAGATORS`; outbound propagation to dependencies is not an operator setup step for this feature.
