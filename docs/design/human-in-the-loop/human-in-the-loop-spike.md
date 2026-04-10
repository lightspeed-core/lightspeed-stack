# Spike for Human-in-the-Loop (HIL) for MCP Tool Calling

## Overview

**The problem**: MCP tools can perform write operations (create issues, send
messages, modify data) that carry risk of unwanted changes. Currently, LCS
hardcodes `require_approval="never"` for all MCP tools, providing no mechanism
for human review before execution.

**The recommendation**: Implement asynchronous approval via a new `/approvals`
API. When a tool requires approval, LCS returns a `requires_action` status with
approval request details. Clients submit approvals via POST, and LCS continues
the agent loop. Allow/deny lists in YAML config enable permanent pre-approval
for trusted tools.

**PoC validation**: Not yet built. The core mechanism (Llama Stack approval
types) is already implemented and tested in the codebase.

## Decisions for Product/Architecture Review

These are the high-level decisions that determine scope, approach, and cost.
Each has a recommendation - please confirm or override.

### Decision 1: Approval flow model

When an MCP tool requires approval, how should LCS handle the request?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Synchronous (hold connection) | Keep HTTP connection open until approval received | Simple client integration | Timeout issues, doesn't scale |
| B. Asynchronous (separate API) | Return immediately with `requires_action`, client submits approval via `/approvals` | Scalable, supports UIs/webhooks | More complex, requires storage |

**Recommendation**: Option B (Asynchronous). This matches OpenAI's pattern for
function calling requiring action, scales better, and supports diverse client
implementations (CLI, web UI, mobile).

### Decision 2: Approval scope

What is the scope of an approval decision?

| Option | Description |
|--------|-------------|
| A. Per-user global | Once approved, tool is approved for all user conversations |
| B. Per-conversation | Approval is valid only for the current conversation |
| C. Per-request | Each tool invocation requires separate approval |

**Recommendation**: Option C (Per-request). Each tool invocation requires
explicit approval, providing maximum security and auditability. Users maintain
full control over every action taken on their behalf.

### Decision 3: Permanent allow/deny list storage

Where should permanent tool allow/deny lists be configured?

| Option | Description |
|--------|-------------|
| A. Database only | Runtime configuration, managed via API |
| B. YAML config only | Deployment-time configuration |
| C. Both | YAML baseline with database overrides |

**Recommendation**: Option B (YAML config only). Keeps security policy
declarative and auditable. Runtime overrides can be added in a future iteration
if customer demand exists.

### Decision 4: Default approval requirement

What should the default `require_approval` value be for MCP servers?

| Option | Description |
|--------|-------------|
| A. `"never"` (current behavior) | Backwards compatible, opt-in HIL |
| B. `"always"` | Secure by default, opt-out for trusted tools |

**Recommendation**: Option A (`"never"`). Maintains backwards compatibility.
Operators explicitly enable HIL for servers with write operations.

## Technical Decisions for Engineering Review

Architecture-level and implementation-level decisions.

### Decision 5: Approval request storage backend

Where should pending approval requests be stored?

| Option | Description |
|--------|-------------|
| A. In-memory only | Simple, no persistence |
| B. Existing cache backends (SQLite/PostgreSQL) | Reuse infrastructure |
| C. New dedicated store (following A2A pattern) | Clean separation |

**Recommendation**: Option B (Existing cache backends). Approval requests are
ephemeral (configurable TTL), similar to conversation cache entries. Adding a
new table to existing cache backends minimizes infrastructure changes.

See: [A2A storage pattern](../../../src/a2a_storage/context_store.py)

### Decision 6: Approval TTL configuration

How should approval request expiration be configured?

**Recommendation**: Add `approval_ttl_seconds` field to main configuration with
a default of 300 seconds (5 minutes). This is configurable per-deployment.

```yaml
# lightspeed-stack.yaml
approval_ttl_seconds: 300  # Default: 5 minutes
```

### Decision 7: Response status for pending approvals

How should LCS indicate that an approval is required?

**Recommendation**: Return HTTP 200 with response body containing:
- `status: "requires_action"` (new status value)
- `required_action.type: "mcp_approval"`
- `required_action.approvals: [...]` (list of pending approvals)

This follows the OpenAI Assistants API pattern for `requires_action` status.

### Decision 8: MCP tool annotation handling

Should LCS use MCP tool annotations (`destructiveHint`, `readOnlyHint`) to
automatically determine approval requirements?

| Option | Description |
|--------|-------------|
| A. Ignore annotations | Use only YAML config |
| B. Trust annotations | Auto-require approval for `destructiveHint=true` |
| C. Annotations as hints | Annotations inform defaults, config overrides |

**Recommendation**: Option A (Ignore annotations). MCP spec explicitly states
annotations are "untrusted hints." Security policy should be explicit in YAML,
not derived from potentially malicious MCP servers.

## Proposed JIRAs

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Add `require_approval` configuration for MCP servers

**Description**: Extend `ModelContextProtocolServer` configuration to support
`require_approval` field with values `"always"`, `"never"`, or granular
allow/deny lists per tool.

**Scope**:
- Add `require_approval` field to `ModelContextProtocolServer` in config.py
- Add `approval_ttl_seconds` to main configuration
- Add validation for the new fields
- Update configuration documentation

**Acceptance criteria**:
- [ ] `require_approval` accepts `"always"`, `"never"`, or `ApprovalFilter`
- [ ] `ApprovalFilter` supports `always` and `never` tool name lists
- [ ] `approval_ttl_seconds` defaults to 300, accepts positive integers
- [ ] Invalid configurations raise clear validation errors
- [ ] JSON schema updated for OpenAPI docs

**Agentic tool instruction**:
```text
Read the "Configuration" section in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: src/models/config.py, src/configuration.py.
```

---

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement approval request storage

**Description**: Create storage layer for pending approval requests using
existing cache backend infrastructure (SQLite/PostgreSQL).

**Scope**:
- Add `approval_requests` table to cache schemas
- Implement CRUD operations for approval requests
- Add TTL-based expiration cleanup
- Unit tests for storage operations

**Acceptance criteria**:
- [ ] Approval requests stored with: id, conversation_id, user_id, server_label, tool_name, arguments, status, created_at, expires_at
- [ ] SQLite and PostgreSQL implementations
- [ ] Expired requests cleaned up on access or via background task
- [ ] Storage operations are async

**Agentic tool instruction**:
```text
Read the "Storage / data model changes" section in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: src/cache/sqlite_cache.py, src/cache/postgres_cache.py.
```

---

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement `/approvals` API endpoints

**Description**: Create REST API endpoints for listing, viewing, and submitting
approval decisions.

**Scope**:
- `GET /approvals` - List pending approvals (filter by conversation_id)
- `GET /approvals/{id}` - Get approval request details
- `POST /approvals/{id}` - Submit approval/denial
- Authorization checks (user can only access own approvals)
- Request/response models

**Acceptance criteria**:
- [ ] Endpoints return appropriate HTTP status codes
- [ ] Authorization enforced (user scope)
- [ ] OpenAPI documentation generated
- [ ] Integration tests for happy path and error cases

**Agentic tool instruction**:
```text
Read the "API changes" section in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: src/app/endpoints/, src/models/requests.py, src/models/responses.py.
```

---

<!-- type: Story -->
<!-- key: LCORE-???? -->
### LCORE-???? Integrate approval flow into query endpoints

**Description**: Modify query and streaming_query endpoints to handle
`mcp_approval_request` events, store pending approvals, and return
`requires_action` status.

**Scope**:
- Detect `mcp_approval_request` in response stream
- Store approval request in database
- Return response with `status: "requires_action"`
- Handle approval submission and continue agent loop

**Acceptance criteria**:
- [ ] Query endpoint returns `requires_action` when approval needed
- [ ] Streaming endpoint emits approval request event
- [ ] Approval submission continues conversation
- [ ] Denied approvals handled gracefully
- [ ] Expired approvals return appropriate error

**Agentic tool instruction**:
```text
Read the "Trigger mechanism" and "API changes" sections in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: src/app/endpoints/query.py, src/app/endpoints/streaming_query.py, src/utils/responses.py.
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Wire `require_approval` to MCP tool creation

**Description**: Pass the configured `require_approval` value to
`InputToolMCP` when creating MCP tools for Llama Stack requests.

**Scope**:
- Read `require_approval` from MCP server config
- Pass to `InputToolMCP` constructor in `get_mcp_tools()`
- Handle `ApprovalFilter` translation

**Acceptance criteria**:
- [ ] `require_approval` from config passed to Llama Stack
- [ ] Default remains `"never"` when not configured
- [ ] Unit tests verify correct value propagation

**Agentic tool instruction**:
```text
Read the "Implementation Suggestions" section in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: src/utils/responses.py (get_mcp_tools function).
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add E2E tests for HIL approval flow

**Description**: Create end-to-end tests covering the full approval workflow.

**Scope**:
- Test approval required -> approval submitted -> tool executed
- Test approval denied -> graceful handling
- Test approval expired -> error response
- Test allow/deny list bypasses approval

**Acceptance criteria**:
- [ ] E2E test for approval happy path
- [ ] E2E test for denial path
- [ ] E2E test for expiration
- [ ] E2E test for allow list bypass

**Agentic tool instruction**:
```text
Read the "Test patterns" section in docs/design/human-in-the-loop/human-in-the-loop.md.
Key files: tests/e2e/features/, tests/e2e/mock_mcp_server/.
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Document HIL feature for operators and API consumers

**Description**: Create user-facing documentation for the HIL feature.

**Scope**:
- Configuration guide for operators
- API reference for `/approvals` endpoints
- Client integration examples

**Acceptance criteria**:
- [ ] Configuration examples in docs
- [ ] API usage examples
- [ ] Troubleshooting section

**Agentic tool instruction**:
```text
Read docs/design/human-in-the-loop/human-in-the-loop.md for feature details.
Reference existing docs in docs/ for style.
```

## PoC Results

No PoC was built for this spike. The core mechanisms are already validated:

1. **Llama Stack approval types exist**: `MCPApprovalRequest` and
   `MCPApprovalResponse` are defined in `llama_stack_api.openai_responses`
2. **LCS already parses approval events**: `build_tool_call_summary()` in
   [responses.py:1067-1094](../../../src/utils/responses.py#L1067-L1094) handles
   both `mcp_approval_request` and `mcp_approval_response` types
3. **Llama Stack supports `require_approval`**: The `InputToolMCP` model
   accepts `"always"`, `"never"`, or `ApprovalFilter`

The main implementation work is:
- Adding configuration
- Creating storage layer
- Building the `/approvals` API
- Wiring the approval flow into query endpoints

## Background Sections

### Current Architecture

**MCP tool creation** ([responses.py:687-744](../../../src/utils/responses.py#L687-L744)):
```python
async def get_mcp_tools(...) -> list[InputToolMCP]:
    # ...
    tools.append(
        InputToolMCP(
            type="mcp",
            server_label=mcp_server.name,
            server_url=mcp_server.url,
            require_approval="never",  # <-- Hardcoded, needs to be configurable
            # ...
        )
    )
```

**MCP server configuration** ([config.py:468-530](../../../src/models/config.py#L468-L530)):
- Currently has: `name`, `url`, `provider_id`, `authorization_headers`, `headers`, `timeout`
- Missing: `require_approval`

**Approval event handling** ([responses.py:1067-1094](../../../src/utils/responses.py#L1067-L1094)):
- Already parses `mcp_approval_request` into `ToolCallSummary`
- Already parses `mcp_approval_response` into `ToolResultSummary`
- No storage or API to act on these events

### Llama Stack Support

From `llama_stack_api.openai_responses`:

```python
class ApprovalFilter(BaseModel):
    always: list[str] | None = None  # Tools that always require approval
    never: list[str] | None = None   # Tools that never require approval

class OpenAIResponseInputToolMCP(BaseModel):
    require_approval: Literal["always"] | Literal["never"] | ApprovalFilter = "never"
    # ...

class OpenAIResponseMCPApprovalRequest(BaseModel):
    arguments: str
    id: str
    name: str
    server_label: str
    type: Literal["mcp_approval_request"]

class OpenAIResponseMCPApprovalResponse(BaseModel):
    approval_request_id: str
    approve: bool
    reason: str | None = None
    type: Literal["mcp_approval_response"]
```

### MCP Specification Context

From MCP spec research:

1. **Tool annotations** (`readOnlyHint`, `destructiveHint`, etc.) are defined
   but explicitly labeled as "untrusted hints"
2. **MCP Elicitation** is the spec's native HIL mechanism, but it's for
   server-initiated user prompts, not tool approval
3. **Best practice**: Clients should decide approval policy based on server
   trust level, not annotation values

### Alternative Considered: Synchronous Approval

A simpler approach would hold the HTTP connection open until approval is
received. This was rejected because:
- HTTP timeouts (30-60s typically) conflict with human review time
- Doesn't scale (holds server resources)
- Poor UX for mobile/web clients
- Incompatible with streaming responses

## Appendix A: Related Tickets

- **LCORE-268**: Parent feature ticket (Support HIL for write tool calling)
- **LCORE-233**: Prior demo work (Human in the Loop Demo - Closed)
- **RHAIRFE-464**: Llama Stack dependency (Allow confirmation by human - Approved)

## Appendix B: OpenAI Assistants API Reference

The proposed `requires_action` pattern follows OpenAI's Assistants API:

```json
{
  "id": "run_abc123",
  "status": "requires_action",
  "required_action": {
    "type": "submit_tool_outputs",
    "submit_tool_outputs": {
      "tool_calls": [...]
    }
  }
}
```

LCS adapts this for MCP approvals:
```json
{
  "status": "requires_action",
  "required_action": {
    "type": "mcp_approval",
    "approvals": [...]
  }
}
```
