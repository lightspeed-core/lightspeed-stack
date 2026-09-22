# OpenTelemetry Tracing Design

|                          |                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------|
| **Date**                 | 2026-04-08                                                                        |
| **Component**            | lightspeed-stack                                                                  |
| **Authors**              | Andrej Šimurka                                                                    |
| **Feature / Initiative** | [LCORE-322](https://redhat.atlassian.net/browse/LCORE-322)                        |
| **Spike**                | [LCORE-2655](https://redhat.atlassian.net/browse/LCORE-2655)                      |
| **Links**                | Spike doc: `docs/design/observability-opentelemetry/observability-opentelemetry-spike.md` |

## What

Request tracing for Lightspeed Core using the OpenTelemetry Python SDK.

It provides:

- OpenTelemetry SDK configuration through standard `OTEL_*` environment variables at process startup
- Effective OpenTelemetry settings exposed by the `GET /config` endpoint (environment variables collected on demand and added to the endpoint response)
- Manual spans for key execution stages, following a session → trace → span hierarchy:
    - **Session:** conversation-scoped, associated with the user and environment
    - **Trace:** one per user prompt or model turn
    - **Span:** an ordered pipeline step within a trace, including intent routing, RAG context retrieval, tool execution, response generation, moderation, and conversation management
- Spans generated from LCORE internal summary objects rather than merging backend-exported spans into internal traces
- Configurable option for extraction of W3C trace context from inbound LCORE HTTP requests to preserve trace continuity across gateways
- Proper OpenTelemetry lifecycle management, including SDK initialization at startup and flushing telemetry on shutdown

When tracing is off (`OTEL_SDK_DISABLED=true` or exporter env not set), no spans are exported. Application-level manual span creation should remain a no-op when the SDK is disabled.

## Why

Request tracing provides visibility into how requests flow through LCORE, enabling operators and developers to understand system behavior in production.

Without tracing, it is difficult to:
- Identify latency bottlenecks across components such as RAG, LLM calls, and tools
- Localize errors to a specific stage of request handling
- Debug issues that involve multiple LCORE subsystems and backend calls
- Evaluate product behavior or understand what configurations and setups customers use in production

By introducing OpenTelemetry-based tracing, LCORE enables:
- **Request-level tracing:** A single trace covers the full LCORE request path—from an optional upstream gateway through validation, backend calls, and response assembly—making it possible to see the complete execution timeline in one place.
- **Precise latency breakdown:** Each major step (e.g., validation, RAG retrieval, LLM invocation, shield moderation) is represented as a span, allowing operators to identify which component is responsible for latency.
- **Backend abstraction:** External backends are implementation details. LCORE emits a multi-span trace per request populated from internal summaries. Backend OTel is not merged into the LCORE tree.
- **Safe observability by design:** Only structured metadata (e.g., IDs, counts) is captured in span attributes; latency is visible from span timing, avoiding exposure of raw prompts, retrieved content, or other sensitive user data.

This improves observability, reduces time to diagnose issues, and aligns LCORE with modern cloud-native monitoring practices.

## Requirements

**R1 – Tracing support**  
LCORE shall support request tracing for all requests, producing telemetry compatible with OpenTelemetry.  

**R2 – Configuration**  
Tracing shall be configurable at deployment time. The effective tracing configuration shall be inspectable at runtime so operators can verify the running setup without hunting through separate deployment manifests (secret values shall be redacted).

**R3 – Trace continuation**  
It shall be possible to continue an upstream trace when a calling service already started one, and to disable that behavior so LCORE starts a standalone trace per request. The configuration shall be documented.

**R4 – Session grouping**  
LCORE shall group all traces for a user conversation into a session container, so that multiple user prompts / model turns within the same conversation can be correlated and analyzed together. Each session shall carry a unique conversation identifier, an anonymized user id and other relevant attributes.

**R5 – LCORE-owned span tree**  
LCORE shall emit the prescribed multi-span trace per request from its own pipeline summary objects. LCORE shall not merge backend-exported spans into the trace.

**R6 – Coverage**  
Tracing shall cover the full request lifecycle, including key stages such as request handling, LLM calls, RAG retrieval, conversation management, and shield moderation.  

**R7 – Semantic conventions and data handling**  
Spans and their attributes shall follow OpenTelemetry semantic conventions and avoid capturing sensitive or high-volume data.  

**R8 – Lifecycle management**  
Tracing shall be properly initialized and shut down with the application, ensuring all data is flushed on shutdown.  

**R9 – Resilience**  
Tracing failures must not impact request processing or user-facing behavior.  

**R10 – Documentation**  
The feature shall include documentation describing how to enable tracing, configure required environment variables, and verify correct behavior.

## Use Cases

**U1**  
As an SRE, I want LCORE to export traces to my OTLP endpoint, so that I can monitor and alert consistently with other services.

**U2**  
As a platform engineer, I want upstream W3C trace context honored by default, with the option to disable it, so that gateway-started traces continue through LCORE when needed.

**U3**  
As a developer, I want spans for RAG, LLM, tools, and shields, so that I can localize latency and errors without storing high volume data in the trace backend.

**U4**  
As an administrator, I want tracing configurable at deploy time and the effective settings visible for inspection at runtime, so I can verify the running setup without hunting through separate deployment manifests.

**U5**  
As an SRE, I want each pipeline step (retrieval, tool call, generation, etc.) as its own LCORE span with consistent naming and metadata, without depending on backend trace export or cross-service propagation.

**U6**  
As a developer, I want remote and in-process backend integrations to produce the same trace shape from LCORE's perspective.

## Architecture

### Chosen approach (spike decisions)

| Spike decision | Choice |
|----------------|--------|
| 1 — Configuration | Environment-first (`OTEL_*`; no LCORE YAML block); `/config` scrapes env |
| 2 — SDK initialization | `opentelemetry-instrument` |
| 3 — Inbound trace context | Default W3C propagators; `OTEL_PROPAGATORS=none` to disable |
| 4 — Outbound to backends | LCORE-owned multi-span tree; no outbound propagation |
| 5 — Export topology | OTLP to a configurable endpoint only; collector deployment out of scope (operator choice) |
| 6 — Span filtering | Downstream in operator-managed collector or backend pipeline |

### Overview

Clients send requests to LCORE, which builds a structured span tree from internal pipeline summaries. External backends are not represented by their own exported spans. LCORE exports traces via OTLP to a configured trace backend for monitoring.

### Tracing boundary

LCORE exports a single coherent trace per inbound request. External dependencies (inference backends, MCP servers, databases) are implementation details - their work is reflected only in LCORE-constructed step spans.

- LCORE does **not** propagate trace context to external backends.
- LCORE does **not** depend on downstream services exporting spans into the same trace.
- Each backend interaction is represented by **one parent span** (e.g., `backend.inference`, `backend.rag.retrieve`, `backend.toolgroups.list`) whose duration covers the full call, including retries and streaming.
- Downstream services may run their own OTel independently; that is an operator concern, not part of the LCORE trace contract.

```
Caller ──(HTTP, optional traceparent/tracestate)──► LCORE FastAPI (root span)
                                                        │
                                                        ├─► validation, conversation management, shields
                                                        ├─► llm_inference
                                                        │       ├─► rag_retrieval
                                                        │       ├─► tool_execution
                                                        │       └─► response_generation
                                                        └─► conversation persistence, quota, etc.

LCORE: TracerProvider ──► OTLP exporter ──► (optional) Collector ──► trace backend

External backends: not merged into the LCORE span tree; optional separate OTel export
```

### Configuration and SDK initialization

Spike **Decision 1** (environment-first) and **Decision 2** (`opentelemetry-instrument`).

All tracing configuration uses **`OTEL_*` environment variables** at process launch. LCORE defines **no YAML block** for tracing.

LCORE starts with **`opentelemetry-instrument`**, which initializes the SDK from `OTEL_*` before application code runs and auto-instruments supported libraries. The application does not construct or configure the SDK. Use `OTEL_SDK_DISABLED=true` as a process-wide kill switch.

**`/config` visibility:** `GET /v1/config` handler reads relevant `OTEL_*` variables and appends them under `observability.otel` (secrets redacted).

### Inbound W3C trace context

Spike **Decision 3** (default propagators).

Use standard OpenTelemetry propagators via **`OTEL_PROPAGATORS`** (default includes W3C `tracecontext`). FastAPI auto-instrumentation extracts `traceparent` on incoming requests. Applies to inbound LCORE HTTP requests only.

To disable inbound propagation, set `OTEL_PROPAGATORS=none`.

### LCORE-owned span tree

Spike **Decision 4** (LCORE-owned spans; no outbound propagation).

External backend interactions are implementation details from a tracing perspective. LCORE does **not** inject W3C trace context on outbound backend calls and does **not** merge backend-exported spans into the trace.

Instead, LCORE constructs the full span tree per request from internal pipeline summary objects - structures that accumulate timings, inputs/outputs, retrieved sources, and tool-call records as the request is handled. Each prescribed step becomes its own span (e.g. retrieval, each tool invocation, response generation).

```python
with tracer.start_as_current_span("backend.inference") as span:
    span.set_attribute("backend.operation", "inference")
    span.set_attribute("llm.model.id", model_id)
    # ... invoke backend client ...
    span.add_event("llm.response.completed")
    span.set_attribute("llm.usage.input_tokens", ...)
```

### Export topology

Spike **Decision 5**.

LCORE's responsibility is only to export OTLP telemetry to the configured endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT` and related `OTEL_*` variables).

What exists behind that endpoint is out of scope for this feature and is an infrastructure/operator decision. The endpoint may point directly to an OTLP-compatible backend (e.g. LangFuse) or to an OpenTelemetry Collector, which can perform fan-out, filtering, or export to additional destinations. Deployment and configuration of any collector or downstream telemetry infrastructure are managed outside of LCORE **for now**.

### Span filtering

Spike **Decision 6**.

LCORE emits all spans defined in this specification. Filtering, sampling, scrubbing, or tail sampling is applied downstream in the collector or backend. LCORE does **not** provide per-span or per-span-group enable flags.

### Span coverage

Recommended candidate spans, grouped by functional category. Each logical operation is represented by one parent span, with child spans for underlying pipeline steps—populated only from LCORE summary objects, not from backend-exported traces.

#### Shared inference pipeline

Covers core request handling and LLM processing (`POST /v1/query`, `/streaming_query`, `/responses`, `/infer`).

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| MCP OAuth probe | `utils.mcp_oauth_probe.check_mcp_auth` | Validate MCP-related auth before backend calls | `mcp.auth.probe.ok` | `mcp.auth.probe.finished` |
| Quota gate | `utils.quota.check_tokens_available` | Enforce token quota before work | `quota.check.passed` | — |
| Request validation | Various validators | Validate overrides & attachments | `request.attachments.count`, `llm.model.id`, `llm.provider.id` | `validation.completed` |
| Shield | `utils.shields.run_shield_moderation` now (shields will be agent capabilities in the future) | Apply input/output shields | `shield.result` | `shield.rejected`, `pii.detected` |
| `llm.inference` (parent) | `utils.agents.query.retrieve_agent_response`; `utils.agents.streaming.retrieve_agent_response_generator`, `agent_response_generator` | Orchestrate backend invoke and post-process | span duration → response time | `llm.inference.started`, `llm.inference.completed` |
| ↳ `rag.retrieve` (child) | `utils.agents.tool_processor.process_native_tool_result` (`FileSearchTool`), `summarize_file_search_result`, `rag_chunks_from_file_search_results` | Retrieve context for the turn | `rag.input`; `rag.sources.count`, `rag.sources[]` | `rag.retrieval.completed` |
| ↳ `tool.execute` (child) | `utils.agents.tool_processor.process_function_tool_call`, `process_native_tool_call`, `process_function_tool_result`, `process_native_tool_result`; `utils.agents.streaming.dispatch_stream_event` | Execute tools for the turn (one span per tool call) | `tool.calls.count`, `tool.calls.names` | `tool.execution.completed` |
| ↳ `skill.activate` (child) | `utils.pydantic_ai.build_agent` (`_skills_capability`, `_agent_capabilities`) | Skills selected for the turn | `skill.activations` | `skill.activated` |
| ↳ `response.generate` (child) | `utils.agents.query.build_turn_summary_from_agent_run`, `extract_agent_token_usage`; `utils.agents.streaming._process_token`, `dispatch_stream_event` (`AgentRunResultEvent`) | Generate assistant response | `llm.usage.input_tokens`, `llm.usage.output_tokens`, `llm.stream`, `llm.response` | `llm.response.completed`, `turn.persisted` |

#### Streaming pipeline spans

For streaming endpoints (`/streaming_query`, `/responses`) and async tasks.

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| SSE stream lifecycle | Async generators in `streaming_query.py` / `responses.py` | Bind stream to trace |  `stream.conversation.id`; span duration → response time | `stream.first_delta`, `stream.completed`, `stream.error` |
| MCP tool in stream | Stream parsers / MCP handlers | Tool call visible in stream | `mcp.tool.name`, `mcp.args.byte.len`, `tool.calls.count`, `tool.calls.names` | `mcp.tool.arguments.done`, `mcp.tool.result.received` |
| Topic summary (background) | `utils.query.update_conversation_topic_summary` | Async topic summary | `topic.summary.task.started` | `topic.summary.task.finished` |

#### Catalog, discovery, and MCP auth

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| List toolgroups | `tools.tools_endpoint_handler` | List backend toolgroups | `toolgroups.count`, `backend.operation` | `toolgroups.list.done` |
| List tools per group | `tools.tools_endpoint_handler` | Tools in one toolgroup | `tools.toolgroup.id`, `tools.count`, `backend.operation` | `tools.list.done` |
| Get RAG | `rags.get_rag_endpoint_handler` | Single RAG metadata | `rags.rag.id`, `backend.operation` | — |
| Get provider | `providers` get handler | Single provider | `providers.provider.id`, `backend.operation` | — |

**Other discovery spans (trivial):** List shields, models, providers, service info, effective config, MCP client options (attributes/events similar to above).

#### MCP server administration

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Register MCP server | `mcp_servers.register_mcp_server_handler` | Register dynamic MCP | `mcp.server.name`, `mcp.register.ok`, `backend.operation` | `mcp.server.registered` |
| List MCP servers | `mcp_servers.list_mcp_servers_handler` | List runtime MCP servers | `mcp.servers.count` | — |
| Delete MCP server | `mcp_servers.delete_mcp_server_handler` | Unregister toolgroup | `mcp.server.name`, `mcp.delete.ok`, `backend.operation` | `mcp.server.deleted` |

#### Conversations, feedback, RLS, A2A, misc

| Span | Place | Description | Key Attributes | Key Events |
|------|-------|-------------|----------------|------------|
| Conversations CRUD | Handlers & backend client calls | DB + backend conversation APIs; session grouping | `conversation.id`, `conversation.items.count`, `session.invocation.count`, `session.transcript` (anonymized), `backend.operation` | `conversation.db.query`, `conversation.backend.call` |
| Feedback | `feedback` module handlers | Submit/query feedback | `feedback.operation`, `feedback.status.code`, `feedback.rating`, `feedback.comment` `feedback.conversation`  | `feedback.submitted`  |
| RLS infer | `rlsapi_v1` | Render template / infer request | `rls.template.ok`, `llm.model.id`, `llm.provider.id` | `rls.template.rendered` |
| Stream interrupt | `stream_interrupt.*` | Cancel in-flight stream | `interrupt.request_id` | — |
| A2A | `a2a` endpoints | Inbound agent requests | `a2a.rpc.method`, `a2a.request.id` | `a2a.dispatch.start`, `a2a.dispatch.end` |
| Authorized probe | `authorized.*` | Auth check | `authorized.ok` | — |

Health, metrics, and root endpoints are noisy and should not have manual spans, but FastAPI will still generate automatic spans. These can be filtered via `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` or dropped downstream.

#### Naming conventions

- **Span names:** `component.operation` (e.g., `rag.retrieve`, `llm.invoke`, `backend.inference`)  
- **Attributes:** Dot-separated namespaces (e.g., `llm.model.id`, `rag.chunks.count`, `backend.operation`)  
- **Events:** Short, past-tense, milestone names (e.g., `stream.completed`, `llm.response.finished`)  

### Prometheus metrics

LCORE continues to expose **Prometheus-compatible metrics** via `/metrics`. While OpenTelemetry tracing is introduced for spans, **metrics remain on Prometheus**.

- Continue using `/metrics` for all operational metrics.
- Expand Prometheus metrics as product needs evolve.
- Maintain low cardinality in metric labels.

### Failure handling and sensitive data

- **Export errors on request path:** Tracing failures do not affect the HTTP response; errors are logged.
- **Misconfigured exporter:** Missing or invalid `OTEL_*` exporter settings mean spans are not exported; user requests are not impacted. Operator/deployment concern, not a startup failure.
- **Span attributes:** Metadata only (lengths, hashes, IDs, coarse results). No raw prompts or retrieved content.

### Environment variables

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

### Deployment

**`docker-compose.yaml` (LCORE service)** — set `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_PROTOCOL`; add headers, sampler, `OTEL_SDK_DISABLED`, etc. as needed via `environment` / `env_file`.

**`Containerfile` (LCORE image)** —  
`ENTRYPOINT ["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`

### Trigger mechanism

Tracing is active when the process starts with **`opentelemetry-instrument`** and a coherent set of **`OTEL_*`** values (unless `OTEL_SDK_DISABLED=true`). The SDK and propagators are fully configured from the environment at process launch; LCORE YAML plays no role.

## Storage / data model changes

**None.** Traces are exported; LCORE does not persist span data in application databases.

## Configuration

LCORE defines **no YAML block** for OpenTelemetry. All tracing settings are **`OTEL_*` environment variables**, set at deploy time. See Architecture → Environment variables.

### `/config` response enrichment

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

### API changes

No **required** change to JSON requests/responses. The `/config` response gains `observability.otel` as described above.

### Error handling

- **Request path:** Tracing errors do not change HTTP status for the user.
- **Startup:** Invalid or missing `OTEL_*` values do not block LCORE startup; they affect export only.

### Security considerations

- OTLP endpoint URL and non-secret `OTEL_*` values may appear in the `/config` response via env scraping.
- Bearer tokens, client keys, and sensitive headers stay in **`OTEL_*`** and secret mounts; redact them in `/config` output.
- Span attributes: no raw user ids or secrets.

### Migration / backwards compatibility

- **No tracing by default:** Until operators set **`OTEL_*`** exporter variables and use **`opentelemetry-instrument`**, existing deployments behave as today (no OTLP export).
- New dependencies must not alter runtime when the SDK is disabled.

## New dependencies

- `opentelemetry-distro`
- `opentelemetry-exporter-otlp`
- `opentelemetry-instrumentation-fastapi`

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `pyproject.toml` | Add OTel API, SDK, OTLP exporter, FastAPI instrumentor, propagators; pin versions per project policy. |
| `src/app/endpoints/config.py` | Scrape `OTEL_*` env vars into `observability.otel` on `/config` response; redact secrets. |
| `app/endpoints/*.py`, `utils/*.py` | Add manual spans around logical sections of request handlers. |
| `Containerfile` | Add OTel packages; set **`ENTRYPOINT`** to **`["opentelemetry-instrument", "python3.12", "src/lightspeed_stack.py"]`**. |
| `docker-compose.yaml` | **`environment`** / **`env_file`**: required **`OTEL_*`** exporter fields. |

## Open Questions

- Which `OTEL_*` variables are included in the `/config` scrape?


## Addendum: PII redaction strategy

|                          |                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------|
| **Date**                 | 2026-09-22                                                                        |
| **Authors**              | Anik Bhattacharjee                                                                |
| **Feature / Initiative** | [UIESTRAT-229: Enable collection & upload of Observability OTel data stripped of PII/sensitive data](https://redhat.atlassian.net/browse/UIESTRAT-229)                      |

The three core inference spans (`/v1/query`, `/v1/streaming_query`, `/v1/responses`) carry
raw, un-hashed request/response content for evaluation, relaxing the original metadata-only rule
(**R7**; §Why "Safe observability by design"). This addendum covers how that content is
redacted of PII.

### The problem

Raw span text (prompts, responses, RAG chunks, tool I/O) can contain PII, so it must be scrubbed
before the span leaves LCORE — before OTLP export to a hosted backend such as LangFuse, and before
any cross-org sharing. This is a portfolio-wide obligation from Red Hat's AI Assessment process, 
not specific to LCORE.

### The approach — Presidio from PyPI

Use the upstream [Presidio](https://github.com/microsoft/presidio) library directly. Add
[`presidio-analyzer`](https://pypi.org/project/presidio-analyzer/) and
[`presidio-anonymizer`](https://pypi.org/project/presidio-anonymizer/)
(both on PyPI) to `pyproject.toml`, and wrap them in a small `redact(text) -> str` helper that
detects and replaces email, hostname, IP (v4/v6), location, organization, person, phone, and URL.
No new runtime service: the pieces are two libraries plus one helper, applied wherever content is
set on a span (more details in next section). 
It is not free of build and footprint cost, though — the [spaCy](https://spacy.io/) model
has to be packaged into the hermetic Konflux build and adds image size and pod memory (see § Deploying the
spaCy model).

### Deploying the spaCy model

`presidio-analyzer` pulls in the [spaCy](https://spacy.io/) library but not a model. The
named-entity recognition (NER) runs against a separate [model artifact](https://spacy.io/models/en)
(`en_core_web_lg` by Presidio's default, ~560 MB; `en_core_web_md` ~40 MB; `en_core_web_sm` ~12 MB)
that spaCy loads by name at runtime via
[`spacy.load(...)`](https://spacy.io/api/top-level#spacy.load). Without the model in the image,
`AnalyzerEngine()` fails to construct.

Getting the model into the image will require some work, because the production image is a
Konflux **hermetic build** (`deploy/lightspeed-stack/Containerfile`): in LCORE's existing setup, when
[cachi2](https://github.com/containerbuildsystem/cachi2) is active it sets
`PIP_NO_INDEX=true` and installs only prefetched, hash-pinned wheels from `--find-links`, against
`.konflux/requirements.hashes.*.txt`. There is no network at build time, which rules out the usual
[`python -m spacy download en_core_web_lg`](https://spacy.io/usage/models#download) (it fetches from
[GitHub](https://github.com/explosion/spacy-models) at build time) and rules out
downloading at container startup (breaks air-gapped runtime, adds cold-start latency).

The hermetic-compatible path is to pin the model wheel as an explicit dependency so cachi2
prefetches and hash-locks it like any other package:

```
en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl
```

The model version must match the resolved spaCy version, so they need to be pinned together.

At runtime, loading the model costs a few hundred MB of RSS, so the `AnalyzerEngine` and
`AnonymizerEngine` are constructed once (module-level singleton or lazy init) and reused across
requests — `redact()` never rebuilds them per call.

The `sm`/`md`/`lg` choice is the accuracy-vs-footprint knob, and it moves three things at once: image
size, pod memory, and NER recall on names, organizations, and locations. `lg` gives the best recall
at the largest cost; `sm` is small but weaker.

### Alternatives considered

- **Reuse the existing regex redaction engine** ([`redact_text`](../../../src/pydantic_ai_lightspeed/capabilities/redaction/core.py#L24) + the configurable [`RedactionConfig`](../../../src/models/config.py#L2912)
  rules, already in the repo) at span emission. This is the engine under the `PiiRedactionCapability`
  shield, not the shield itself — the shield is used to redact PII during a2a live message flow. Only the 
  "text in, redacted text out" engine would be used from here. No new dependency and no model
  download, deterministic, and fast. However, regex handles structured PII well (email, IP, phone are
  easy to express) but cannot reliably detect free-text entities like names, organizations, and
  locations, so recall on those depends on hand-written patterns and is weak.

  Comparatively, the existing data-anonymizer based on Presidio is already [compliance approved and in production](https://docs.google.com/document/d/1BNBIDUz-lLmUjT9N9cEMqgaQv9EqfLKwZrA8gtbtlY8/edit?tab=t.0).  

- **Managed cloud PII services** (AWS Comprehend, Google Cloud DLP, Azure AI Language). Ruled out:
  each sends span content to an external service on every request, which reintroduces the
  PII-leaves-the-process problem this work exists to close, adds a network hop, and adds a cloud
  dependency the LCORE binary can't assume.

Presidio wins on two counts: good name/org/location recall without building an NER pipeline by
hand, and alignment with the shared `data-anonymizer` library (also Presidio-based; see § Future),
so the later swap stays a drop-in rather than an engine change. The one cost is the spaCy model
download. If that model turns out to block image size or air-gapped builds, the regex-extend option
above is the fallback.

### Where redaction runs — redact at emission, through one helper

Content is redacted at the point it's set on the span. All content fields will go on spans
through a **single centralized helper** — e.g. `set_content_attribute(span, key, text)` — that runs
each value through the Presidio `redact()` helper before calling `set_attribute`. For any content
serialized as a JSON string (e.g. RAG chunks or tool I/O), the helper redacts each leaf string
(`content`/`args`/`source`) before `json.dumps`, so the serialized attribute never contains raw
PII. Properties of this approach:

- **The span never holds raw PII.** R11 ("redact before content leaves the process") is satisfied
  by construction — there is no in-memory window where a raw value sits on a span or in the export
  queue.
- **One code path to audit.** Because content can only reach a span through the helper, there is a
  single place to review and test; individual emission sites cannot forget to redact (there is no
  raw path to `set_attribute` for content keys). A review/lint rule reinforces "content goes
  through the helper."
- **Fail-closed.** If the redactor raises, the helper omits the field rather than emitting raw
  text — consistent with R9 (a tracing failure must never leak or break the request).
- **Cost.** Redaction runs on the request path (synchronous), not in the export background thread.
  This is minor. It's a text pass over already-generated output, dwarfed by the LLM call, and only
  incurred when raw-content capture is enabled (scoped to the three core spans). The helper is the
  single place to make it async/best-effort if it ever becomes a bottleneck.

### Future: adopting the shared `data-anonymizer` library

A shared, Presidio-based redactor already exists: `data-anonymizer` (used by Ask Red Hat et al.;
see the [shared Presidio library strategy doc](https://docs.google.com/document/d/1BNBIDUz-lLmUjT9N9cEMqgaQv9EqfLKwZrA8gtbtlY8/edit?tab=t.0#heading=h.9qfphopokr7u)).
LCORE may move to it eventually, so redaction is maintained once across teams rather than
per-project. The only obstacle is distribution. `data-anonymizer` lives on Red Hat's internal GitLab
(`gitlab.cee.redhat.com/uxe-data-ai-solutions/data-anonymizer`), not PyPI, and a GitHub build/CI
can't install from internal GitLab without internal credentials — so it can't go in
`pyproject.toml`.

The swap stays small because redaction is already funneled through the single `redact()` helper
(§ Where redaction runs). To adopt the shared library without breaking the GitHub build, turn that
helper into a **redaction slot** — one interface the telemetry path calls without knowing the
backend:

- **GitHub build (default):** the slot keeps using public Presidio from PyPI.
- **Red Hat's internal build:** a downstream build fills the slot with `data-anonymizer` via an
  adapter, added at the stage where internal GitLab is reachable.

Until such a move is deemed required, the PyPI Presidio helper above is the whole
implementation.

### Requirements addendum

- **R11 — PII redaction before export.** Raw content on the three core inference spans shall pass
  through PII detection/redaction before leaving the process (OTLP export or cross-org sharing).

## Appendix A: Jira epics and related tracking

**Epics**

- [LCORE-1791](https://redhat.atlassian.net/browse/LCORE-1791)
- [LCORE-1799](https://redhat.atlassian.net/browse/LCORE-1799)
- [UIESTRAT-229](https://redhat.atlassian.net/browse/UIESTRAT-229)

## Appendix B: External references

- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
