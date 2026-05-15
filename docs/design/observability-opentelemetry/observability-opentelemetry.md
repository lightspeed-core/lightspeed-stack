# OpenTelemetry tracing in Lightspeed Core

|                          |                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------|
| **Date**                 | 2026-04-08                                                                        |
| **Component**            | lightspeed-stack                                                                  |
| **Authors**              | Andrej Šimurka                                                                    |
| **Feature / Initiative** | [LCORE-322](https://redhat.atlassian.net/browse/LCORE-322)                        |
| **Spike**                | [LCORE-1591](https://redhat.atlassian.net/browse/LCORE-1591)                      |
| **Links**                | —                                                                                 |

This document is the feature specification for observability in Lightspeed Core. It defines how to integrate comprehensive observability and tracing by leveraging the existing OpenTelemetry collector support in the upstream Llama Stack. It covers background, requirements, use cases, and architecture, including areas where multiple approaches are possible and which options are recommended.

---

## OpenTelemetry terminology

- **Trace**: A complete record of a single request as it flows through one or more services. A trace is composed of multiple spans linked together via context propagation.

- **Span**: A timed operation representing a unit of work within a trace (e.g., HTTP request handling, LLM call, RAG retrieval). Spans can be nested to reflect parent–child relationships.

- **Attributes**: Key–value pairs attached to a span that describe its properties (e.g., model ID, token counts). Elapsed time for the operation is represented by the span’s own start/end, not duplicated as a duration attribute. Attributes should be low-cardinality and must not contain sensitive data.

- **Events**: Timestamped annotations within a span that capture significant moments during execution (e.g., `stream.first_delta`, `llm.response.completed`). Events are not for bulk data, but for marking milestones.

---

## Background

### Llama Stack

Llama Stack supports **OpenTelemetry (OTel)** and can export traces and metrics via **OTLP** when configured through standard `OTEL_*` environment variables. 

It provides in-process tracing and metrics via the OTel SDK. When deployed with standard HTTP instrumentation, it can **extract W3C trace context (`traceparent`, `tracestate`) from incoming requests**, allowing spans to attach to an upstream trace when context-providing headers are present.

Configuration of telemetry in Llama Stack is controlled entirely by its own runtime configuration (`OTEL_*` environment variables) and is not managed or influenced by LCORE.

---

### Lightspeed Core

LCORE exposes only Prometheus-compatible metrics via the `/metrics` endpoint. OpenTelemetry is not supported yet: there are no traces, spans, or OTLP metrics, and no configuration exists for enabling or controlling OTEL. All observability today relies entirely on Prometheus scraping.

## What

This feature introduces distributed tracing into LCORE using the OpenTelemetry Python SDK.

It provides:

- Configuration for tracing, including required OTLP export settings (endpoint, protocol, service name) and context propagation controls (incoming and outgoing)
- Automatic HTTP server spans for the FastAPI application
- Manual spans for key execution stages such as LLM calls, RAG processing, tool execution, moderation, and conversation management
- Support for W3C trace context propagation on inbound and outbound HTTP requests
- Proper lifecycle management, including initialization on startup and flushing on shutdown

When tracing is disabled, no spans are created and no tracing-related processing is performed.

---

## Why

Distributed tracing provides visibility into how requests flow through LCORE and its dependencies, enabling operators and developers to understand system behavior in production.

Without tracing, it is difficult to:
- Identify latency bottlenecks across components such as RAG, LLM calls, and tools
- Correlate failures across service boundaries
- Debug issues that span multiple systems, including Llama Stack

By introducing OpenTelemetry-based tracing, LCORE enables:
- End-to-end request tracing: A single trace can cover the full request path—from an upstream gateway, through LCORE processing, to downstream Llama Stack calls—making it possible to see the complete execution timeline in one place.
- Precise latency breakdown: Each major step (e.g., validation, RAG retrieval, LLM invocation, shield moderation) is represented as a span, allowing operators to identify which component is responsible for latency.
- Safe observability by design: Only structured metadata (e.g., IDs, counts) is captured in span attributes; latency is visible from span timing, avoiding exposure of prompts, retrieved content, or other sensitive user data.

This improves observability, reduces time to diagnose issues, and aligns LCORE with modern cloud-native monitoring practices.

---

## Requirements

**R1 – Tracing support**  
LCORE shall support distributed tracing for all requests, producing telemetry compatible with OpenTelemetry.  

**R2 – Configuration**  
Tracing shall be configurable with **global enablement**, which controls whether spans are recorded and exported; **export settings**, including collector endpoint, protocol, and service name; and **context propagation**, with independent toggles for incoming (accepting upstream trace context) and outgoing (injecting trace context to downstream services).  

**R3 – Trace continuation**  
LCORE shall continue an existing distributed trace when upstream trace context is provided.  

**R4 – Trace propagation**  
LCORE shall propagate trace context to downstream services so that all operations within a request are part of a single trace.  

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
The feature shall include documentation describing how to enable tracing, configure required fields and optional environment variables, and verify correct behavior.

---

## Use Cases

**U1**  
As an SRE, I want LCORE to export traces to my OTLP endpoint, so that I can monitor and alert consistently with other services.

**U2**  
As a platform engineer, I want upstream W3C trace context (`traceparent`) honored, so that gateway-started traces continue through LCORE.

**U3**  
As a developer, I want spans for RAG, LLM, tools, and shields, so that I can localize latency and errors without storing full prompts in the trace backend.

**U4**  
As an administrator, I want YAML to pin the OTLP sink basics (endpoint, protocol, service name) and tracing policy, and `OTEL_*` variables for advanced OpenTelemetry options and secrets, so that the deployment manifest stays reviewable without listing every OTel knob in one file.

**U5**  
As a customer, I want LCORE and Llama Stack spans in one trace, so that I can follow a single user action across processes.

---

## Architecture

### Overview

Clients send requests to LCORE, which handles them with FastAPI and manual spans, then may call LLS over HTTP. Both LCORE and LLS export traces via OTLP, optionally through a collector, to the trace backend for monitoring.

End-to-end flow:

```text
Caller ──(HTTP, traceparent/tracestate)──► LCORE FastAPI (server span)
                                                │
                                                ├─► Manual spans: shields, RAG, tools, LLM, streaming
                                                │
                                                └─► AsyncLlamaStackClient ──(inject)──► LLS HTTP ──(extract)──► LLS spans

LCORE: TracerProvider ──► OTLP exporter ──► (optional) Collector ──► trace backend
LLS:   TracerProvider ──► OTLP exporter ──► same endpoint/collector (typical)
```

---

### Step 1: Where the configuration lives (variants)

OpenTelemetry is usually configured entirely via standard environment variables (`OTEL_*`). LCORE, however, is a **configuration-driven** tool, which means that the YAML configuration is typically the source of truth for setup, rather than environment variables. 

There are three approaches for splitting **LCORE YAML** versus standard **`OTEL_*`** variables:

**Option 1 — Config-only (rejected)**  
All tracing and exporter options are placed in YAML, avoiding raw `OTEL_*` entirely.  
**Pros:** Single file for operators who prefer no environment variables.  
**Cons:** OpenTelemetry exposes a large, evolving set of options (headers, TLS, samplers, instrumentor flags, resource attributes, etc.). Modeling all of this in YAML is difficult to maintain. 

**Option 2 — Environment-first**  
All OTLP and SDK wiring comes from `OTEL_*` variables. LCORE YAML only carries tracing policy: enable/disable and context propagation flags.  
**Pros:** Closest to upstream OpenTelemetry tutorials; minimal YAML surface.  
**Cons:** Mandatory (highly recommended) sink identity (endpoint, protocol, service name) is not visible alongside other LCORE settings.   

**Option 3 — Hybrid**  
LCORE YAML contains all **important sink configuration** required/recommended to start tracing, namely: **OTLP endpoint**, **protocol**, and **service name**, plus **propagation** flags. Optional OpenTelemetry settings, such as headers, TLS files, sampling, or instrumentor-only flags, can still be provided via standard `OTEL_*` environment variables. The implementation reads mandatory YAML fields first and exports them explicitly, while honoring additional `OTEL_*` variables for advanced behavior.  
**Pros:** Sink basics are explicit and visible alongside other LCORE settings; advanced OTEL options remain on the standard environment path; avoids fully modeling OpenTelemetry in YAML.  
**Cons:** Operators manage two surfaces; precedence rules between YAML and env vars must be clear.  

**Normative precedence for Option 3:**  
- If `enabled: false`, no TracerProvider or exporters are created; LCORE incurs no tracing overhead regardless of `OTEL_*` or stale YAML values.  
- If `enabled: true`, YAML must contain mandatory **endpoint**, **protocol**, and **service name**; startup should fail if missing.  
- When both YAML and env vars define the same concern, **YAML mandatory fields take precedence** for endpoint, protocol, and service name; `OTEL_*` variables control optional advanced settings (sampling, headers, TLS files, instrumentor-only options).  

**Recommendation:** Option 1 is rejected for maintainability. Option 2 remains viable if LCORE is run with `opentelemetry-instrument`. Option 3 leverages LCORE’s configuration-driven design to ensure mandatory fields are always explicit when tracing is enabled.  
 
---

## Step 2: SDK initialization strategy (variants)

There are two distinct and mutually exclusive ways to initialize OpenTelemetry in LCORE, depending on whether configuration is **environment-driven at process start** or **application-driven at runtime** (see Step 1).

---

## Option 1 — Auto-instrumentation with `opentelemetry-instrument` (OTEL-driven model)

In this approach, the application is started using the OpenTelemetry instrumentation wrapper (`opentelemetry-instrument`). The OpenTelemetry SDK is initialized **before the application code executes**, and configuration must be taken exclusively from `OTEL_*` environment variables. YAML config cannot be used as it is loaded on runtime.

The application does not explicitly configure the SDK; instead, it relies on OpenTelemetry’s default initialization behavior.

### Configuration model:
- All tracing configuration is provided via `OTEL_*` environment variables
- YAML does not participate in SDK initialization
- No runtime configuration merging occurs

### Pros:
- No application-level tracing setup required
- **Automatic instrumentation of supported libraries** (HTTP server/client, frameworks, etc.)
- Fully aligned with standard OpenTelemetry deployment patterns
- Consistent behavior across services using the same environment configuration model

### Cons:
- Requires all configuration to be available at **process start time**
- No ability to use runtime-loaded configuration (e.g., YAML loaded inside the application)
- Limited control over initialization ordering and conditional behavior

### Important constraints:
- SDK initialization happens **outside application lifecycle**
- Only `OTEL_*` environment variables influence behavior
- Application cannot modify tracing configuration at runtime startup
- Any supported advanced OpenTelemetry setting provided via `OTEL_*` environment variables is guaranteed to be picked up and applied

---

## Option 2 — Manual SDK initialization with YAML-driven hybrid configuration

In this approach, OpenTelemetry is initialized explicitly inside the application lifecycle (e.g., FastAPI `lifespan`), after configuration has been loaded.

The configuration model is **YAML-first for mandatory settings**, with optional behavior sourced from `OTEL_*` environment variables where applicable.

### Configuration model:
- YAML provides mandatory tracing configuration:
  - OTLP endpoint  
  - protocol  
  - service name  
- `OTEL_*` environment variables provide optional advanced configuration (e.g., sampling, headers, TLS settings) where supported by the SDK
- Application code explicitly constructs and configures the OpenTelemetry SDK

### Pros:
- Full control over SDK initialization timing (after configuration is loaded)
- Mandatory configuration is explicitly validated and enforced from YAML
- Clear separation between required configuration (YAML) and optional tuning (`OTEL_*`)
- Supports conditional initialization (e.g., tracing enabled/disabled at runtime)

### Cons:
- Requires explicit SDK setup and maintenance in application code
- Some `OTEL_*` variables are not automatically applied and **must be manually resolved** (e.g., sampling)
- More complex than default OpenTelemetry bootstrap approach
- Requires careful implementation to ensure parity with expected OpenTelemetry behaviors

### Important constraints:
- SDK is initialized **after YAML is loaded**
- YAML is the authoritative source for mandatory configuration
- `OTEL_*` variables are applied only where explicitly supported or resolved
- Each worker process initializes its own tracing instance independently

**Recommendation:** The environment-variable-driven approach with automatic instrument is generally the preferred and standard OpenTelemetry deployment model, and it aligns best with upstream conventions and operational simplicity. However, this approach conflicts with the feature requirement that explicitly asks for configurable tracing parameters within LCORE’s own configuration file. **LCORE YAML can still include propagation flags** (`incoming` / `outgoing`).

---

### Step 3: Inbound W3C trace context (variants)

There are two main approaches for handling incoming W3C trace context in LCORE:

- **Always extract:** Every incoming request parses the `traceparent` header automatically. This approach is simple but removes operator control, which may be undesirable in strict or isolated environments.  

- **Config-gated extraction:** The extraction of W3C trace context is controlled via configuration. This approach is **recommended** because it satisfies operational requirements while still allowing operators to ignore foreign traces when necessary. The configuration toggle should default to **enabled** so that trace continuity is preserved unless explicitly disabled.  

**Recommendation:** Implement extraction based on the configuration toggle and use the standard OpenTelemetry W3C propagator with FastAPI instrumentation to continue traces across LCORE. Other propagation formats (such as B3 or vendor-specific headers) are not supported.

---

### Step 4: Outbound propagation to Llama Stack

There are two main approaches for propagating trace context to Llama Stack:

- **Global, config-controlled injection:** The shared HTTP client for LLS calls automatically injects the active trace context into outgoing requests, controlled by a configuration toggle. This approach is **recommended** because it ensures trace continuity across services, centralizes behavior, and is easy to maintain. The configuration toggle should default to **enabled** so that traces are propagated unless explicitly disabled.  

- **Per-request override:** Individual requests can optionally disable or enable trace context injection, overriding the global default. This approach is **rejected** because it adds complexity, is harder to maintain consistently, and has no significant operational benefit compared to the global toggle.  

**Recommendation:** Use global, config-controlled injection on the shared LLS HTTP client, ensuring that LLS is instrumented to extract the context so all spans join the same trace.

In **service mode**, when outbound propagation is enabled, LCORE supplies a custom **`http_client`** (`httpx.AsyncClient`) whose **request** hook injects W3C context from the active span at send time. Static **`default_headers`** would pin one trace for the whole process; the hook matches auto-instrumented HTTP clients without changing generated SDK calls. The following excerpts show the hook, client factory, and `AsyncLlamaStackClient` wiring.

```python
async def _inject_w3c_trace_context(request: httpx.Request) -> None:
    """Attach ``traceparent`` (and related) headers for the current OTel context."""
    from opentelemetry import propagate

    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    for key, value in carrier.items():
        request.headers[key] = value


def llama_stack_httpx_async_client(
    *, base_url: str, timeout: float | httpx.Timeout
) -> httpx.AsyncClient:
    """Build an httpx client that injects W3C trace context on every request."""
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        event_hooks={"request": [_inject_w3c_trace_context]},
    )
```
Enrichment of Llama Stack server-mode client initialization:

```python
        client_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "api_key": api_key,
            "timeout": config.timeout,
        }
        if distributed_tracing_to_llama_enabled() and base_url is not None:
            client_kwargs["http_client"] = llama_stack_httpx_async_client(
                base_url=base_url,
                timeout=config.timeout,
            )
        self._lsc = AsyncLlamaStackClient(**client_kwargs)
```

**Library mode:** This wiring applies only to the **service-mode `AsyncLlamaStackClient`**.  
The **`AsyncLlamaStackAsLibraryClient` is explicitly not covered and does not integrate with LCORE’s tracing hooks**, meaning Llama Stack spans will not reliably appear as child spans within the LCORE trace.

Library client is **not an HTTP client in the usual sense**. It is an in-process library facade over Llama Stack, so there is no LCORE-owned outbound HTTP request path where a per-request W3C inject hook could run.

In library mode, Llama Stack runs **inside the same process boundary**, but it does not participate in LCORE’s outbound instrumentation layer. As a result, trace continuity is not guaranteed and spans are missing from the LCORE trace tree.

**Likely reasons for this limitation:**
- There is **no LCORE-owned outbound HTTP client layer** in library mode where instrumentation hooks can be attached  
- Execution occurs in-process, so propagation depends entirely on **thread-local / context propagation mechanics**, which may not be preserved across async boundaries  
- Trace continuity requires LLS to correctly propagate or reuse **W3C context (`traceparent`)**, which may not be passed or respected in library calls  

---

### Step 5: Export topology

LCORE is responsible for exporting traces via OTLP to a configured endpoint. What happens beyond that endpoint—whether it is a vendor backend (Jaeger, etc.) or an OpenTelemetry Collector—is outside LCORE’s control and is the responsibility of the deployment environment.  

Two common setups exist:

- **Direct OTLP to vendor:** LCORE and Llama Stack send OTLP directly to the tracing backend. This approach works for development or small deployments.  

- **Via an OpenTelemetry Collector:** OTLP is sent to a collector, which handles retries, PII scrubbing, and fan-out to one or more backends. This is **recommended** for production environments. LCORE itself does **not** embed or manage the collector.  

**Recommendation:** Document both options. The normative requirement for LCORE is simply that it successfully exports OTLP from the process; the choice of collector or backend is up to the deployment and operational team.

---

### Step 6: Span filtering

Operators may want to reduce span volume, drop noisy spans, or apply sampling before storage. There are two possible approaches:

- **Filtering in LCORE:** The application could include span group filters in configuration and use a `SpanProcessor` to skip exporting certain spans.  

- **Filtering in the OpenTelemetry Collector or pipeline:** LCORE emits all spans defined in this specification, and filtering, sampling, scrubbing, or tail sampling is applied downstream in the collector or backend. This centralizes policy and avoids per-service configuration drift.  

**Recommendation:** Use the collector or pipeline for span filtering. LCORE does **not** provide per-span or per-span-group enable flags in configuration.

---

### Step 7: Span coverage (fundamental)

This subsection offers recommended candidate spans for LCORE, grouped by functional categories with example attributes and events. These are guidelines to consider during implementation; the actual spans, names, and coverage can be adjusted as needed.

#### 7.1 Shared inference pipeline

Covers core request handling and LLM processing (`POST /v1/query`, `/streaming_query`, `/responses`, `/infer`).

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| MCP OAuth probe | `utils.mcp_oauth_probe.check_mcp_auth` | Validate MCP-related auth before LLS calls | `mcp.auth.probe.ok` | `mcp.auth.probe.finished` |
| Quota gate | `utils.quota.check_tokens_available` | Enforce token quota before work | `quota.check.passed` | — |
| Request validation | Various validators | Validate overrides & attachments | `request.attachments.count`, `request.model.override` | `validation.completed` |
| LLM processing | `utils.responses.*` | Prepare inputs, invoke LLM, post-process | `llm.model.id`, `llm.stream`, `llm.usage.*`, `persist.ok` | `llm.response.completed`, `turn.persisted` |

#### 7.2 Streaming pipeline spans

For streaming endpoints (`/streaming_query`, `/responses`) and async tasks.

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| SSE stream lifecycle | Async generators in `streaming_query.py` / `responses.py` | Bind stream to trace | `stream.sse`, `stream.conversation.id` | `stream.first_delta`, `stream.completed`, `stream.error` |
| MCP tool in stream | Stream parsers / MCP handlers | Tool call visible in stream | `mcp.tool.name`, `mcp.args.byte.len` | `mcp.tool.arguments.done`, `mcp.tool.result.received` |
| Topic summary (background) | `utils.query.update_conversation_topic_summary` | Async topic summary | `topic.summary.task.started` | `topic.summary.task.finished` |

#### 7.3 Catalog, discovery, and MCP auth

Representative spans for listing and retrieving services and tools.

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| List toolgroups | `tools.tools_endpoint_handler` → `client.toolgroups.list` | List LLS toolgroups | `toolgroups.count` | `toolgroups.list.done` |
| List tools per group | `tools.tools_endpoint_handler` → `client.tools.list` | Tools in one toolgroup | `tools.toolgroup.id`, `tools.count` | `tools.list.done` |
| Get RAG | `rags.get_rag_endpoint_handler` | Single RAG metadata | `rags.rag.id` | — |
| Get provider | `providers` get handler | Single provider | `providers.provider.id` | — |

**Other discovery spans (trivial):** List shields, models, providers, service info, effective config, MCP client options (attributes/events similar to above).  

#### 7.4 MCP server administration

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Register MCP server | `mcp_servers.register_mcp_server_handler` → `client.toolgroups.register` | Register dynamic MCP | `mcp.server.name`, `mcp.register.ok` | `mcp.server.registered` |
| List MCP servers | `mcp_servers.list_mcp_servers_handler` | List runtime MCP servers | `mcp.servers.count` | — |
| Delete MCP server | `mcp_servers.delete_mcp_server_handler` | Unregister toolgroup | `mcp.server.name`, `mcp.delete.ok` | `mcp.server.deleted` |

#### 7.5 Conversations, feedback, RLS, A2A, misc

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Conversations CRUD | Handlers & client calls | DB + LLS conversation APIs | `conversation.id`, `conversation.items.count` | `conversation.db.query`, `conversation.lls.call` |
| Feedback | `feedback` module handlers | Submit/query feedback | `feedback.operation`, `feedback.status.code` | — |
| RLS infer | `rlsapi_v1` | Render template / infer request | `rls.template.ok` | `rls.template.rendered` |
| Stream interrupt | `stream_interrupt.*` | Cancel in-flight stream | `interrupt.request_id` | — |
| A2A | `a2a` endpoints | Inbound agent requests | `a2a.rpc.method`, `a2a.request.id` | `a2a.dispatch.start`, `a2a.dispatch.end` |
| Authorized probe | `authorized.*` | Auth check | `authorized.ok` | — |

**Note:** Health, metrics, and root endpoints are noisy and should not have manual spans, but FastAPI will still generate automatic spans. These can be filtered via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` or dropped downstream to keep traces focused on meaningful operations.

#### 7.6 Naming conventions

- **Span names:** `component.operation` (e.g., `rag.retrieve`, `llm.invoke`)  
- **Attributes:** Dot-separated namespaces (e.g., `llm.model.id`, `rag.chunks.count`)  
- **Events:** Short, past-tense, milestone names (e.g., `stream.completed`, `llm.response.finished`)  
- Avoid dynamic/user-provided values to prevent high cardinality.  

---

### Step 8: Prometheus Metrics Extension

LCORE continues to expose **Prometheus-compatible metrics** via the existing `/metrics` endpoint using the native Prometheus Python SDK.  

While OpenTelemetry tracing is introduced for spans, **metrics remain on Prometheus**, ensuring backward compatibility with scraping and alerting setups.  

**Recommendation:**
- Continue using the `/metrics` endpoint for all operational metrics.
- Expand the set of Prometheus metrics as needed to cover additional components (e.g., LLM calls, RAG retrieval, tool execution) as product needs evolve.
- Ensure metrics align with existing naming conventions and maintain low cardinality to avoid high-memory cost in Prometheus servers.

This separation allows spans and metrics to evolve independently while maintaining observability for both traces and Prometheus-native metrics.

---

### Step 9: Failure handling and sensitive data

LCORE must handle tracing errors and sensitive data carefully to avoid impacting users or exposing confidential information.  

- **Export errors on request path:** If tracing fails while processing a user request, the HTTP response should remain unaffected. Tracing errors are ignored for user requests, but logged for operational visibility.  

- **Startup with tracing enabled but exporter misconfigured:** If mandatory export fields are missing, Pydantic validation fails and startup is blocked. If fields are present but the exporter is misconfigured (e.g., unreachable endpoint), no spans are sent and the process continues without tracing; user requests are not impacted. 

- **Span attributes and sensitive data:** Spans must capture metadata only, such as lengths, hashes, IDs, or coarse results. Raw prompts, retrieved content, or other sensitive information must not be included in span attributes.

---

### Step 10: Environment variable customization

LCORE tracing can be further customized using standard OpenTelemetry environment variables. These variables allow operators to configure authentication, sampling, instrumentation, and filtering without modifying YAML configuration.  

**Global kill switch:** `OTEL_SDK_DISABLED=true` disables the OpenTelemetry SDK for the entire process, so no spans are produced or exported even if an OTLP endpoint and other settings are present (YAML or env). Use it when you need telemetry explicitly off at runtime.

Some useful examples include:

- `OTEL_EXPORTER_OTLP_HEADERS` – Set auth or vendor-specific headers; recommended for secrets instead of YAML.  
- `OTEL_EXPORTER_OTLP_CERTIFICATE` and client key paths – Configure mTLS credentials.  
- `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG` – Control sampling behavior for traces.  
- `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` – Comma-separated patterns to skip automatic HTTP server spans, e.g., `/metrics` or `/health`.  
- `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` – Disable noisy or duplicate auto-instrumentation.  

Note: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, and `OTEL_EXPORTER_OTLP_PROTOCOL` are not required, as LCORE reads these from YAML when tracing is enabled.  

For a full list of environment variables and their effects, see the [OpenTelemetry SDK environment variables reference](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/).

---

### Step 11: Deployment files

**`docker-compose.yaml` (LCORE service)**  
- **`environment:`** or **`env_file:`** — set at least **`OTEL_EXPORTER_OTLP_ENDPOINT`**, **`OTEL_SERVICE_NAME`**, **`OTEL_EXPORTER_OTLP_PROTOCOL`**; add **`OTEL_EXPORTER_OTLP_HEADERS`**, **`OTEL_TRACES_SAMPLER`**, **`OTEL_SDK_DISABLED`**, etc. as needed.  

**`Containerfile` (LCORE image)** — change the final **`ENTRYPOINT`** so the wrapper runs first, for example:  
`ENTRYPOINT ["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`  
(instead of invoking `python3.12` alone).

**`scripts/llama-stack-entrypoint.sh` (Llama Stack image)** — the shell entrypoint should become **`exec opentelemetry-instrument llama stack run …`**.

---

### Trigger mechanism

When tracing becomes active depends on the pair of choices in **Step 1** (where configuration lives) and **Step 2** (how the SDK is initialized).

**Hybrid configuration:** The tracing SDK is registered inside the application lifecycle, after YAML is loaded, when the primary configuration toggle and mandatory export settings are satisfied. With tracing enabled, mandatory export fields in LCORE YAML—**endpoint**, **protocol**, and **service name**—must be provided so startup validation passes and OTLP export is correctly wired. Standard **`OTEL_*`** environment variables are then used for sampling, OTLP headers, TLS paths, and other non-mandatory OpenTelemetry options that the implementation merges or resolves alongside YAML.

**OTEL-only design:** When LCORE is run with **`opentelemetry-instrument`**, the SDK is initialized **before** application code runs, and exporter identity and behavior come from **`OTEL_*`** variables. The effective trigger is that the process starts with a coherent set of **`OTEL_*`** values at launch; LCORE YAML is limited to propagation flags.

---

### Storage / data model changes

**None.** Traces are exported; LCORE does not persist span data in application databases.

---

## Configuration

This section describes the OpenTelemetry configuration in LCORE. Tracing is **config-driven**, with mandatory OTLP sink fields in YAML and optional SDK behavior via `OTEL_*` environment variables.

Mandatory `export` block applies when tracing is enabled:

```yaml
observability:
  otel:
    # Following 2 sections corresponds to Hybrid approach from Step 1
    enabled: true                 # global on/off
    export:
      endpoint: "http://otel-collector:4318"
      protocol: "http/protobuf"   # e.g., http/protobuf or grpc
      service: "lightspeed-core"
    propagation:
      incoming: true              # propagate upstream trace context
      outgoing: true              # inject context to Llama Stack
```

**Propagation** is part of this LCORE YAML surface (`incoming` / `outgoing`), not something operators must set only through `OTEL_*` environment variables.

```python
class OpenTelemetryExportConfiguration(ConfigurationBase):
    """Mandatory OTLP sink identity when tracing is enabled."""

    endpoint: str = Field(..., description="OTLP base URL.")
    protocol: str = Field(..., description="Protocol for export, e.g., http/protobuf or grpc.")
    service: str = Field(..., description="Service name displayed in trace backends.")


class OpenTelemetryPropagationConfiguration(ConfigurationBase):
    """Flags controlling trace context propagation."""

    incoming: bool = Field(True, description="Enable upstream trace context extraction")
    outgoing: bool = Field(True, description="Enable propagation to Llama Stack")


class OpenTelemetryConfiguration(ConfigurationBase):
    enabled: bool = Field(False, description="Enable OpenTelemetry tracing")
    export: OpenTelemetryExportConfiguration | None = Field(
        None,
        description="Required when tracing is enabled; validated on startup"
    )
    propagation: OpenTelemetryPropagationConfiguration = Field(
        default_factory=OpenTelemetryPropagationConfiguration
    )
```

### API changes

No **required** change to JSON requests/responses.

---

### Error handling

- **Request path:** Tracing errors do not change HTTP status for the user.
- **Startup / configuration errors:** For hybrid approach, when LCORE tracing is **`enabled: true`**, fail fast or refuse tracing if mandatory YAML **`export`** fields are missing or invalid. For `OTEL_*`-driven design, startup follows OpenTelemetry’s env-based model: invalid or missing exporter/resource **`OTEL_*`** values are an operator concern.

---

### Security considerations

- OTLP **endpoint URL** may live in YAML (**option 3**); **bearer tokens, client keys, and sensitive headers** stay in **`OTEL_*`** and secret mounts, not in committed YAML.
- Span attributes: no raw prompts or retrieved content by default.

---

### Migration / backwards compatibility

- **No tracing by default:** Until operators explicitly turn tracing on—either via LCORE **`observability.otel.enabled`** or by adopting **`opentelemetry-instrument`** with suitable **`OTEL_*`**—existing deployments behave as today (no LCORE-managed OTLP export).
- New dependencies must not alter runtime when tracing is disabled.

---

## New dependencies

- `opentelemetry-distro`
- `opentelemetry-exporter-otlp`
- `opentelemetry-instrumentation-fastapi`

---

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `pyproject.toml` | Add OTel API, SDK, OTLP exporter, FastAPI instrumentor, propagators; pin versions per project policy. |
| `src/models/config.py`, `src/configuration.py` | `OpenTelemetryConfiguration` with propagation flags. |
| `src/client.py` | Inject trace context to LLS when policy requires. |
| `app/endpoints/*.py`, `utils/*.py` | Add manual spans around logical sections of request handlers. |
| `Containerfile` | Add OTel packages so **`opentelemetry-instrument`** is on **`PATH`**; set **`ENTRYPOINT`** to **`["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`**. |
| `scripts/llama-stack-entrypoint.sh` | Prefix **`llama stack run`** with **`opentelemetry-instrument`**. |
| `docker-compose.yaml` | **`environment`** / **`env_file`**: required **`OTEL_*`** exporter fields. |

---

## Open questions

- **Library mode:** Outbound W3C injection is built primarily for **service-mode**; **`AsyncLlamaStackAsLibraryClient` is in-process, not an HTTP client**, so that mechanism does not apply and Llama Stack spans **may not** join the LCORE trace. **What should we do**—treat library mode as unsupported for unified tracing, document limits only, or invest in in-process context alignment (LCORE + LLS contract)?

---

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-10 | **Trigger mechanism:** split hybrid vs `OTEL_*`-driven model. **Step 10:** `OTEL_SDK_DISABLED=true` as process-wide telemetry off. | Align activation story with Step 1/2 variants; document standard env kill switch. |
| 2026-04-10 | Added **Step 11: Deployment files**  | Document concrete deployment changes. |

---

## Appendix A: Jira epics and related tracking

Epics below structure program delivery around observability and related work. **[LCORE-1805](https://redhat.atlassian.net/browse/LCORE-1805)** is included for traceability only: it covers **Prometheus metrics enrichment** and is **outside the scope** of the OpenTelemetry tracing feature defined in this document.

**Epics**

- [LCORE-1789](https://redhat.atlassian.net/browse/LCORE-1789)
- [LCORE-1792](https://redhat.atlassian.net/browse/LCORE-1792)
- [LCORE-1803](https://redhat.atlassian.net/browse/LCORE-1803)

**Related maintenance task**

- [LCORE-1805](https://redhat.atlassian.net/browse/LCORE-1805) — Prometheus metrics enrichment

---

## Appendix B: External references

- [Llama Stack — Telemetry](https://llama-stack.readthedocs.io/en/latest/references/telemetry.html)
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

---
