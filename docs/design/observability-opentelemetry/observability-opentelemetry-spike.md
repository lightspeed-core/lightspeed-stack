# Overview

This document is the deliverable for [LCORE-1591](https://redhat.atlassian.net/browse/LCORE-1591). It explores design options for OpenTelemetry tracing in Lightspeed Core and records recommendations for each decision.

**The problem**: RH needs visibility into how AI products are used (request flows, tool invocations, latency, errors, and outcomes across agent turns), but LCORE does not yet emit OpenTelemetry traces into the collection pipeline.

**Scope of this spike**: Trace data format and required attributes, where tracing configuration lives, how the SDK is initialized, how trace context is handled on inbound and outbound boundaries, collector deployment options (out of scope for implementation), and span filtering. The chosen approach is captured in the [feature design document](observability-opentelemetry-design.md).

---

## OpenTelemetry terminology

- **Trace**: A complete record of a single request as it flows through one or more services. A trace is composed of multiple spans that may be linked via context propagation.

- **Span**: A timed operation representing a unit of work within a trace (e.g., HTTP request handling, LLM call, RAG retrieval). Spans can be nested to reflect parent–child relationships.

- **Attributes**: Key–value pairs attached to a span that describe its properties (e.g., model ID, token counts). Elapsed time for the operation is represented by the span's own start/end, not duplicated as a duration attribute. Attributes should be low-cardinality and must not contain sensitive data.

- **Events**: Timestamped annotations within a span that capture significant moments during execution (e.g., `stream.first_delta`, `llm.response.completed`). Events are not for bulk data, but for marking milestones.

- **Session**: A logical container above the trace level that groups related user traces from the same ongoing interaction (e.g., a multi-turn conversation). OpenTelemetry has no native session object; sessions are represented by shared context carried on each trace export so backends can correlate separate requests into one conversation view.

---

## Background

### External backends

LCORE delegates inference, retrieval, tool execution, and related work to external backend services. Those backends may run as separate processes (remote HTTP) or be embedded in-process.

External backends may export their own telemetry when configured independently. How LCORE traces relate to backend telemetry is a design decision (see Decision 4).

### Lightspeed Core

Currently, LCORE exposes only Prometheus-compatible metrics via the `/metrics` endpoint. OpenTelemetry is not supported yet: there are no traces, spans, or OTLP metrics, and no configuration exists for enabling or controlling OTEL. All observability today relies on Prometheus scraping.

---

# Strategic decisions

## Decision 1: Where the configuration lives

OpenTelemetry is usually configured via standard environment variables (`OTEL_*`). LCORE is configuration-driven for most features, but the SDK may bootstrap at process start, before LCORE YAML loads—constraining which options are viable.

| Option | Description |
|--------|-------------|
| A — Config-only | All tracing and exporter options in LCORE YAML |
| B — Environment-first | All OTLP/SDK wiring from `OTEL_*` at process launch |
| C — Hybrid YAML + env | Mandatory export fields in YAML; advanced options in `OTEL_*` |

**Option A — Config-only**  
All tracing and exporter options are modeled in LCORE YAML, avoiding `OTEL_*` entirely.  
- **Pros:** Single file alongside other LCORE settings.  
- **Cons:** OpenTelemetry exposes a large, evolving option set; modeling it in YAML is hard to maintain. Incompatible with automatic `opentelemetry-instrument`, which initializes the SDK before YAML is available.

**Option B — Environment-first**  
All OTLP and SDK wiring comes from `OTEL_*` variables at process launch. LCORE defines no YAML block for tracing.  
- **Pros:** Matches upstream OpenTelemetry standards and deployment patterns; works with automatic `opentelemetry-instrument`; no duplicate config surface.  
- **Cons:** Tracing settings are not in the LCORE YAML file - operators set them in the deployment manifest. Values are read at process startup and are immutable until the process is restarted.

**Option C — Hybrid YAML + env**  
LCORE YAML carries mandatory export fields (endpoint, protocol, service name); `OTEL_*` covers advanced options. Requires manual SDK initialization after YAML loads.  
- **Pros:** Sink basics visible in LCORE YAML.  
- **Cons:** Two configuration surfaces with precedence rules; fights the instrument bootstrap model; more application code to maintain.

**Recommendation:** **Option B.** Configure tracing through `OTEL_*` environment variables at deployment time, and pair it with `opentelemetry-instrument` (Decision 2). Expose the effective configuration through `GET /config` to provide a single inspection point for operators. The endpoint can read the relevant `OTEL_*` environment variables and include them under an `observability.otel` section in the configuration response (with secrets redacted), allowing operators to inspect the effective tracing configuration via the API without duplicating it in YAML.

---

## Decision 2: SDK initialization strategy

| Option | Description |
|--------|-------------|
| A — `opentelemetry-instrument` | SDK from `OTEL_*` before app code; auto-instrumentation |
| B — Manual SDK initialization | Construct `TracerProvider` in application lifecycle after YAML loads |

**Option A — Auto-instrumentation with `opentelemetry-instrument`**  
The process starts with `opentelemetry-instrument`, which initializes the SDK from `OTEL_*` **before** application code runs and auto-instruments supported libraries (FastAPI, HTTP clients, etc.).  

- **Pros:** No application-level SDK setup; aligned with standard OpenTelemetry deployment; all `OTEL_*` settings applied automatically.  
- **Cons:** Configuration must be available at process start; cannot be sourced from runtime-loaded LCORE YAML. Collector authentication is static (`OTEL_EXPORTER_OTLP_HEADERS` collected at startup). Per-request OTLP export authentication is not supported; that would require a custom exporter, not env-only auto-instrumentation.

**Option B — Manual SDK initialization**  
OpenTelemetry is initialized explicitly in application lifecycle (e.g., FastAPI `lifespan`) after LCORE YAML loads. Application code constructs the `TracerProvider` and exporters.  

- **Pros:** Could read export settings from YAML (Option C in Decision 1). Required if OTLP export authentication must vary per request (e.g., custom `SpanExporter` that reads request context when exporting).  
- **Cons:** More code to maintain; some `OTEL_*` variables must be resolved manually; diverges from upstream conventions.

**Recommendation:** **Option A** (`opentelemetry-instrument`) for now. LCORE application code creates only manual spans, making automatic instrumentation the simplest approach. This is sufficient unless export authentication must vary per request. If that requirement arises, **Option B** may become appropriate in the future.

---

## Decision 3: Inbound W3C trace context

When a gateway or upstream service sends a requests LCORE with W3C headers (`traceparent`, `tracestate`), LCORE must decide whether to continue that trace or start a new one.

| Option | Description |
|--------|-------------|
| A — Default propagators | Extract `traceparent` via standard `OTEL_PROPAGATORS` |
| B — Disable propagation | Set `OTEL_PROPAGATORS=none`; standalone LCORE traces |

**Option A — Accept upstream context via default propagators**  
Keep default setup for `OTEL_PROPAGATORS` (or set it explicitly to include `tracecontext`). The OpenTelemetry SDK and FastAPI auto-instrumentation extract `traceparent` on incoming requests, so LCORE spans attach to the upstream trace.  

- **Pros:** Works out of the box with gateways and service meshes; no LCORE-specific code; matches how other OpenTelemetry services behave.  
- **Cons:** LCORE joins upstream traces unless the operator changes env vars.

**Option B — Disable inbound propagation**  
Set `OTEL_PROPAGATORS=none`. LCORE ignores `traceparent` and starts a standalone trace for every request.  

- **Pros:** Useful in isolated environments or when upstream trace IDs must not flow into LCORE.  
- **Cons:** Breaks end-to-end trace continuity from gateways.

**Recommendation:** **Option A** as the default deployment posture. Document **Option B** (`OTEL_PROPAGATORS=none`) for operators who need standalone traces.

---

## Decision 4: Outbound trace context to external backends

LCORE calls external backend services (remote HTTP or in-process). A key design choice is whether those calls participate in the **same distributed trace** as LCORE or are represented differently.

| Option | Description |
|--------|-------------|
| A — Outbound W3C propagation | Inject `traceparent` on backend HTTP requests; backend spans join the LCORE trace |
| B — LCORE-owned span tree | LCORE emits the prescribed multi-span trace from internal pipeline summaries; no outbound propagation |

**Option A — Outbound W3C propagation**  
The shared HTTP client for backend calls injects the active trace context into outgoing requests (e.g., via an `httpx` request hook or auto-instrumented client). Backend services that extract W3C context export child spans in the same trace tree.  

- **Pros:** Single unified trace across LCORE and backend processes when backends are OTel-instrumented; familiar distributed-tracing model.  
- **Cons:** Requires coordination with backend OTel configuration and propagation; in-process backends may not expose an HTTP inject point; library vs service deployment modes behave differently; couples LCORE observability to backend trace export. Backend-exported spans use each service’s own naming and shape and cannot satisfy LCORE’s required trace structure.

**Option B — LCORE-owned span tree**  
LCORE does not propagate trace context to backends and does not merge backend-exported spans into the trace. Instead, LCORE constructs the full span tree itself—one span per prescribed pipeline step (e.g. retrieval, each tool call, response generation)—populated from internal summary objects gathered during request handling (timings, anonymized inputs/outputs, source lists, tool-call records). Backend services remain implementation details; their own telemetry, if any, stays outside the LCORE trace contract.

- **Pros:** Same structured trace for remote and in-process backends; no cross-service propagation contract; backend OTel remains an independent operator concern. LCORE alone defines span names, parent/child links, sequence, and step metadata so every export matches unified schema.  
- **Cons:** Finer backend-internal breakdown (e.g. individual HTTP retries inside Llama Stack) is not visible unless LCORE chooses to surface it in step metadata; operators rely on LCORE’s summaries rather than raw backend traces.

**Recommendation:** **Option B.** Observability follows a unified schema with prescribed step types and fields. LCORE must emit that multi-span tree from its own pipeline summaries; accepting backend service spans would break the contract (foreign names, wrong granularity, missing sequence metadata). Do not inject trace context to external backends.

---

## Decision 5: Collector deployment

LCORE exports OTLP to a configurable endpoint. Operators may route that traffic through an OpenTelemetry Collector; if they do, the deployment choice is how that collector runs relative to LCORE:

| Option | Description |
|--------|-------------|
| A — Sidecar | Collector container in the same pod as LCORE; OTLP to localhost |
| B — Standalone service | Shared collector Service in the cluster; OTLP over the network |

**Recommendation:** Out of scope for this feature. The scope of this work is limited to enabling LCORE to export OpenTelemetry telemetry to a configurable OTLP endpoint. How that endpoint is deployed is an infrastructure decision that can be made independently and may be addressed in a future design. Accordingly, this feature does not prescribe a collector deployment model.

---

## Decision 6: Span filtering

| Option | Description |
|--------|-------------|
| A — Filtering in LCORE | `SpanProcessor` or per-span enable flags in application configuration |
| B — Filtering in collector/pipeline | Downstream sampling, scrubbing, tail sampling |

**Recommendation:** **Option B.** LCORE emits spans as defined in the feature design; filtering policy lives in the collector or pipeline. LCORE does not provide per-span or per-span-group enable flags.

---

# Appendix: External references

- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OTLP specification](https://opentelemetry.io/docs/specs/otlp/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry SDK environment variables reference](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)

---
