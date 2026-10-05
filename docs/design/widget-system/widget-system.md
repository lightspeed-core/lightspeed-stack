# Feature design for Widget System (AG-UI Protocol)

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-10-05                                |
| **Component**      | Core / Endpoints / Configuration          |
| **Authors**        | Chih-Tao Lee                              |
| **Feature**        | [LCORE-4575](https://redhat.atlassian.net/browse/LCORE-4575) |
| **Spike**          | [LCORE-4288](https://redhat.atlassian.net/browse/LCORE-4288) |
| **Links**          | [AG-UI Protocol](https://docs.ag-ui.com/introduction), [pydantic-ai AG-UI](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/) |

## What

A new `/agui` endpoint that speaks the
[AG-UI (Agent-User Interaction) protocol](https://docs.ag-ui.com/introduction),
enabling agents to drive rich, interactive UI widgets (forms, confirmation
dialogs, data tables, charts) in customer frontends. The endpoint uses
[pydantic-ai's built-in AG-UI integration](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/)
(`AGUIAdapter`) to translate agent execution into AG-UI protocol events streamed
as SSE.

Customers define UI-related tools on their own MCP servers. The AG-UI protocol
handles structured delivery of tool calls, state synchronization, and rendering
data to the frontend. All existing LCS cross-cutting concerns — authentication,
authorization, BYOK, MCP, conversations, conversation compaction, shields,
quota, and telemetry — are integrated into the new endpoint.

Key capabilities:
- Streaming agent responses as AG-UI protocol events (~30 event types)
- Frontend tool calls — agent invokes browser-side actions defined via MCP
- State synchronization between agent and frontend (snapshot + delta)
- Human-in-the-loop interrupts — agent pauses for user approval, resumes on
  response
- Predictive state updates — UI updates in real-time as tool arguments stream
- Sub-agent composition with scoped state and tracing
- Custom events for application-specific widget behavior

## Why

Today, Lightspeed Stack has limited options for agent-driven UI:
- `/streaming_query` emits raw `tool_call`/`tool_result` SSE events that
  customers can intercept, but there is no standard for interpreting them as
  widgets
- No protocol-level support for state synchronization, human-in-the-loop
  approvals, or structured UI rendering
- Each customer that needs widget-like behavior must build a bespoke solution

This creates problems as more teams evaluate migrating to Lightspeed Stack:
- **Per-customer reinvention**: Each team builds its own SSE parser, state
  manager, and widget-event conventions from scratch
- **No ecosystem compatibility**: Customers cannot use off-the-shelf AG-UI
  frontends (CopilotKit, Vercel AI SDK)
- **Missing capabilities**: No frontend tool calls, no state sync, no
  interrupt/resume — these would require significant per-customer engineering

The AG-UI protocol solves these by providing a standardized, widely adopted
event vocabulary that any compatible frontend can consume. The immediate driver
is preparing for a potential PCM team migration, but the design accommodates any
team needing agent-driven UI in the future.

## Requirements

- **R1:** A new `POST /agui` endpoint accepts AG-UI `RunAgentInput` requests
  and returns SSE-formatted AG-UI protocol events
- **R2:** The endpoint integrates with existing LCS authentication via
  `get_auth_dependency()` and a new `Action.AGUI` authorization action
- **R3:** MCP tools (including customer-defined UI tools) are resolved via
  existing `mcp_headers_dependency` and `resolve_tool_choice()` mechanisms
- **R4:** Conversations are supported via AG-UI `threadId` mapped to LCS
  `conversation_id`
- **R5:** Conversation compaction is applied via `apply_compaction_blocking()`
  before inference when the conversation approaches the context window limit
- **R6:** Shield moderation is applied to user input via
  `run_shield_moderation_v2()` before inference
- **R7:** Token quota is checked via `check_tokens_available()` before inference
- **R8:** BYOK (Azure Entra ID) token refresh is handled when the selected
  model is Azure-hosted
- **R9:** AG-UI state is passed through to customer MCP tools without LCS
  interpretation — customers manage state entirely between their tools and
  frontend
- **R10:** OTEL tracing spans are emitted for the AG-UI request lifecycle
- **R11:** The endpoint is registered in `routers.py` without a version prefix
  (same pattern as A2A)

## Use Cases

- **U1:** As a PCM team developer, I want to connect my CopilotKit frontend to
  Lightspeed Stack so that my agent can render interactive widgets defined by my
  MCP server tools
- **U2:** As an LS app team, I want to define UI tools on my MCP server so that
  the agent can invoke them and the frontend renders the appropriate widgets
- **U3:** As a user, I want the agent to pause and ask for my approval before
  performing a destructive action, so that I can review and confirm
- **U4:** As a frontend developer, I want to receive structured AG-UI events so
  that I can render agent tool calls as interactive UI components without
  building custom SSE parsing logic
- **U5:** As an operator, I want the `/agui` endpoint to respect the same
  auth, quota, and shield policies as other endpoints so that security is
  consistent

## Architecture

### Overview

```text
                                                    ┌──────────────────────────────┐
┌─────────────────────┐   POST /agui                │       Lightspeed Stack       │
│                     │   (RunAgentInput)           │                              │
│   Frontend App      │ ─────────────────────────▶  │  ┌────────────────────────┐  │
│   (CopilotKit /     │                             │  │    /agui endpoint      │  │
│    custom client)   │  ◀───────────────────────── │  │                        │  │
│                     │   SSE (AG-UI events)        │  │ ┌──────────────────┐   │  │
│  ┌───────────────┐  │     RunStarted              │  │ │  AGUIAdapter     │   │  │
│  │ Widget        │  │     TextMessageContent      │  │ │       │          │   │  │
│  │ Renderer      │  │     ToolCallStart/Args/End  │  │ │       ▼          │   │  │
│  │  (forms,      │  │     StateSnapshot/Delta     │  │ │  pydantic-ai     │   │  │
│  │   dialogs,    │  │     RunFinished             │  │ │  Agent           │   │  │
│  │   charts)     │  │                             │  │ │       │          │   │  │
│  └───────────────┘  │                             │  │ │       ▼          │   │  │
│                     │                             │  │ │  OGX (LLM)       │   │  │
└─────────────────────┘                             │  │ └──────────────────┘   │  │
                                                    │  └───────────┬────────────┘  │
                                                    │              │               │
                                                    │              ▼               │
                                                    │  ┌────────────────────────┐  │
                                                    │  │ Customer MCP Server    │  │
                                                    │  │ (UI tool definitions)  │  │
                                                    │  └────────────────────────┘  │
                                                    └──────────────────────────────┘
```

### Request flow

```text
  ┌─────────────────────┐
  │ POST /agui          │  RunAgentInput (AG-UI protocol request)
  │ (RunAgentInput)     │  Contains: messages, state, frontend tools, threadId
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Auth + Authorize    │  get_auth_dependency() + @authorize(Action.AGUI)
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Parse AG-UI input   │  AGUIAdapter.from_request() → RunAgentInput
  │                     │  Extract threadId → conversation_id
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ LCS middleware      │  check_mcp_auth()
  │                     │  check_tokens_available()
  │                     │  validate_model_provider_override()
  │                     │  run_shield_moderation_v2()
  │                     │  Azure Entra ID token refresh (if BYOK)
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Resolve context     │  resolve_response_context() or direct conversation lookup
  │                     │  prepare_responses_params()
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Compaction          │  apply_compaction_blocking() if conversation
  │                     │  is approaching context window limit
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Build + run agent   │  build_agent() with MCP tools + frontend tools
  │                     │  AGUIAdapter.run_stream()
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Stream AG-UI events │  SSE response: RunStarted, TextMessage*,
  │                     │  ToolCall*, StateSnapshot/Delta, RunFinished
  └──────────┬──────────┘
             │
             ▼
  ┌─────────────────────┐
  │ Post-stream         │  Persist conversation turn (if store=true)
  │                     │  Emit OTEL telemetry
  │                     │  Consume quota tokens
  └─────────────────────┘
```

### Endpoint implementation

The `/agui` endpoint lives in `src/app/endpoints/agui.py`. It follows the A2A
endpoint pattern — a protocol adapter that reuses LCS utility functions for
all cross-cutting concerns.

```python
"""Handler for AG-UI (Agent-User Interaction) protocol endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.responses import Response

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from models.config import Action
from utils.mcp.mcp_headers import McpHeaders, mcp_headers_dependency

router = APIRouter(tags=["agui"])


@router.post(
    "/agui",
    summary="AG-UI Protocol Endpoint",
)
@authorize(Action.AGUI)
async def agui_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> Response:
    """Handle AG-UI protocol requests.

    Receives an AG-UI RunAgentInput, applies LCS middleware (auth, MCP,
    shields, quota, BYOK, conversation context, compaction), runs the
    pydantic-ai agent via AGUIAdapter, and streams AG-UI events as SSE.
    """
    # 1. Parse AG-UI request
    # 2. Apply LCS middleware (auth, MCP, shields, quota, BYOK)
    # 3. Resolve conversation context from threadId
    # 4. Apply compaction if needed
    # 5. Build agent via build_agent() + prepare_responses_params()
    # 6. Run via AGUIAdapter and stream response
    # 7. Post-stream: persist turn, emit telemetry, consume quota
    ...
```

**Note**: The endpoint handler accepts a raw `Request` rather than a typed
Pydantic model because `AGUIAdapter.from_request()` parses the AG-UI
`RunAgentInput` from the request body internally. LCS middleware is inserted
between parsing and agent execution.

### Authorization

Add `AGUI` to the `Action` enum in `src/models/config.py`:

```python
class Action(StrEnum):
    # ... existing actions ...

    # Access the streaming query endpoint
    STREAMING_QUERY = "streaming_query"

    # Access the AG-UI protocol endpoint
    AGUI = "agui"
```

### Router registration

Register in `src/app/routers.py` without a version prefix, following the A2A
pattern:

```python
from app.endpoints import (
    agui,
    # ... existing imports ...
)

def include_routers(app: FastAPI) -> None:
    # ... existing routers ...

    # AG-UI (Agent-User Interaction) protocol endpoint
    app.include_router(agui.router)
```

### Conversation mapping

AG-UI `threadId` maps directly to LCS `conversation_id` via
`normalize_conversation_id()`. This is a direct mapping — no intermediate
context store is needed (unlike A2A which uses `A2AContextStore` because A2A
`contextId` has different semantics).

```python
adapter = await AGUIAdapter.from_request(request, agent=agent)
conversation_id = normalize_conversation_id(adapter.conversation_id)
```

When `threadId` is `None` (first turn), a new conversation is created via the
standard `prepare_responses_params()` flow.

### MCP tool integration

MCP tools are resolved through the existing mechanism. The endpoint calls
`prepare_responses_params()` which internally resolves MCP tools via
`resolve_tool_choice()`. These tools are passed to `build_agent()` and become
available to the pydantic-ai agent alongside any frontend tools provided in the
AG-UI `RunAgentInput`.

Frontend tools from `RunAgentInput` are handled by `AGUIAdapter` — they are
converted to pydantic-ai tools and merged with the server-side MCP tools
automatically. When the agent invokes a frontend tool, `AGUIAdapter` emits
`ToolCallStart`/`ToolCallArgs`/`ToolCallEnd` events; the frontend executes the
tool and submits results in the next request.

### State management

AG-UI state is passed through without LCS interpretation (Decision T3 from
spike). Customers manage state entirely between their MCP server tools and
their frontend.

The `AGUIAdapter` handles state automatically:
- `RunAgentInput.state` is available to tools via `StateDeps`
- Tools can return `StateSnapshotEvent` or `StateDeltaEvent` objects to push
  state changes to the frontend
- State deltas use JSON Patch (RFC 6902) for efficient incremental updates

LCS does not populate, validate, or interpret the state. Conversation metadata
(ID, model, quota) is conveyed through other mechanisms (AG-UI lifecycle events,
response headers).

#### Limitation: AG-UI state is not forwarded to MCP servers

AG-UI state and MCP tools live in different layers. State is available to local
pydantic-ai tools (Python functions decorated with `@agent.tool`) via
`ctx.deps.state`, but MCP tools are remote — they are invoked via the MCP
protocol, which only transmits `tool_name` + `arguments`. There is no
side-channel to pass AG-UI state to an MCP server automatically.

Customers who need their MCP-hosted UI tools to access AG-UI state have two
options:

1. **Design MCP tool arguments to include needed state.** The LLM sees the
   AG-UI state (it is part of the agent context) and can pass relevant parts as
   tool call arguments. This relies on the LLM correctly forwarding state
   fields, which can be guided via system prompt instructions or tool parameter
   descriptions.

2. **Use AG-UI frontend tools instead of MCP tools.** For tools that primarily
   read or write UI state (e.g., updating a form, toggling a panel), define
   them as AG-UI frontend tools (executed in the browser) rather than MCP
   tools. Frontend tools have direct access to the shared state via the AG-UI
   protocol — no forwarding needed.

Note: a local pydantic-ai tool bridge (reading `ctx.deps.state` and calling
the MCP server programmatically) is not feasible in LCS's architecture.
Customers provide tools via MCP servers — they do not control agent
construction or register local Python tools. There is no mechanism to inject
a local tool wrapper into the agent built by `build_agent()`.

Customers should choose based on their use case: option 1 for simple cases
where the LLM can reliably pass state, and option 2 when the tool logic is
primarily UI-side.

### BYOK (Azure Entra ID)

Azure token refresh follows the same 5-line pattern as `responses.py`:

```python
if (
    model.startswith("azure")
    and AzureEntraIDManager().is_entra_id_configured
    and AzureEntraIDManager().is_token_expired
    and AzureEntraIDManager().refresh_token()
):
    client = await AsyncOgxClientHolder().update_azure_token()
```

This is applied after model selection and before agent construction.

### Shield moderation

User input text is extracted from the AG-UI `RunAgentInput` messages and passed
through `run_shield_moderation_v2()` before inference. If moderation blocks the
request, the endpoint emits a `RunError` AG-UI event with the refusal message
instead of running the agent.

### Conversation compaction

Compaction is applied via `apply_compaction_blocking()` before inference, the
same function used by both the `/responses` and A2A endpoints. The AG-UI
endpoint operates in the same mode as A2A — blocking compaction with no
client-side progress event, since AG-UI has its own lifecycle signaling.

### Telemetry

OTEL spans follow the A2A pattern and are implemented inline in the endpoint
handler (not a separate module):

| Span | Attributes | Purpose |
|------|------------|---------|
| `agui.handle_request` | `user_id`, `input`, `session_id` | Root span for the request |
| `agui.execute` | `tool_calls_count`, `tool_calls_names` | Agent execution |
| `llm.inference` | `model_id`, `provider_id`, `input_tokens`, `output_tokens` | LLM call |

Splunk telemetry is not included in the initial implementation. Only 2 of ~15
endpoints (`/responses` and `/rlsapi`) currently emit Splunk events. A Splunk
event format module can be added later if the product/analytics team requests
it.

### Error handling

| Scenario | AG-UI behavior | HTTP status |
|----------|----------------|-------------|
| Auth failure | No AG-UI stream; standard HTTP error | 401 |
| Authorization denied | No AG-UI stream; standard HTTP error | 403 |
| Quota exceeded | No AG-UI stream; standard HTTP error | 429 |
| Shield blocked | `RunError` event in stream with refusal message | 200 (stream) |
| Model not found | No AG-UI stream; standard HTTP error | 404 |
| OGX unavailable | `RunError` event in stream | 200 (stream) |
| Agent runtime error | `RunError` event in stream | 200 (stream) |
| Context window exceeded | `RunError` event in stream | 200 (stream) |

Errors that occur before the SSE stream starts (auth, quota, model resolution)
return standard HTTP error responses. Errors that occur during streaming are
emitted as AG-UI `RunError` events within the stream — this is consistent with
AG-UI protocol semantics where errors during a run are part of the event stream.

### Migration / backwards compatibility

- **No breaking changes**: The `/agui` endpoint is purely additive
- **No modifications to existing endpoints**: `/streaming_query`, `/responses`,
  and A2A continue to work unchanged
- **New dependency**: `pydantic-ai[ag-ui]` extra must be added to
  `pyproject.toml` (the base `pydantic-ai` is already a dependency)
- **New authorization action**: `Action.AGUI` must be granted to roles that
  need access; existing roles are unaffected

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `pyproject.toml` | Change `pydantic-ai==2.27.1` to `pydantic-ai[ag-ui]==2.27.1` |
| `src/models/config.py` | Add `AGUI = "agui"` to `Action` enum (next to `STREAMING_QUERY`) |
| `src/app/endpoints/agui.py` | New file: AG-UI endpoint handler |
| `src/app/routers.py` | Import and register `agui.router` (no version prefix) |
| `src/constants.py` | Add `ENDPOINT_PATH_AGUI` constant |

### Insertion point detail

**Action enum** (`src/models/config.py`, next to `STREAMING_QUERY`):

```python
# Access the streaming query endpoint
STREAMING_QUERY = "streaming_query"

# Access the AG-UI protocol endpoint
AGUI = "agui"
```

**Router registration** (`src/app/routers.py`):

```python
from app.endpoints import (
    agui,
    # ... existing ...
)

def include_routers(app: FastAPI) -> None:
    # ... existing routers ...

    # A2A (Agent-to-Agent) protocol endpoint
    app.include_router(a2a.router)

    # AG-UI (Agent-User Interaction) protocol endpoint
    app.include_router(agui.router)
```

**Dependency change** (`pyproject.toml`):

```toml
# Before
"pydantic-ai==2.27.1",

# After
"pydantic-ai[ag-ui]==2.27.1",
```

### Reference patterns

| Concern | Reference file | What to reuse |
|---------|---------------|---------------|
| Protocol adapter endpoint | `src/app/endpoints/a2a.py` | Overall structure: auth, agent build, stream conversion, telemetry |
| LCS middleware integration | `src/app/endpoints/responses.py` | Shield moderation, BYOK, compaction, model selection, quota |
| Agent construction | `src/utils/pydantic_ai_helpers.py` | `build_agent()`, `captured_output_items()` |
| Response params | `src/utils/responses.py` | `prepare_responses_params()` |
| Compaction | `src/utils/conversation_compaction.py` | `apply_compaction_blocking()` |
| Conversation persistence | `src/utils/conversations.py` | `append_turn_items_to_conversation()` |
| Telemetry format | `src/observability/formats/responses.py` | Event builder pattern |
| OTEL spans | `src/utils/otel_tracing.py` | `SpanAttributes`, `SpanEvents`, `set_span_attributes()` |

### Test patterns

- Framework: pytest + pytest-asyncio + pytest-mock
- Mock OGX client: `mocker.AsyncMock(spec=AsyncOgxClient)`
- Auth mock: `MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")`
- Async tests: use `pytest.mark.asyncio` marker

**AG-UI-specific test considerations:**
- Mock `AGUIAdapter.from_request()` to return controlled adapter instances
- Test middleware integration (auth, MCP, shields, quota) independently
- Test conversation mapping from `threadId` to `conversation_id`
- Test error paths: auth failure, quota exceeded, shield blocked, OGX
  unavailable
- E2E tests: POST AG-UI `RunAgentInput` and verify SSE event stream contains
  expected AG-UI event types

## Open Questions for Future Work

- **Built-in widget tool library**: Should LCS ship pre-defined UI tool types
  (e.g., `render_form`, `show_dialog`) as a convenience? Deferred until common
  patterns emerge across consumers.
- **A2UI integration**: Google's A2UI generative UI spec is complementary to
  AG-UI (payload vs. transport). Can be layered on top in a future iteration.
- **AG-UI WebSocket transport**: The initial implementation uses SSE. AG-UI also
  supports WebSocket transport for bidirectional communication. Consider if
  latency-sensitive use cases require it.
- **State persistence**: Should LCS persist AG-UI state across sessions (beyond
  what the conversation cache provides)? Deferred — customers manage state via
  their MCP tools.

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-10-05 | Initial version | Widget system spike |

## Appendix A: AG-UI Event Types Reference

The AG-UI protocol defines ~30 event types organized into categories. The full
list is documented at [docs.ag-ui.com/concepts/events](https://docs.ag-ui.com/concepts/events).

| Category | Events | Purpose |
|----------|--------|---------|
| Lifecycle | `RunStarted`, `RunFinished`, `RunError`, `StepStarted`, `StepFinished` | Run lifecycle management |
| Text | `TextMessageStart`, `TextMessageContent`, `TextMessageEnd`, `TextMessageChunk` | Incremental text streaming |
| Tool calls | `ToolCallStart`, `ToolCallArgs`, `ToolCallEnd`, `ToolCallResult`, `ToolCallChunk` | Tool invocation with streaming args |
| State | `StateSnapshot`, `StateDelta`, `MessagesSnapshot` | State synchronization (JSON Patch) |
| Activity | `ActivitySnapshot`, `ActivityDelta` | Structured activity rendering |
| Reasoning | `ReasoningStart`, `ReasoningMessageStart`, `ReasoningMessageContent`, `ReasoningMessageEnd`, `ReasoningEnd`, `ReasoningEncryptedValue` | Chain-of-thought visualization |
| Sub-agents | `SubagentStarted`, `SubagentFinished`, `SubagentError` | Nested agent delegation |
| Special | `Raw`, `Custom` | Passthrough and extension events |

## Appendix B: AG-UI `RunAgentInput` Structure

`RunAgentInput` is the AG-UI protocol's request format, provided by the
`ag-ui-protocol` package. Key fields as surfaced by `AGUIAdapter`:

| Field | Maps to | Purpose |
|-------|---------|---------|
| `threadId` | `AGUIAdapter.conversation_id` → LCS `conversation_id` | Conversation identifier |
| `runId` | `AGUIEventStream.run_id` | Protocol run identifier |
| `messages` | `AGUIAdapter.messages` (converted to pydantic-ai `ModelMessage`) | Conversation history |
| `state` | `AGUIAdapter.state` | Frontend state dictionary |
| Frontend tools | `AGUIAdapter.toolset` | Frontend-defined tools |
| `resume` | `AGUIAdapter.deferred_tool_results` | Interrupt resume entries (approve/deny/edit) |

## Appendix C: Comparison with Existing Protocol Endpoints

| Aspect | `/v1/streaming_query` | A2A (`/a2a`) | AG-UI (`/agui`) |
|--------|----------------------|--------------|-----------------|
| Protocol | Custom LCS SSE | A2A (JSON-RPC) | AG-UI (SSE) |
| Request model | `QueryRequest` | A2A JSON-RPC | `RunAgentInput` |
| Event types | 8 (token, tool_call, etc.) | A2A task events | ~30 AG-UI events |
| Frontend tools | No | No | Yes |
| State sync | No | No | Yes (snapshot + delta) |
| Human-in-the-loop | No | No | Yes (interrupt/resume) |
| Conversation | `conversation_id` param | `contextId` → store | `threadId` → direct |
| Target consumer | LCS-native clients | Other agents | Frontend apps |
| Agent construction | `build_agent()` | `build_agent()` | `build_agent()` |
| MCP tools | `resolve_tool_choice()` | `prepare_responses_params()` | `prepare_responses_params()` |
| Compaction | `apply_compaction()` | `apply_compaction_blocking()` | `apply_compaction_blocking()` |
