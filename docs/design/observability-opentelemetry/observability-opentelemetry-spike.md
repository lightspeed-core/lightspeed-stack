# Overview

This document is the deliverable for [LCORE-1591](https://redhat.atlassian.net/browse/LCORE-1591). It explores design options for OpenTelemetry tracing in Lightspeed Core and records recommendations for each decision.

**The problem**: LCORE exposes only limited set of Prometheus-compatible metrics today. There are no traces, spans, or OTLP export, making it difficult to identify latency bottlenecks, localize errors, and debug issues across LCORE subsystems and backend calls.

**Scope of this spike**: Where tracing configuration lives, how the SDK is initialized, how trace context is handled on inbound and outbound boundaries, export topology, and span filtering. The chosen approach is captured in the feature design document.

---

## OpenTelemetry terminology

- **Trace**: A complete record of a single request as it flows through one or more services. A trace is composed of multiple spans that may be linked via context propagation.

- **Span**: A timed operation representing a unit of work within a trace (e.g., HTTP request handling, LLM call, RAG retrieval). Spans can be nested to reflect parent–child relationships.

- **Attributes**: Key–value pairs attached to a span that describe its properties (e.g., model ID, token counts). Elapsed time for the operation is represented by the span's own start/end, not duplicated as a duration attribute. Attributes should be low-cardinality and must not contain sensitive data.

- **Events**: Timestamped annotations within a span that capture significant moments during execution (e.g., `stream.first_delta`, `llm.response.completed`). Events are not for bulk data, but for marking milestones.

---

## Background

### External backends

LCORE delegates inference, retrieval, tool execution, and related work to **external backend services**. Those backends may run as separate processes (remote HTTP) or be embedded in-process.

External backends may export their own telemetry when configured independently. How LCORE traces relate to backend telemetry is a design decision (see Decision 4).

### Lightspeed Core

Currently, LCORE exposes only Prometheus-compatible metrics via the `/metrics` endpoint. OpenTelemetry is not supported yet: there are no traces, spans, or OTLP metrics, and no configuration exists for enabling or controlling OTEL. All observability today relies entirely on Prometheus scraping.

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
**Pros:** Single file alongside other LCORE settings.  
**Cons:** OpenTelemetry exposes a large, evolving option set; modeling it in YAML is hard to maintain. Incompatible with `opentelemetry-instrument`, which initializes the SDK before YAML is available.

**Option B — Environment-first**  
All OTLP and SDK wiring comes from `OTEL_*` variables at process launch. LCORE defines no YAML block for tracing.  
**Pros:** Matches upstream OpenTelemetry standards and deployment patterns; works with `opentelemetry-instrument`; no duplicate config surface.  
**Cons:** Tracing settings are not in the LCORE YAML file—operators set them in the deployment manifest.

**Option C — Hybrid YAML + env**  
LCORE YAML carries mandatory export fields (endpoint, protocol, service name); `OTEL_*` covers advanced options. Requires manual SDK initialization after YAML loads.  
**Pros:** Sink basics visible in LCORE YAML.  
**Cons:** Two configuration surfaces with precedence rules; fights the instrument bootstrap model; more application code to maintain.

**Recommendation:** **Option B.** Configure tracing through `OTEL_*` at deploy time. Pair with `opentelemetry-instrument` (Decision 2). Surface effective settings via `/config` if operators need a single inspection point. **`GET /v1/config`** can read relevant `OTEL_*` variables and append them under `observability.otel` block in the configuration response (secrets redacted), so operators inspect effective tracing config via the API without duplicating it in YAML.

---

## Decision 2: SDK initialization strategy

| Option | Description |
|--------|-------------|
| A — `opentelemetry-instrument` | SDK from `OTEL_*` before app code; auto-instrumentation |
| B — Manual SDK initialization | Construct `TracerProvider` in application lifecycle after YAML loads |

**Option A — Auto-instrumentation with `opentelemetry-instrument`**  
The process starts with `opentelemetry-instrument`, which initializes the SDK from `OTEL_*` **before** application code runs and auto-instruments supported libraries (FastAPI, HTTP clients, etc.).  

**Pros:** No application-level SDK setup; aligned with standard OpenTelemetry deployment; all `OTEL_*` settings applied automatically.  
**Cons:** Configuration must be available at process start; cannot be sourced from runtime-loaded LCORE YAML.

**Option B — Manual SDK initialization**  
OpenTelemetry is initialized explicitly in application lifecycle (e.g., FastAPI `lifespan`) after LCORE YAML loads. Application code constructs the `TracerProvider` and exporters.  

**Pros:** Could read export settings from YAML (Option C in Decision 1).  
**Cons:** More code to maintain; some `OTEL_*` variables must be resolved manually; diverges from upstream conventions.

**Recommendation:** **Option A.** LCORE does not construct or configure the SDK. Application code creates manual spans only. Use `OTEL_SDK_DISABLED=true` as a process-wide kill switch.

---

## Decision 3: Inbound W3C trace context

When a gateway or upstream service sends a requests LCORE with W3C headers (`traceparent`, `tracestate`), LCORE must decide whether to **continue that trace** or **start a new one**.

| Option | Description |
|--------|-------------|
| A — Default propagators | Extract `traceparent` via standard `OTEL_PROPAGATORS` |
| B — Disable propagation | Set `OTEL_PROPAGATORS=none`; standalone LCORE traces |
| C — LCORE YAML or app toggle | Custom flag in YAML or application logic |

**Option A — Accept upstream context via default propagators**  
Do not set `OTEL_PROPAGATORS` (or set it explicitly to include `tracecontext`). The OpenTelemetry SDK and FastAPI auto-instrumentation extract `traceparent` on incoming requests, so LCORE spans attach to the upstream trace.  

**Pros:** Works out of the box with gateways and service meshes; no LCORE-specific code; matches how other OpenTelemetry services behave.  
**Cons:** LCORE joins upstream traces unless the operator changes env vars.

**Option B — Disable inbound propagation**  
Set **`OTEL_PROPAGATORS=none`**. LCORE ignores `traceparent` and starts a standalone trace for every request.  

**Pros:** Useful in isolated environments or when upstream trace IDs must not flow into LCORE.  
**Cons:** Breaks end-to-end trace continuity from gateways.

**Option C — LCORE YAML or application toggle (rejected)**  
A custom flag in LCORE YAML or runtime application logic to enable/disable extraction.  

**Pros:** Propagation policy visible in LCORE config file.  
**Cons:** Duplicates `OTEL_PROPAGATORS`; adds config surface and code paths; inconsistent with an env-only tracing model if Decision 1 Option B is chosen.

**Recommendation:** **Option A** as the default deployment posture. Document **Option B** (`OTEL_PROPAGATORS=none`) for operators who need standalone traces. Reject **Option C**. B3 and other non-W3C formats are out of scope unless explicitly set via `OTEL_PROPAGATORS` per upstream documentation.

---

## Decision 4: Outbound trace context to external backends

LCORE calls external backend services (remote HTTP or in-process). A key design choice is whether those calls participate in the **same distributed trace** as LCORE or are represented differently.

| Option | Description |
|--------|-------------|
| A — Outbound W3C propagation | Inject `traceparent` on backend HTTP requests; backend spans join the LCORE trace |
| B — Backend facade spans | One LCORE span per logical backend operation; no outbound propagation |
| C — Per-integration mixed model | Propagate for remote HTTP only; different behavior for in-process backends |

**Option A — Outbound W3C propagation**  
The shared HTTP client for backend calls injects the active trace context into outgoing requests (e.g., via an `httpx` request hook or auto-instrumented client). Backend services that extract W3C context export child spans in the same trace tree.  

**Pros:** Single unified trace across LCORE and backend processes when backends are OTel-instrumented; familiar distributed-tracing model.  
**Cons:** Requires coordination with backend OTel configuration and propagation; in-process backends may not expose an HTTP inject point; library vs service deployment modes behave differently; couples LCORE observability to backend trace export.

**Option B — Backend facade spans**  
LCORE does not propagate trace context to backends. Each logical backend operation is wrapped in a **single LCORE span** whose duration covers the full round-trip (retries, streaming, in-process delegation). Backend-internal detail stays an implementation detail.  

**Pros:** Same trace shape for remote and in-process integrations; no cross-service propagation contract; backend OTel remains an independent operator concern; simpler LCORE implementation.  
**Cons:** Backend-internal spans do not appear in the LCORE trace tree; total backend latency is visible only as one span duration.

**Option C — Per-integration mixed model**  
Propagate W3C context for remote HTTP backends only; use facade spans or no propagation for in-process backends.  

**Pros:** Unified traces where HTTP propagation works; acknowledges library-mode limitations.  
**Cons:** Two behavioral paths to maintain and document; operators see different trace shapes depending on deployment mode.

**Recommendation:** **Option B.** LCORE owns the trace; backend calls are facade spans. Do not inject trace context to external backends. Document that backends may export telemetry independently.

---

## Decision 5: Export topology

| Setup | Description |
|-------|-------------|
| Direct OTLP to vendor | LCORE sends OTLP directly to the tracing backend (e.g. LangFuse) |
| Via OpenTelemetry Collector | OTLP to a collector (retries, PII scrubbing, fan-out, **file** export) |

**Recommendation:** Document both options. LCORE exports OTLP only; local file persistence is configured on the collector (`file` exporter), not in LCORE. The choice of collector, backend, or file sink is up to the deployment team.

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
