# OpenTelemetry Tracing Design

|                          |                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------|
| **Date**                 | 2026-04-08                                                                        |
| **Component**            | lightspeed-stack                                                                  |
| **Authors**              | Andrej Šimurka                                                                    |
| **Feature / Initiative** | [LCORE-322](https://redhat.atlassian.net/browse/LCORE-322)                        |
| **Spike**                | [LCORE-2655](https://redhat.atlassian.net/browse/LCORE-2655)                      |
| **Links**                | Spike doc: `docs/design/observability-opentelemetry/observability-opentelemetry-spike.md` |

# What

Request tracing for Lightspeed Core using the OpenTelemetry Python SDK.

It provides:

- OpenTelemetry SDK configuration via standard `OTEL_*` environment variables (process launch)
- Effective OTEL settings visible in the `/config` response (env vars scraped at dump time)
- Automatic HTTP server spans for the FastAPI application
- Manual spans for key execution stages such as LLM calls, RAG processing, tool execution, moderation, and conversation management
- Backend facade spans that represent each external backend interaction as a single LCORE-owned step, hiding backend-internal detail
- Optional W3C trace context extraction on inbound LCORE HTTP requests (gateway continuity; disable with `OTEL_PROPAGATORS=none` environment variable)
- Proper lifecycle management, including initialization on startup and flushing on shutdown

When tracing is off (`OTEL_SDK_DISABLED=true` or exporter env not set), no spans are exported. Application-level manual span creation should remain a no-op or cheap when the SDK is disabled.

# Why

Request tracing provides visibility into how requests flow through LCORE, enabling operators and developers to understand system behavior in production.

Without tracing, it is difficult to:
- Identify latency bottlenecks across components such as RAG, LLM calls, and tools
- Localize errors to a specific stage of request handling
- Debug issues that involve multiple LCORE subsystems and backend calls

By introducing OpenTelemetry-based tracing, LCORE enables:
- **Request-level tracing:** A single trace covers the full LCORE request path—from an optional upstream gateway through validation, backend calls, and response assembly—making it possible to see the complete execution timeline in one place.
- **Precise latency breakdown:** Each major step (e.g., validation, RAG retrieval, LLM invocation, shield moderation) is represented as a span, allowing operators to identify which component is responsible for latency.
- **Backend abstraction:** External backend work appears as facade spans (e.g., `backend.inference`, `backend.rag.retrieve`) whose duration covers the full round-trip, including retries and streaming, without depending on backend trace export or cross-service propagation.
- **Safe observability by design:** Only structured metadata (e.g., IDs, counts) is captured in span attributes; latency is visible from span timing, avoiding exposure of prompts, retrieved content, or other sensitive user data.

This improves observability, reduces time to diagnose issues, and aligns LCORE with modern cloud-native monitoring practices.

# Requirements

**R1 – Tracing support**  
LCORE shall support request tracing for all requests, producing telemetry compatible with OpenTelemetry.  

**R2 – Configuration**  
All tracing settings shall be configured via **`OTEL_*` environment variables** at process launch. LCORE defines no YAML block for tracing. The **`/config` endpoint** shall include effective OTEL settings by reading relevant `OTEL_*` variables from the environment when the configuration is returned (secret values redacted), so operators can inspect the running setup in one place.

**R3 – Trace continuation**  
By default, LCORE shall continue an existing trace when upstream W3C trace context is provided (standard OpenTelemetry propagator behavior). Operators may modify inbound propagation with `OTEL_PROPAGATORS` variable.  

**R4 – Backend facade spans**  
External backend calls shall be represented as single LCORE spans per logical operation. LCORE shall not propagate trace context to external backends.  

**R5 – Coverage**  
Tracing shall cover the full request lifecycle, including key stages such as request handling, LLM calls, RAG retrieval, conversation management, and shield moderation.  

**R6 – Semantic conventions and data handling**  
Spans and their attributes shall follow OpenTelemetry semantic conventions and avoid capturing sensitive or high-volume data (e.g., raw prompts or retrieved content).  

**R7 – Lifecycle management**  
Tracing shall be properly initialized and shut down with the application, ensuring all data is flushed on shutdown.  

**R8 – Multi-worker support**  
Tracing shall function correctly in multi-worker deployments, with each worker maintaining its own tracing context.  

**R9 – Resilience**  
Tracing failures must not impact request processing or user-facing behavior.  

**R10 – Documentation**  
The feature shall include documentation describing how to enable tracing, configure required environment variables, and verify correct behavior.

# Use Cases

**U1**  
As an SRE, I want LCORE to export traces to my OTLP endpoint, so that I can monitor and alert consistently with other services.

**U2**  
As a platform engineer, I want upstream W3C trace context (`traceparent`) honored by default, with the option to disable it via `OTEL_PROPAGATORS` variable, so that gateway-started traces continue through LCORE when needed.

**U3**  
As a developer, I want spans for RAG, LLM, tools, and shields, so that I can localize latency and errors without storing full prompts in the trace backend.

**U4**  
As an administrator, I want tracing configured via standard `OTEL_*` environment variables at deploy time, and reflected in the `/config` response, so I can verify the running setup without hunting through separate deployment manifests.

**U5**  
As an SRE, I want each backend interaction to appear as a single LCORE span showing total latency, without depending on backend trace export or cross-service propagation.

**U6**  
As a developer, I want remote and in-process backend integrations to produce the same trace shape from LCORE's perspective.

# Architecture

## Chosen approach (spike decisions)

| Spike decision | Choice |
|----------------|--------|
| 1 — Configuration | Environment-first (`OTEL_*`; no LCORE YAML block); `/config` scrapes env |
| 2 — SDK initialization | `opentelemetry-instrument` |
| 3 — Inbound trace context | Default W3C propagators; `OTEL_PROPAGATORS=none` to disable |
| 4 — Outbound to backends | Backend facade spans; no outbound propagation |
| 5 — Export topology | OTLP direct or via collector (collector recommended for production) |
| 6 — Span filtering | Collector or pipeline |

## Overview

Clients send requests to LCORE, which handles them with automatic and manual spans. External backend calls are wrapped in facade spans and kept as implementation details. LCORE exports traces via OTLP, optionally through a collector, to the trace backend for monitoring.

## Tracing boundary

LCORE exports a **single coherent trace per inbound request**. External dependencies (inference backends, MCP servers, databases) are **implementation details** behind LCORE-defined spans.

- LCORE does **not** propagate trace context to external backends.
- LCORE does **not** depend on downstream services exporting spans into the same trace.
- Each backend interaction is represented by **one parent span** (e.g., `backend.inference`, `backend.rag.retrieve`, `backend.toolgroups.list`) whose duration covers the full call, including retries and streaming.
- Downstream services may run their own OTel independently; that is an operator concern, not part of the LCORE trace contract.

```
Caller ──(HTTP, optional traceparent/tracestate)──► LCORE FastAPI (server span)
                                                        │
                                                        ├─► validation, conversation management, shields
                                                        ├─► backend.rag.retrieve     (facade; full backend round-trip)
                                                        ├─► backend.inference        (facade; streaming + retries included)
                                                        └─► conversation.db, quota, etc.

LCORE: TracerProvider ──► OTLP exporter ──► (optional) Collector ──► trace backend

External backends: not in the LCORE trace tree; optional separate OTel export
```

## Configuration and SDK initialization

Spike **Decision 1** (environment-first) and **Decision 2** (`opentelemetry-instrument`).

All tracing configuration uses **`OTEL_*` environment variables** at process launch. LCORE defines **no YAML block** for tracing.

LCORE starts with **`opentelemetry-instrument`**, which initializes the SDK from `OTEL_*` before application code runs and auto-instruments supported libraries. The application does not construct or configure the SDK. Use `OTEL_SDK_DISABLED=true` as a process-wide kill switch.

**`/config` visibility:** **`GET /v1/config`** reads relevant `OTEL_*` variables and appends them under `observability.otel` (secrets redacted).

## Inbound W3C trace context

Spike **Decision 3** (default propagators).

Use standard OpenTelemetry propagators via **`OTEL_PROPAGATORS`** (default includes W3C `tracecontext`). FastAPI auto-instrumentation extracts `traceparent` on incoming requests. Applies to **inbound LCORE HTTP requests only**.

To disable inbound propagation, set **`OTEL_PROPAGATORS=none`**.

## Backend facade spans

Spike **Decision 4** (facade spans; no outbound propagation).

External backend interactions are **implementation details** from a tracing perspective. LCORE does **not** inject W3C trace context on outbound backend calls. Wrap each logical backend operation in a single LCORE facade span. The span duration covers the full backend round-trip, including retries, streaming, and any in-process delegation. Remote (HTTP) and in-process backend integrations produce the **same trace shape**.

```python
with tracer.start_as_current_span("backend.inference") as span:
    span.set_attribute("backend.operation", "inference")
    span.set_attribute("llm.model.id", model_id)
    # ... invoke backend client ...
    span.add_event("llm.response.completed")
    span.set_attribute("llm.usage.input_tokens", ...)
```

## Export topology

Spike **Decision 5**.

LCORE exports OTLP only. The destination is configured outside LCORE:

- **Direct OTLP** to any compatible backend (e.g. LangFuse) via `OTEL_EXPORTER_OTLP_ENDPOINT` and headers.
- **Via OpenTelemetry Collector** (recommended for production): fan-out, filtering, and alternative sinks such as file export. The collector owns exporter configuration (including `file` exporters and output paths); LCORE does not implement or manage file-based exports.

## Span filtering

Spike **Decision 6**.

LCORE emits all spans defined in this specification. Filtering, sampling, scrubbing, or tail sampling is applied downstream in the collector or backend. LCORE does **not** provide per-span or per-span-group enable flags.

## Span coverage

Recommended candidate spans, grouped by functional category. Backend-facing rows use **facade spans**: one span per logical backend operation.

### Shared inference pipeline

Covers core request handling and LLM processing (`POST /v1/query`, `/streaming_query`, `/responses`, `/infer`).

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| MCP OAuth probe | `utils.mcp_oauth_probe.check_mcp_auth` | Validate MCP-related auth before backend calls | `mcp.auth.probe.ok` | `mcp.auth.probe.finished` |
| Quota gate | `utils.quota.check_tokens_available` | Enforce token quota before work | `quota.check.passed` | — |
| Request validation | Various validators | Validate overrides & attachments | `request.attachments.count`, `request.model.override` | `validation.completed` |
| LLM processing | `utils.responses.*` | Prepare inputs, invoke backend, post-process | `llm.model.id`, `llm.stream`, `llm.usage.*`, `persist.ok`, `backend.integration` | `llm.response.completed`, `turn.persisted` |

### Streaming pipeline spans

For streaming endpoints (`/streaming_query`, `/responses`) and async tasks.

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| SSE stream lifecycle | Async generators in `streaming_query.py` / `responses.py` | Bind stream to trace | `stream.sse`, `stream.conversation.id` | `stream.first_delta`, `stream.completed`, `stream.error` |
| MCP tool in stream | Stream parsers / MCP handlers | Tool call visible in stream | `mcp.tool.name`, `mcp.args.byte.len` | `mcp.tool.arguments.done`, `mcp.tool.result.received` |
| Topic summary (background) | `utils.query.update_conversation_topic_summary` | Async topic summary | `topic.summary.task.started` | `topic.summary.task.finished` |

### Catalog, discovery, and MCP auth

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| List toolgroups | `tools.tools_endpoint_handler` | List backend toolgroups | `toolgroups.count`, `backend.operation` | `toolgroups.list.done` |
| List tools per group | `tools.tools_endpoint_handler` | Tools in one toolgroup | `tools.toolgroup.id`, `tools.count`, `backend.operation` | `tools.list.done` |
| Get RAG | `rags.get_rag_endpoint_handler` | Single RAG metadata | `rags.rag.id`, `backend.operation` | — |
| Get provider | `providers` get handler | Single provider | `providers.provider.id`, `backend.operation` | — |

**Other discovery spans (trivial):** List shields, models, providers, service info, effective config, MCP client options (attributes/events similar to above).

### MCP server administration

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Register MCP server | `mcp_servers.register_mcp_server_handler` | Register dynamic MCP | `mcp.server.name`, `mcp.register.ok`, `backend.operation` | `mcp.server.registered` |
| List MCP servers | `mcp_servers.list_mcp_servers_handler` | List runtime MCP servers | `mcp.servers.count` | — |
| Delete MCP server | `mcp_servers.delete_mcp_server_handler` | Unregister toolgroup | `mcp.server.name`, `mcp.delete.ok`, `backend.operation` | `mcp.server.deleted` |

### Conversations, feedback, RLS, A2A, misc

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Conversations CRUD | Handlers & backend client calls | DB + backend conversation APIs | `conversation.id`, `conversation.items.count`, `backend.operation` | `conversation.db.query`, `conversation.backend.call` |
| Feedback | `feedback` module handlers | Submit/query feedback | `feedback.operation`, `feedback.status.code` | — |
| RLS infer | `rlsapi_v1` | Render template / infer request | `rls.template.ok` | `rls.template.rendered` |
| Stream interrupt | `stream_interrupt.*` | Cancel in-flight stream | `interrupt.request_id` | — |
| A2A | `a2a` endpoints | Inbound agent requests | `a2a.rpc.method`, `a2a.request.id` | `a2a.dispatch.start`, `a2a.dispatch.end` |
| Authorized probe | `authorized.*` | Auth check | `authorized.ok` | — |

Health, metrics, and root endpoints are noisy and should not have manual spans, but FastAPI will still generate automatic spans. These can be filtered via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` or dropped downstream.

### Naming conventions

- **Span names:** `component.operation` (e.g., `rag.retrieve`, `llm.invoke`, `backend.inference`)  
- **Attributes:** Dot-separated namespaces (e.g., `llm.model.id`, `rag.chunks.count`, `backend.operation`)  
- **Events:** Short, past-tense, milestone names (e.g., `stream.completed`, `llm.response.finished`)  
- Avoid dynamic/user-provided values to prevent high cardinality.

## Prometheus metrics

LCORE continues to expose **Prometheus-compatible metrics** via `/metrics`. While OpenTelemetry tracing is introduced for spans, **metrics remain on Prometheus**.

- Continue using `/metrics` for all operational metrics.
- Expand Prometheus metrics as product needs evolve.
- Maintain low cardinality in metric labels.

## Failure handling and sensitive data

- **Export errors on request path:** Tracing failures do not affect the HTTP response; errors are logged.
- **Misconfigured exporter:** Missing or invalid `OTEL_*` exporter settings mean spans are not exported; user requests are not impacted. Operator/deployment concern, not a startup failure.
- **Span attributes:** Metadata only (lengths, hashes, IDs, coarse results). No raw prompts or retrieved content.

## Environment variables

All tracing SDK configuration uses standard OpenTelemetry environment variables at process launch.

**Global kill switch:** `OTEL_SDK_DISABLED=true`

**Required for export (typical):**

- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_SERVICE_NAME`

**Common optional settings:**

- `OTEL_EXPORTER_OTLP_HEADERS` — secrets; redacted in `/config`
- `OTEL_EXPORTER_OTLP_CERTIFICATE` and client key paths — mTLS
- `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG`
- `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS`
- `OTEL_PROPAGATORS` — use `none` to disable W3C extraction
- `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS`

See the [OpenTelemetry SDK environment variables reference](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/).

## Deployment

**`docker-compose.yaml` (LCORE service)** — set `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_PROTOCOL`; add headers, sampler, `OTEL_SDK_DISABLED`, etc. as needed via `environment` / `env_file`.

**`Containerfile` (LCORE image)** —  
`ENTRYPOINT ["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`

## Trigger mechanism

Tracing is active when the process starts with **`opentelemetry-instrument`** and a coherent set of **`OTEL_*`** values (unless `OTEL_SDK_DISABLED=true`). The SDK and propagators are fully configured from the environment at process launch; LCORE YAML plays no role.

## Storage / data model changes

**None.** Traces are exported; LCORE does not persist span data in application databases.

# Configuration

LCORE defines **no YAML block** for OpenTelemetry. All tracing settings are **`OTEL_*` environment variables**, set at deploy time. See Architecture → Environment variables.

## `/config` response enrichment

When **`GET /v1/config`** returns the effective configuration, the handler shall append scraped `OTEL_*` values under `observability.otel`:

```json
{
  "observability": {
    "otel": {
      "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4318",
      "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
      "OTEL_SERVICE_NAME": "lightspeed-core",
      "OTEL_PROPAGATORS": "tracecontext,baggage",
      "OTEL_EXPORTER_OTLP_HEADERS": "[REDACTED]"
    }
  }
}
```

Values are read from the process environment at request time. Secret-bearing variables shall be redacted. There is no corresponding LCORE config model for tracing.

## API changes

No **required** change to JSON requests/responses. The `/config` response gains `observability.otel` as described above.

## Error handling

- **Request path:** Tracing errors do not change HTTP status for the user.
- **Startup:** Invalid or missing `OTEL_*` values do not block LCORE startup; they affect export only.

## Security considerations

- OTLP endpoint URL and non-secret `OTEL_*` values may appear in the `/config` response via env scraping.
- Bearer tokens, client keys, and sensitive headers stay in **`OTEL_*`** and secret mounts; redact them in `/config` output.
- Span attributes: no raw prompts or retrieved content by default.

## Migration / backwards compatibility

- **No tracing by default:** Until operators set **`OTEL_*`** exporter variables and use **`opentelemetry-instrument`**, existing deployments behave as today (no OTLP export).
- New dependencies must not alter runtime when the SDK is disabled.

# New dependencies

- `opentelemetry-distro`
- `opentelemetry-exporter-otlp`
- `opentelemetry-instrumentation-fastapi`

# Implementation Suggestions

## Key files and insertion points

| File | What to do |
|------|------------|
| `pyproject.toml` | Add OTel API, SDK, OTLP exporter, FastAPI instrumentor, propagators; pin versions per project policy. |
| `src/app/endpoints/config.py` | Scrape `OTEL_*` env vars into `observability.otel` on `/config` response; redact secrets. |
| `app/endpoints/*.py`, `utils/*.py` | Add manual spans around logical sections of request handlers. |
| `Containerfile` | Add OTel packages; set **`ENTRYPOINT`** to **`["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`**. |
| `docker-compose.yaml` | **`environment`** / **`env_file`**: required **`OTEL_*`** exporter fields. |

# Open Questions

- Which `OTEL_*` variable names are included in the `/config` scrape?


# Appendix A: Jira epics and related tracking

**Epics**

- [LCORE-1788](https://redhat.atlassian.net/browse/LCORE-1788)
- [LCORE-1791](https://redhat.atlassian.net/browse/LCORE-1791)
- [LCORE-1799](https://redhat.atlassian.net/browse/LCORE-1799)

**Related maintenance task**

- [LCORE-1805](https://redhat.atlassian.net/browse/LCORE-1805) — Prometheus metrics enrichment

# Appendix B: External references

- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

See the spike doc for the full environment variables reference link.
