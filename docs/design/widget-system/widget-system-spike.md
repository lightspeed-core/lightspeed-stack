# Spike for Widget System in Lightspeed Stack

## Overview

**The problem**: Lightspeed Stack currently supports text streaming and tool-call
events, but lacks a standardized way for agents to drive rich, interactive UI
elements (forms, confirmation dialogs, data tables, charts) in the frontend.
Customers who need widget-like behavior must build bespoke solutions on top of
raw `tool_call`/`tool_result` SSE events, with no protocol-level support for
state synchronization, human-in-the-loop approvals, or structured UI rendering.
As more teams evaluate migrating to Lightspeed Stack — most immediately the PCM
team — a standardized widget system becomes a prerequisite.

**The recommendation**: Implement a new `/agui` endpoint that speaks the
[AG-UI protocol](https://docs.ag-ui.com/introduction), using
[pydantic-ai's built-in AG-UI integration](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/)
(`AGUIAdapter`). Customers provide UI-related tools through their own MCP
servers. The AG-UI protocol handles structured communication of tool calls,
state, and UI rendering data to the frontend. LCS already depends on
`pydantic-ai`; adding the `[ag-ui]` optional extra is the only new dependency
required.

**PoC validation**: Not applicable for this spike. The AG-UI protocol is a
well-established open standard with integrations from Microsoft, Google, Amazon,
and Oracle. The pydantic-ai `AGUIAdapter` is production-ready and has been
validated by [Rocket Science](https://www.copilotkit.ai/blog/introducing-pydantic-ai-integration-with-ag-ui)
in near-production deployments.

## Strategic decisions

High-level decisions that determine scope, approach, and cost. Each has a
recommendation — please confirm or override.

### Decision S1: Protocol approach for the widget system

How should Lightspeed Stack deliver structured widget events to frontends?

| Option | Description |
|--------|-------------|
| A. AG-UI protocol endpoint | New `/agui` endpoint speaking the [AG-UI protocol](https://docs.ag-ui.com/introduction) via `AGUIAdapter`. Customers define UI tools on their MCP server; the endpoint streams AG-UI events (tool calls, state sync, interrupts) to the frontend. |
| B. Reuse existing `/streaming_query` tool call events | No LCS changes. Customers catch `tool_call`/`tool_result` SSE events from `/streaming_query` and map them to widgets client-side. |

See: [Background: Option A detail](#option-a--ag-ui-protocol-endpoint-agui),
[Background: Option B detail](#option-b--reuse-streaming_query-tool-call-events).

**Recommendation**: Option A. The AG-UI protocol provides maximum flexibility
via a publicly governed, widely adopted standard. The immediate driver is
preparing for a potential PCM team migration, but additional teams will likely
need this feature. A standardized protocol avoids per-customer reinvention and
provides advanced capabilities (state sync, human-in-the-loop, frontend tools)
out of the box. See [Recommendation rationale](#recommendation-rationale) for
full trade-off analysis.

**Confidence**: 85%

### Decision S2: Endpoint design

Since AG-UI requires its own request format (`RunAgentInput` — containing
message history, frontend state, frontend tool definitions, and resume entries
for interrupts) and emits its own protocol-defined stream events (~30 event
types), how should this be exposed?

| Option | Description |
|--------|-------------|
| A. Separate `/agui` endpoint | Dedicated endpoint with its own `Action` enum value and authorization |
| B. Overload `/streaming_query` | Accept both `QueryRequest` and AG-UI `RunAgentInput` on the same path via discriminated union |

**Recommendation**: Option A. The request/response formats are fundamentally
different — AG-UI has its own lifecycle events, state management, and tool
semantics. Overloading would create a large `if/else` handler with two
incompatible response formats. Separate endpoints match how LCS already
separates protocols (A2A gets its own endpoint, rlsapi gets its own, responses
gets its own). Shared logic lives in the utility layer (`build_agent`,
`prepare_responses_params`, `apply_compaction_blocking`, etc.).

**Confidence**: 95%

### Decision S3: UI tool ownership model

Who defines and maintains the UI-related tools?

| Option | Description |
|--------|-------------|
| A. Customer MCP server | Customers register UI tools on their own MCP server, maintaining full control over tool definitions and backend logic |
| B. Built-in LCS tools | LCS ships pre-defined UI tool types (e.g., `render_form`, `show_dialog`) |
| C. Both | Built-in defaults with customer overrides via MCP |

**Recommendation**: Option A. Customer-owned MCP servers provide a safe,
isolated way for teams to implement customized backend logic. Each team's UI
needs differ — PCM needs different widgets than RHEL Lightspeed. Built-in tools
can be added in a future iteration if common patterns emerge across consumers.

**Confidence**: 80%

## Technical decisions

Architecture-level and implementation-level decisions.

### Decision T1: Integration with `AGUIAdapter`

How should the `/agui` endpoint invoke `AGUIAdapter`?

| Option | Description |
|--------|-------------|
| A. `dispatch_request()` | Single class method that takes a Starlette `Request`, parses `RunAgentInput`, runs the agent, and returns a `StreamingResponse`. Minimal code. |
| B. `from_request()` + `run_stream()` | Build the adapter from the request, then manually run the stream and encode. More control over intermediate steps. |
| C. `run_stream()` with manual parsing | Parse `RunAgentInput` manually, construct the adapter, and run. Maximum flexibility. |

See: [pydantic-ai AG-UI API reference](https://pydantic.dev/docs/ai/api/ui/ag_ui/)

**Recommendation**: Option B. `dispatch_request()` (Option A) is too opaque —
LCS needs to inject its own middleware (auth, MCP header resolution, shield
moderation, quota checks, conversation context, BYOK token refresh, compaction)
between request parsing and agent execution. Option B provides a clean split:
`from_request()` handles AG-UI protocol parsing, then LCS inserts its middleware,
then `run_stream()` executes the agent.

**Confidence**: 75% — depends on whether `AGUIAdapter` allows injecting
middleware between parsing and execution; may need to use Option C if not.

### Decision T2: Conversation mapping

How should AG-UI `threadId` map to LCS conversations?

| Option | Description |
|--------|-------------|
| A. Direct mapping | `threadId` maps directly to `conversation_id` via `normalize_conversation_id()` |
| B. Context store mapping | Use a context store (like A2A's `A2AContextStore`) to map `threadId` to `conversation_id` |

**Recommendation**: Option A. AG-UI's `threadId` serves the same purpose as
`conversation_id` in LCS. A direct mapping avoids an extra indirection layer.
The A2A endpoint uses a context store because A2A `contextId` is a separate
concept; AG-UI `threadId` is a direct conversation identifier.

**Confidence**: 70%

### Decision T3: State management scope

What LCS state (if any) should be exposed through AG-UI's state sync mechanism?

| Option | Description |
|--------|-------------|
| A. Passthrough only | LCS passes frontend state through without interpreting it; customers manage state entirely between their MCP tools and frontend |
| B. LCS-managed state | LCS populates AG-UI state with conversation metadata, tool progress, quota info, etc. |
| C. Hybrid | Passthrough by default, with optional LCS-managed fields |

**Recommendation**: Option A. State semantics are widget-specific and
customer-defined. LCS should not impose state structure. Customers define what
state means for their widgets through their MCP server tools that return
`StateSnapshotEvent` or `StateDeltaEvent` objects. Conversation metadata (ID,
model, quota) is already conveyed through other AG-UI events.

**Confidence**: 80%

### Decision T4: Telemetry approach

How should the `/agui` endpoint emit observability data?

| Option | Description |
|--------|-------------|
| A. OTEL tracing only | Add OTEL spans inline in the endpoint handler (same pattern as A2A and every other endpoint) |
| B. OTEL + Splunk telemetry | Also create a dedicated Splunk event format module |

**Recommendation**: Option A. OTEL tracing is standard across all endpoints and
is implemented inline in the handler — not a separate module. Splunk telemetry
is only implemented in 2 of ~15 endpoints (`/responses` and `/rlsapi`) and is
not required for parity. A Splunk module can be added later if the
product/analytics team requests it.

**Confidence**: 90%

## Stakeholder decisions — for PCM team

Decisions that the requesting team is uniquely positioned to weigh in on.

### Decision SH1: Frontend framework for AG-UI consumption

Which frontend framework will the PCM team (and other early consumers) use to
consume AG-UI events?

| Option | Description |
|--------|-------------|
| A. CopilotKit | Official AG-UI reference frontend; zero-effort AG-UI consumption with built-in widget rendering |
| B. Custom implementation | Parse AG-UI SSE events directly; full control, more work |
| C. Vercel AI SDK | Alternative AG-UI-compatible frontend SDK |

**Recommendation**: No recommendation from LCS side — this is a consumer
decision. LCS emits standard AG-UI events; any AG-UI-compatible frontend works.

**Confidence**: N/A

## Out of scope

What this spike deliberately does *not* address. Each item explains why it's
deferred.

- **Built-in widget tool library** — No pre-defined UI tool types shipped with
  LCS. Deferred until common patterns emerge across consumers. Each team's UI
  needs are currently too diverse to standardize.
- **Widget rendering implementation** — Frontend widget rendering is the
  customer's responsibility. LCS provides the protocol transport, not the
  rendering layer.
- **MCP server registration changes** — The existing MCP server registration
  mechanism is sufficient for UI tools. No changes needed to tool definition
  format.
- **A2UI (Google's generative UI spec) integration** — A2UI is complementary to
  AG-UI (payload vs. transport) but is too early-stage. Can be layered on top
  of AG-UI in a future iteration.

## Proposed JIRAs

Order reflects dependency / kickoff sequence.

### Epic: Implement AG-UI widget system endpoint

**Goals**:
- Expose a `/agui` endpoint that speaks the AG-UI protocol
- Integrate with all existing LCS features (auth, BYOK, MCP, conversations,
  compaction, shields, quota, telemetry)
- Enable customers to deliver agent-driven UI widgets via their MCP server tools

**Scope**:
- New endpoint, authorization action, telemetry, tests
- No changes to existing endpoints or MCP infrastructure

**Success criteria**:
- A CopilotKit (or equivalent) frontend can connect to `/agui` and render
  agent-driven widgets defined by customer MCP tools
- All existing LCS cross-cutting concerns (auth, quota, shields, conversations,
  compaction) work through the AG-UI endpoint

#### LCORE-4577 E2E feature files for AG-UI widget system (no step implementation)

**Description**: Author behave `.feature` files under `tests/e2e/features/`
that describe the behaviors required of the AG-UI widget system.

**Scope**:
- `.feature` files covering: AG-UI endpoint availability, auth, streaming
  events, tool calls via MCP, conversation persistence, shield moderation,
  quota enforcement
- Additions to `tests/e2e/test_list.txt`
- Author from spec doc requirements only; do not read implementation code

**Acceptance criteria**:
- behave parses every new `.feature` file without syntax errors
- behave marks all new scenario steps as `undefined`
- `uv run make test-e2e` remains green (new scenarios skipped/undefined, not failing)

#### LCORE-4578 Implement behave step definitions for AG-UI feature files

**Description**: Implement Python step definitions under
`tests/e2e/features/steps/` for the `.feature` files authored in the kickoff
ticket. Take the Gherkin as-is.

**Scope**:
- Step definition modules under `tests/e2e/features/steps/` covering all
  steps in the AG-UI `.feature` files
- Environment setup/teardown hooks if needed for AG-UI SSE connections
- No modifications to existing `.feature` Gherkin

**Acceptance criteria**:
- All AG-UI `.feature` scenarios pass with `uv run make test-e2e`
- No regressions in existing e2e tests
- Step definitions follow existing patterns in `tests/e2e/features/steps/`

**Blocked by**:
- LCORE-4577 (E2E feature files kickoff)
- LCORE-4576 (AG-UI endpoint implementation)

#### LCORE-4576 Implement `/agui` endpoint

**Description**: Create the core AG-UI endpoint handler in
`src/app/endpoints/agui.py`. The endpoint receives AG-UI `RunAgentInput`
requests, applies LCS middleware (auth, MCP, shields, quota, BYOK, conversation
context, compaction), runs the pydantic-ai agent via `AGUIAdapter`, and streams
AG-UI events back as SSE. This includes adding the `Action.AGUI` authorization
action to the `Action` enum.

**Scope**:
- Add `AGUI = "agui"` to `Action` enum in `src/models/config.py` (next to
  `STREAMING_QUERY`)
- Create `src/app/endpoints/agui.py` with `POST /agui` handler
- Use `AGUIAdapter.from_request()` for AG-UI protocol parsing
- Apply LCS middleware: `get_auth_dependency()`, `@authorize(Action.AGUI)`,
  `mcp_headers_dependency`, `check_mcp_auth`, `check_tokens_available`,
  `validate_model_provider_override`, `run_shield_moderation_v2`,
  `apply_compaction_blocking`
- Handle BYOK Azure token refresh (same pattern as `responses.py`)
- Build agent via `build_agent()` and `prepare_responses_params()`
- Register router in `src/app/routers.py`
- OTEL tracing following the A2A span pattern

**Acceptance criteria**:
- `Action.AGUI` is available and can be used with `@authorize(Action.AGUI)`
- Existing roles/permissions are not affected
- `POST /agui` accepts AG-UI `RunAgentInput` and returns SSE AG-UI events
- Auth, MCP, shields, quota, BYOK, conversations, compaction all function
- Unauthorized requests return 401
- Forbidden requests return 403
- Quota-exceeded requests return 429
- Unit tests cover handler, error paths, and middleware integration
- `uv run make verify` and `uv run make test-unit` pass

#### LCORE-4588 Document AG-UI widget system for operators and API consumers

**Description**: Create user-facing documentation for the AG-UI widget system
feature.

**Scope**:
- Configuration guide for operators
- API reference for `/agui` endpoint
- Client integration examples (CopilotKit, custom frontend)
- MCP server tool authoring guide for UI widgets

**Acceptance criteria**:
- Configuration examples in docs
- API usage examples with sample `RunAgentInput` payloads
- MCP tool definition examples for common widget patterns
- Troubleshooting section

## PoC results

No PoC was built for this spike. The core mechanisms are already validated:

1. **`pydantic-ai` is already a dependency**: LCS depends on `pydantic-ai`;
   adding the `[ag-ui]` optional extra is the only new dependency required
2. **`AGUIAdapter` is production-ready**: The adapter handles AG-UI protocol
   parsing, agent execution, and SSE encoding. It supports all AG-UI event types
   including state management, frontend tools, and interrupts
3. **LCS utility layer is reusable**: `build_agent()`, `prepare_responses_params()`,
   `apply_compaction_blocking()`, auth dependencies, MCP header resolution,
   shield moderation, and quota checks are all framework-agnostic and callable
   from a new endpoint
4. **A2A endpoint validates the pattern**: `src/app/endpoints/a2a.py` (~1250
   lines) demonstrates that adding a protocol adapter endpoint is a proven
   pattern in this codebase

The main implementation work is:
- Creating the `/agui` endpoint handler with LCS middleware integration
- Adding the `Action.AGUI` authorization action
- Building AG-UI-specific telemetry
- Writing unit and E2E tests

## Background sections

### Option A — AG-UI protocol endpoint (`/agui`)

AG-UI (Agent-User Interaction Protocol) is an open standard for bidirectional,
event-driven communication between AI agents and frontend applications,
developed by [CopilotKit](https://www.copilotkit.ai/ag-ui) and released in 2025.
It defines ~30 event types organized into categories:

**Lifecycle events**: `RunStarted`, `RunFinished`, `RunError`, `StepStarted`,
`StepFinished` — enable frontends to show progress indicators and handle errors.

**Text message events**: `TextMessageStart`, `TextMessageContent`,
`TextMessageEnd` — incremental text streaming (equivalent to LCS `token` events).

**Tool call events**: `ToolCallStart`, `ToolCallArgs`, `ToolCallEnd`,
`ToolCallResult` — structured tool invocation with streaming argument support.

**State management events**: `StateSnapshot`, `StateDelta` — real-time state
synchronization between agent and frontend using JSON Patch (RFC 6902).

**Reasoning events**: `ReasoningStart`, `ReasoningMessageContent`,
`ReasoningEnd` — chain-of-thought visualization.

**Sub-agent events**: `SubagentStarted`, `SubagentFinished`, `SubagentError` —
nested agent delegation with scoped state.

**Custom events**: Open-ended extension mechanism for application-specific needs.

AG-UI advanced features relevant to the widget system:

- **Frontend tool calls**: The agent can invoke tools that execute in the
  browser (render a form, open a modal, navigate). The tool definition lives on
  the customer's MCP server, but execution happens client-side, with results
  sent back via the protocol's tool result flow.
- **State synchronization (snapshot + delta)**: Shared structured state between
  agent and frontend using a snapshot-delta pattern. Widgets reflect real-time
  agent state changes without full re-fetches.
- **Predictive state updates**: State fields mapped to tool arguments so that as
  the LLM streams tool call arguments, the UI state updates in real-time before
  the tool call completes — enabling live-preview of form fills.
- **Human-in-the-loop interrupts**: Agents can pause execution and request user
  approval. The frontend renders an approval UI, the user responds, and the
  agent resumes — managed by the protocol's interrupt lifecycle.
- **Generative UI**: Agents propose declarative UI trees that the frontend
  validates and mounts, enabling constrained yet flexible agent-driven
  interfaces.
- **Sub-agent composition**: Nested delegation with scoped state, tracing, and
  cancellation for complex multi-agent widget workflows.

**Ecosystem adoption**: By 2026, AG-UI has first-party integrations with
Microsoft Agent Framework, Google ADK, AWS Bedrock AgentCore, Oracle Agent Spec,
Pydantic AI, LlamaIndex, and AG2. CopilotKit raised $27M Series A (May 2026)
tied to AG-UI adoption. The protocol is MIT-licensed.

**Pydantic-ai integration**: The `AGUIAdapter` class handles the full AG-UI
lifecycle. For FastAPI/Starlette, `dispatch_request()` is a single class method
that parses `RunAgentInput`, runs the agent, and returns a streaming response.
For more control, `from_request()` + `run_stream()` allows inserting middleware.
See [pydantic-ai AG-UI docs](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/).

**Architecture diagram**:

```
                                                     ┌──────────────────────────────┐
┌─────────────────────┐   POST /agui                 │       Lightspeed Stack       │
│                     │   (RunAgentInput)            │                              │
│   Frontend App      │ ─────────────────────────▶   │  ┌────────────────────────┐  │
│   (CopilotKit /     │                              │  │    /agui endpoint      │  │
│    custom client)   │  ◀─────────────────────────  │  │                        │  │
│                     │   SSE (AG-UI events)         │  │ ┌──────────────────┐   │  │
│  ┌───────────────┐  │     RunStarted               │  │ │  AGUIAdapter     │   │  │
│  │ Widget        │  │     TextMessageContent       │  │ │       │          │   │  │
│  │ Renderer      │  │     ToolCallStart/Args/End   │  │ │       ▼          │   │  │
│  │  (forms,      │  │     StateSnapshot/Delta      │  │ │  pydantic-ai     │   │  │
│  │   dialogs,    │  │     RunFinished              │  │ │  Agent           │   │  │
│  │   charts)     │  │                              │  │ │       │          │   │  │
│  └───────────────┘  │                              │  │ │       ▼          │   │  │
│                     │                              │  │ │  OGX (LLM)       │   │  │
└─────────────────────┘                              │  │ └──────────────────┘   │  │
                                                     │  └───────────┬────────────┘  │
                                                     │              │               │
                                                     │              ▼               │
                                                     │  ┌────────────────────────┐  │
                                                     │  │ Customer MCP Server    │  │
                                                     │  │ (UI tool definitions)  │  │
                                                     │  └────────────────────────┘  │
                                                     └──────────────────────────────┘
```

**Pros**:
- Uses a widely adopted open protocol with integrations from major cloud vendors
- LCS already depends on `pydantic-ai`; only the `[ag-ui]` optional extra
  needs to be added
- `AGUIAdapter` handles protocol parsing, agent execution, and SSE encoding
- ~30 event types covering text, tools, state, interrupts, sub-agents, reasoning
- Frontend tools, state management, and human-in-the-loop built into the spec
- Customers using CopilotKit or any AG-UI-compatible frontend get zero-effort
  widget rendering
- MCP server-based tool ownership gives customers isolated, safe backend logic
- Protocol versioning and backward compatibility handled by the AG-UI spec

**Cons**:
- Requires implementing a new endpoint (~500–800 lines) with its own
  authorization action, telemetry, and tests
- AG-UI's request format (`RunAgentInput`) differs from `QueryRequest` /
  `ResponsesRequest`, so clients must adopt a new request shape
- AG-UI's state management concepts (snapshot/delta) have no existing LCS
  equivalent — requires deciding how to handle state
- Frontends not using CopilotKit must implement AG-UI event parsing themselves

**Complexity / Impact**: Medium. Affected components: new endpoint file,
`routers.py`, `Action` enum, telemetry module, tests. Reuses all existing
infrastructure. No modifications to existing endpoints.

### Option B — Reuse `/streaming_query` tool call events

No changes to Lightspeed Stack. Customers define UI-related tools on their MCP
server (e.g., `render_form`, `show_confirmation_dialog`), and the existing
`/streaming_query` endpoint emits `tool_call` and `tool_result` SSE events
when the agent invokes those tools. Customers intercept these events in their
frontend and render the corresponding widgets.

Existing SSE events emitted by `/streaming_query`
([stream_payloads.py](../../../src/models/common/agents/stream_payloads.py)):

| Event | Payload | Purpose |
|-------|---------|---------|
| `start` | `conversation_id`, `request_id` | Stream lifecycle start |
| `token` | `id`, `token` | Incremental text delta |
| `tool_call` | `ToolCallSummary` (name, tool_call_id, arguments) | Agent invoked a tool |
| `tool_result` | `ToolResultSummary` (tool_call_id, content) | Tool returned a result |
| `turn_complete` | `id`, `token` | Full assistant text for completed turn |
| `end` | `referenced_documents`, `input_tokens`, `output_tokens` | Stream lifecycle end |
| `error` | `status_code`, `response`, `cause` | Error during stream |
| `interrupted` | `request_id` | Stream was interrupted |

**Architecture diagram**:

```
┌──────────────────────┐   POST /v1/streaming_query      ┌────────────────────────┐
│                      │   (QueryRequest)                │                        │
│   Frontend App       │ ────────────────────────────▶   │  Lightspeed Stack      │
│                      │                                 │                        │
│  ┌────────────────┐  │  ◀────────────────────────────  │  ┌──────────────────┐  │
│  │ Custom Event   │  │   SSE (existing events)         │  │ /streaming_query │  │
│  │ Parser         │  │     event: start                │  │                  │  │
│  │   │            │  │     event: token                │  │ pydantic-ai Agent│  │
│  │   ▼            │  │     event: tool_call ◀── catch  │  │       │          │  │
│  │ Widget         │  │     event: tool_result          │  │       ▼          │  │
│  │ Renderer       │  │     event: end                  │  │  OGX (LLM)       │  │
│  └────────────────┘  │                                 │  └──────┬───────────┘  │
│                      │                                 │         │              │
└──────────────────────┘                                 │         ▼              │
                                                         │  ┌──────────────────┐  │
                                                         │  │ Customer MCP     │  │
                                                         │  │ Server (UI tools)│  │
                                                         │  └──────────────────┘  │
                                                         └────────────────────────┘
```

**Pros**:
- Zero implementation effort on the Lightspeed Stack side
- No new dependencies, endpoints, or protocol adoption
- Customers already familiar with `/streaming_query` can start immediately
- MCP server-based tool ownership provides the same isolation as Option A

**Cons**:
- Every customer must build custom SSE parsing to identify UI tool calls and
  map them to widget rendering — no standard; each customer reinvents the wheel
- No state synchronization — customers must build their own state management
- No human-in-the-loop interrupt support — tool calls are fire-and-forget
- No frontend tool calls — all tools execute server-side; the agent cannot
  invoke browser-side actions
- No structured lifecycle events — the frontend cannot distinguish agent phases
  without custom conventions
- `ToolCallSummary` carries only name, tool_call_id, and arguments — no
  streaming argument support, no metadata, no UI intent signaling
- As more teams adopt this pattern, lack of standardization leads to fragmented,
  incompatible widget implementations
- No ecosystem compatibility — customers cannot use CopilotKit, Vercel AI SDK,
  or other AG-UI-compatible frontends

**Complexity / Impact**: Low (on LCS side) / Medium-High (on each customer).
No LCS changes. Each consumer bears full complexity.

### Recommendation rationale

Option A is recommended for the following reasons:

1. **Per-customer cost**: With Option B, every team needing widgets must build
   their own SSE parser, state manager, and widget-event conventions from
   scratch. With AG-UI, they adopt a documented protocol with existing frontend
   SDKs.

2. **Advanced capabilities included**: State synchronization, human-in-the-loop,
   predictive state updates, frontend tool calls, and sub-agent composition are
   part of the AG-UI spec and already implemented in `AGUIAdapter`. Building
   these on raw `tool_call` events would be significant effort per consumer.

3. **Ecosystem alignment**: AG-UI has integrations with Microsoft, Google,
   Amazon, Oracle, and frontend frameworks (CopilotKit, Vercel AI SDK). Adopting
   it positions LCS in line with industry direction.

4. **Bounded implementation cost**: LCS already depends on `pydantic-ai`;
   adding the `[ag-ui]` extra is trivial. The endpoint reuses all existing LCS
   infrastructure. Net-new code
   is the endpoint handler, an `Action` enum value, telemetry builders, and
   tests — estimated ~2-3 weeks for one developer.

**Trade-offs**:
- Customers must adopt the AG-UI request format (`RunAgentInput`) instead of
  `QueryRequest`, but this is a one-time cost offset by richer capabilities
- The AG-UI protocol is governed by CopilotKit (MIT-licensed, $27M Series A
  funding) — an external dependency, mitigated by open-source governance and
  wide adoption
- The `/agui` endpoint is purely additive — no regression risk to existing
  consumers

## Glossary

- **AG-UI**: Agent-User Interaction Protocol — open standard for bidirectional
  communication between AI agents and frontend applications
- **RunAgentInput**: AG-UI protocol's request format containing message history,
  frontend state, frontend tool definitions, and resume entries for interrupts
- **AGUIAdapter**: Pydantic-ai class that bridges pydantic-ai agents to the
  AG-UI protocol
- **Frontend tool**: A tool defined on the MCP server but executed in the
  browser — the agent invokes it, the frontend runs it, and the result flows
  back through the protocol
- **State snapshot/delta**: AG-UI's state sync mechanism — full snapshots for
  initialization, JSON Patch deltas for incremental updates
- **PCM**: The team driving the immediate need for this feature

## Appendix A — External references

- [AG-UI Protocol Overview](https://docs.ag-ui.com/introduction)
- [AG-UI Protocol Events](https://docs.ag-ui.com/concepts/events)
- [AG-UI GitHub Repository](https://github.com/ag-ui-protocol/ag-ui)
- [CopilotKit AG-UI](https://www.copilotkit.ai/ag-ui)
- [Pydantic AI AG-UI Integration Guide](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/)
- [Pydantic AI AG-UI API Reference](https://pydantic.dev/docs/ai/api/ui/ag_ui/)
- [Pydantic AI AG-UI Examples](https://pydantic.dev/docs/ai/examples/ag-ui/)
- [AG-UI State Management — Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/ui/ag-ui/state-management)
- [AG-UI + Pydantic AI Announcement (CopilotKit Blog)](https://www.copilotkit.ai/blog/introducing-pydantic-ai-integration-with-ag-ui)
