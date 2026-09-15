# Adopting a Hexagonal Architecture for Lightspeed Core Stack

*Sub-title: Incrementally moving LCORE from a mixed three-layer service to a ports-and-adapters (hexagonal) architecture that treats REST, streaming, telemetry, OKP, agents, and storage as interchangeable adapters around a stable domain.*

| Field | Value |
|-------|-------|
| **Author(s)** | Pavel Tisnovsky, Anik Bhattacharjee |
| **Author Date** | September 15, 2026 |

> **Audience & purpose.** This design doc is written for LCORE maintainers, the leads/architecture group, and adjacent teams that build on top of LCORE (OKP, RHEL Lightspeed, agent consumers etc). It describes *why* LCORE's current internal structure is becoming a drag on delivery, and *how* we propose to migrate — step by step, in the existing repository — to a hexagonal (ports-and-adapters) architecture. It is a direction-setting document, not a big-bang rewrite plan.

---

## Need

**Why do we need this? What problem does it solve?**

LCORE began life as a straightforward three-layer FastAPI service: HTTP handlers → business logic → backend (OGX/DB). That shape was appropriate when there was essentially **one actor (a REST client) and one backend**. It no longer matches reality.

Two forces have eroded the original design:

1. **The layers have blurred.** Business logic has leaked into the REST handlers, and shared logic has accreted into a large, loosely-organized `utils/` package. Concretely, in the current tree:
   - `src/app/endpoints/responses.py` is **~1,460 lines**; `a2a.py` is **~1,250 lines**; `vector_stores.py` is **~990 lines**. These are not thin HTTP adapters — they carry orchestration, provider quirks, persistence, and telemetry decisions inline.
   - A single "thin" endpoint, `src/app/endpoints/query.py`, directly imports orchestration, quota, compaction, MCP, OGX-client, token-counting, and telemetry helpers from **~15 different modules**. The HTTP concern and the domain concern are fused.
   - `src/utils/` holds **34 modules** spanning agent orchestration, compaction, quota, MCP, RAG/vector search, transcripts, token counting, and OpenAPI dumping. "utils" has become the place where domain logic goes to hide.

   The practical cost paid constantly is apparent in many different ways: 
    * it is hard to test a domain without spinning up HTTP
    * it is hard to reason about what "the business logic" even is in most cases
    * every new surface tends to copy-paste from an endpoint rather than call into a shared core.

2. **LCORE is now a multi-actor, multi-protocol service.** We already expose, or are actively building:
   - **Driving (primary) actors:** the REST API (`/v2/query`, `/v2/streaming_query`, the OpenAI-compatible Responses API), the A2A JSON-RPC protocol, and increasingly **agents as first-class callers**. Streaming responses makes the "request in, response out" assumption of a plain three-layer app inadequate.
   - **Driven (secondary) actors:** OGX, multiple databases (user, cache, quota, A2A), MCP tool servers (including **OKP**), BYOK model backends, telemetry, metrics, and shields.

   Each of these is bolted onto the domain today rather than plugged into it. Adding the next actor (e.g., a dedicated **OKP MCP adapter**, or a new streaming transport) means threading new code through existing endpoints instead of writing one self-contained adapter against a stable port.

If we do nothing, the coupling compounds. Every new protocol multiplies the surface that must know about OGX/Pydantic internals, the domain stays untestable in isolation, and onboarding cost keeps rising. 

#### The business need is **sustained delivery velocity and safe extensibility** as LCORE becomes the foundation for an agentic product line. The authors want to explicity make the distinction of this effort from a "architectural purity for its own sake" endeavor.

---

## Approach

**How we intend to address the need.**

We propose adopting **hexagonal architecture (ports and adapters)** — see Alistair Cockburn's original pattern and the practical walkthrough at <https://www.happycoders.eu/software-craftsmanship/hexagonal-architecture/> — and reaching it **incrementally, inside the current repository**. There is no new repo and no rewrite-from-scratch (see *Competition* for why).

### What we mean by "the domain"

The word *domain* is load-bearing throughout this design doc, so we define it up front. In hexagonal architecture the **domain** (also called the *application core*) is the code that captures **what LCORE actually does and the rules for doing it** — stripped of *how* it is exposed (REST, A2A, streaming) and *what* infrastructure it happens to use (OGX, SQLAlchemy, etc). Put another way: if you deleted FastAPI, swapped OGX for another backend, and changed the database, the domain is the irreducible thing LCORE still *is*.

**For LCORE, the domain is the orchestration and policy around a query.** These rules already exist today — they are just scattered across endpoint handlers and `utils/`. Consolidated into a domain, they are:

- **Query orchestration** — assemble the prompt and system prompt, gather RAG context, decide which tools are available, call the model, and turn the result into an answer. *(Today: spread across `utils/agents/`, `utils/query.py`, `utils/responses.py`, and inline in `query.py` / `responses.py`.)*
- **Conversation & compaction rules** — what a conversation / turn *is* in LCORE terms, when history is summarized, and how it folds up. *(Today: `utils/compaction.py`, `utils/conversation_compaction.py`.)*
- **Quota policy** — who may spend how many tokens, when to block a request, and how to account for usage after a call. *(Today: `quota/`, `utils/quota_utils.py`.)*
- **Shield / moderation policy** — what is allowed through and how PII is redacted.
- **RAG context assembly** — what to retrieve and how to inject it.

The domain also owns **its own models** — an LCORE `Conversation`, `Turn`, `Answer` — rather than OGX SDK objects or Pydantic request/response bodies.

Equally important is what the domain is **not**:

- **Not** the HTTP / protocol layer — that is a driving adapter.
- **Not** the OGX client or the LLM inference itself — that is a driven adapter; the actual model call happens *outside* the hexagon.
- **Not** SQLAlchemy or the database schema — driven adapter.
- **Not** Pydantic transport shapes — they are mapped to and from domain models at the boundary.

**An honest caveat.** LCORE is partly *middleware*: much of it is enterprise plumbing (auth, quota, caching, metrics) wrapped around an LLM backend that lives in OGX. A fair reviewer may ask whether LCORE has a rich domain at all, or is mostly adapters. Our position is that **the orchestration and policy described above *is* the domain**, even though the raw inference lives in OGX today as a driven adapter (and will be driven by Pydantic AI tomorrow). We state this explicitly rather than assume it, because how much genuine domain logic exists directly affects how much this restructuring buys us (see *Open Questions*).

### 1. The target shape

At the center sits the **domain** (the "application core"): the LCORE business logic — query orchestration, conversation/compaction rules, quota policy, shield/moderation policy, RAG context assembly — expressed in **plain Python and LCORE's own models**, with **no knowledge of FastAPI, OGX, SQLAlchemy, or Pydantic transport shapes**.

Around it are **ports** (interfaces the domain owns) and **adapters** (concrete implementations that speak to the outside world):

- **Driving / primary adapters** call *into* the domain through **inbound ports**: REST handlers, the A2A JSON-RPC handler, the agent-facing surface, and future streaming transports. Their only job is protocol translation — parse the request, call a domain service, serialize the result.

- **Driven / secondary adapters** are called *by* the domain through **outbound ports**: the OGX/LLM adapter, database/cache/quota persistence, MCP tool adapters (including a dedicated **OKP** adapter), BYOK, telemetry/Splunk, metrics, and shields.

![Hexagonal architecture for LCORE — the domain at the center, ports on the hexagon edges, adapters just outside, primary actors (REST API, Telemetry, Metrics) on the left and secondary actors (Database, OKP MCP, BYOK, LLMs, Agents) on the right, with the request flow crossing the boundary.](./hexagonal_architecture.svg)

Reading the diagram: a hexagon labeled *Domain/Service* sits at the center, with *Ports* on its edges and *Adapters* just outside them. **Primary actors** are on the left (REST API, Telemetry, Metrics), **secondary actors** on the right (Database, OKP MCP, BYOK, LLMs, Agents), and the *request flow* crosses the boundary through a port.

> **Note on the "hexagon".** Six sides is an aesthetic choice by the pattern's author — it does **not** cap us at six ports or six adapters. Ports can be laid out vertically and added freely; the shape carries no numeric meaning.

**Dependency rule:** dependencies point *inward*. Adapters depend on ports; the domain depends on nothing outward. Pydantic and OGX types live **in the adapter layer** and are mapped to/from LCORE's own domain models at the boundary — they must not surface through the domain or leak to callers.

### 2. Plan of execution (incremental, in-repo)

The consensus from the initial discussion was to proceed **step by step**. Proposed ordering, each step independently shippable and reviewable:

1. **Endpoint cleanup (thin the driving adapters).** Pick 1–2 endpoints (candidate: `query.py`, then `streaming_query.py`) and pull their orchestration out of the handler into a domain service the handler calls. The handler shrinks to: authn/authz wiring, request parsing, one domain call, response serialization. This establishes the "endpoints are adapters" pattern with a concrete before/after.
2. **`utils/` triage.** Classify the 34 `utils/` modules into: (a) genuine domain logic → move toward the domain/core, (b) adapter-specific logic → move next to its adapter, (c) true cross-cutting utilities → keep. This is where most hidden domain logic lives; do it gradually, module by module, alongside the endpoints that use them.
3. **First proper class-based adapter: OKP.** Build the **OKP MCP integration as the first real, self-contained adapter class** implementing an outbound "tool provider" port. This is the reference implementation other adapters copy. *(Open question below: whether OKP is its own adapter or a specialization of a general agent/tool adapter — see Key Dependencies.)*
4. **Define the outbound ports explicitly.** As OGX, persistence, telemetry, and metrics access get routed through the new services, extract their interfaces into named ports so the domain depends on abstractions, not concretions. This is where we decide how tightly to couple to OGX/Pydantic (see *Open Questions*).
5. **Define inbound ports / domain services.** Consolidate the query/streaming/conversation/quota logic into a small set of domain services with stable signatures that every driving adapter (REST, A2A, rlsapi, agents) calls the same way.
6. **Bring remaining actors onto the pattern** (A2A, rlsapi, streaming/Kafka-style transports, BYOK) as capacity allows.

### 3. Rollout & guardrails

- **Strangler-fig, not big bang.** Each step leaves the service fully working; we migrate one seam at a time behind the existing test suite. No feature freeze.
- **Tests as the safety net.** Every extraction is covered by unit tests against the newly-isolated domain service (which is the *point* — the domain becomes testable without HTTP). Existing e2e/behave scenarios guard behavior end-to-end.
- **Documentation as we go.** Formal design docs (this doc and follow-ups) record each decision so architectural questions are tracked rather than re-litigated in calls. 
- **CI/quality gates unchanged.** `uv run make format` / `verify` / `test-unit` continue to gate every PR.

---

## Benefit

Tied directly back to the *Need*:

- **The domain becomes testable in isolation.** Business rules can be unit-tested without FastAPI, OGX, or a database — directly addressing the "can't test the core without standing up HTTP" problem. Faster tests, higher confidence.
- **New actors become cheap and safe to add.** A new protocol (streaming transport, another agent surface) is a new *driving adapter* against an existing inbound port; a new backend is a new *driven adapter* against an existing outbound port. No threading logic through 1,000-line endpoint files. This is the concrete payoff for a service that is becoming multi-actor.
- **OGX/Pydantic coupling is contained.** By keeping Pydantic and OGX types behind adapters and mapping to LCORE's own models at the boundary, we keep those semantics *behind the scenes* — they don't surface to callers, and swapping/upgrading a backend is a localized change.
- **Onboarding and reasoning improve.** "Where does the business logic live?" gets a real answer (the domain), instead of "somewhere between an endpoint and `utils/`."
- **Strategic fit for agents.** The industry is shifting toward agents; a first-class **agent adapter** slots the agentic model into the service foundation rather than retrofitting it. The architecture investment is what *lets* LCORE be an agent platform, not a side-quest away from one.
- **Low disruption.** Because it's incremental and in-repo, we capture these benefits progressively — the first thinned endpoint and the OKP adapter deliver value before the full migration is done.

---

## Competition (alternatives considered)

- **Do nothing / keep the current three-layer-ish structure.** This works today. But the coupling compounds with every new actor and protocol; the endpoint files and `utils/` keep growing; the domain stays untestable in isolation; and each new surface copies from an endpoint. The *probable consequence* is steadily rising change-cost and defect risk as LCORE takes on agents and new transports. Rejected as unsustainable, not as wrong-today.
- **Rewrite from scratch in a new repository.** Tempting for a clean slate. Rejected: a parallel repo would fork effort, strand in-flight features, and force a risky cutover. The incremental in-repo path preserves working software the whole way.
- **A different clean-architecture flavor (e.g., "clean architecture" onion, or a strict DDD layering).** These are close cousins and share the dependency-inversion core. We choose the hexagonal framing because its **explicit "actors as adapters"** vocabulary maps cleanly onto LCORE's actual situation (many driving protocols, many driven backends) and onto the diagram the team has already been discussing. Attempt will be to not be dogmatic — the concrete decisions (how many ports, adapter granularity) are what matter, and those are open.
- **Only clean up `utils/` and the big endpoints, without ports/adapters.** A partial win, but without named ports we'd re-accumulate coupling — the domain would still reach directly for OGX/DB concretions. The cleanup is *step one*, not the whole answer.

---

## Non-goals

- **Not a rewrite** and **not a new repository.** Explicitly out of scope.
- **Not a change to external API contracts.** REST/A2A/rlsapi request and response shapes stay stable; this is an internal restructuring.
- **Not replacing OGX, Pydantic, FastAPI, or SQLAlchemy.** We are containing them behind adapters, not removing them, as part of this effort. Replacing OGX with Pydantic will be tracked in other efforts.
- **Not a feature freeze.** Feature work continues in parallel; migration rides alongside it via the strangler-fig approach.
- **Not prescribing the final number of ports/adapters or the exact package layout up front.** Those are decided per-step, informed by the reference OKP adapter.
- **Not a deployment/topology change.** Library mode vs. server mode, container layout, and scaling are unaffected.

---

## Key Dependencies and Open Questions

**Open questions (elephants in the room):**

1. **OKP as its own adapter vs. part of a general agent/tool adapter.** Why should OKP MCP be a separate adapter rather than a case of the general agent adapter? The authors are open to adjusting based on feedback. This design doc currently proposes OKP as the *first concrete adapter* precisely because it's a good, bounded reference — but whether it stays standalone or folds into a general tool/agent adapter is **unresolved and should be settled early**, since it shapes the port design.
2. **How tightly should the domain couple to Pydantic and OGX?** Consensus direction: Pydantic/OGX types live in the adapter layer, with LCORE domain models at the core. Open: how much mapping boilerplate is acceptable, and whether some Pydantic use in the domain is pragmatic. We must avoid Pydantic/OGX semantics leaking to users.
3. **Streaming makes hexagonal harder.** SSE today (and possibly Kafka-style/event-stream transports later) don't fit the clean "request → response" adapter shape as neatly as unary calls. We need a port abstraction for streaming/async-generator flows before migrating `streaming_query.py` and future transports. This is probably the trickiest design area.
4. **Adapter granularity and package layout.** How fine-grained should adapters be (one per protocol? per backend? per MCP server?), and what is the on-disk package structure (`domain/`, `ports/`, `adapters/`?). Deferred to the first steps + Q4 call rather than decided here.
5. **Migration sequencing vs. active feature work.** Which endpoints/utils get migrated first must not collide with in-flight feature PRs touching the same files.

**Dependencies:**

- **The OKP team** — the first adapter is OKP; alignment on its interface is a prerequisite.
- **The stakeholders / architecture group** — Direction needs stakeholder buy-in.
- **Existing test coverage** — the strangler-fig approach leans on the current unit/e2e suites as the behavioral safety net.

**Stated assumption:** that incremental refactoring can reach a coherent hexagonal target without a flag-day cutover. If a seam turns out to be non-incrementally-separable, we revisit.

---

## RACI

| Role | Who |
|------|-----|
| **Responsible** (executor) | LCORE squad; Driving the first steps (endpoint cleanup, `utils/` triage, OKP adapter) will need engineers assinged |
| **Consulted** (explicitly want feedback from) | OKP team representative, leads/architecture group, RHEL Lightspeed maintainers, Ask RedHat maintainers |
| **Informed** (should be aware) | Broader LCORE contributors; teams building on LCORE (BYOK, agent consumers); Q4 readout audience |

---

## Appendix: Evidence from the current codebase (Sep 2026)

Cited in *Need*, for reviewers who want to verify the coupling claims:

- Largest endpoint handlers (lines): `responses.py` ~1,460; `a2a.py` ~1,250; `vector_stores.py` ~990; `rlsapi_v1.py` ~890; `root.py` ~825; `conversations_v1.py` ~575; `streaming_query.py` ~508.
- `src/app/endpoints/query.py` imports domain/orchestration helpers from ~15 modules (`utils.agents.query`, `utils.conversation_compaction`, `utils.query`, `utils.quota_utils`, `utils.responses`, `client.ogx`, `authorization.azure_token_manager`, MCP helpers, OTEL tracing, …) — HTTP and domain concerns fused in one file.
- `src/utils/` contains 34 modules mixing domain logic (agents, compaction, quota, RAG/vector search, transcripts, token counting) with genuine cross-cutting utilities and OpenAPI/schema dumping.
- Current architecture overview: `docs/devel_doc/ARCHITECTURE.md` — documents today's three-layer/pipeline model this design doc evolves.
</content>
</invoke>
