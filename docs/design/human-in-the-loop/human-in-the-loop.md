# Feature design for Human-in-the-Loop (HIL) for MCP Tool Calling

|                    |                                           |
|--------------------|-------------------------------------------|
| **Date**           | 2026-04-01                                |
| **Component**      | MCP Tools, Query Endpoints, Configuration |
| **Authors**        | Lightspeed Core Team                      |
| **Feature**        | [LCORE-268](https://redhat.atlassian.net/browse/LCORE-268) |
| **Spike**          | [LCORE-1589](https://redhat.atlassian.net/browse/LCORE-1589) |
| **Links**          | [MCP Spec](https://modelcontextprotocol.io), [Llama Stack](https://github.com/meta-llama/llama-stack) |

## What

Human-in-the-Loop (HIL) enables human review and approval of MCP tool
invocations before execution. When a tool requires approval, LCS pauses
execution, notifies the client, and waits for an approval decision via the
`/approvals` API.

Key capabilities:
- Configure approval requirements per MCP server or per tool
- Asynchronous approval flow with configurable TTL
- Allow/deny lists for permanent pre-approval of trusted tools
- Per-request approval scope

## Why

MCP tools can perform write operations (create issues, send messages, delete
data) that carry risk of unwanted or irreversible changes. Without HIL:
- Users have no visibility into what tools will do before execution
- Automated systems can make changes without oversight
- Compliance requirements for human review cannot be met

With HIL:
- Users can review tool parameters before approving
- High-risk operations require explicit consent
- Audit trails capture approval decisions
- Trusted tools can be pre-approved to reduce friction

## Requirements

- **R1:** Operators can configure `require_approval` per MCP server with values
  `"always"`, `"never"`, or a granular allow/deny list
- **R2:** When approval is required, query endpoints return a `requires_action`
  status with approval request details
- **R3:** Clients can submit approval/denial decisions via `/approvals/{id}` API
- **R4:** Approved tool calls continue execution; denied calls are gracefully
  handled
- **R5:** Pending approval requests expire after a configurable TTL
- **R6:** Allow/deny lists enable permanent pre-approval of specific tools
- **R7:** Each tool invocation requires separate approval
- **R8:** Default behavior remains `require_approval="never"` for backwards
  compatibility

## Use Cases

- **U1:** As an operator, I want to require approval for all tools from an
  untrusted MCP server, so that users must review before execution
- **U2:** As an operator, I want to pre-approve read-only tools while requiring
  approval for write tools, so that low-risk operations don't require
  interaction
- **U3:** As a user, I want to see what a tool will do before it runs, so that
  I can prevent unwanted changes
- **U4:** As a user, I want to deny a tool invocation, so that I can stop an
  action I don't want
- **U5:** As a developer, I want approval requests to expire, so that abandoned
  sessions don't leave pending approvals indefinitely

## Architecture

### Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Request Flow                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────┐   POST /query    ┌─────────────────┐   responses.create   ┌───────────┐
│  │ Client │ ───────────────► │ LCS Query       │ ───────────────────► │ Llama     │
│  │        │                  │ Endpoint        │                      │ Stack     │
│  └────────┘                  └─────────────────┘                      └───────────┘
│       │                             │                                        │
│       │                             │ ◄─────── mcp_approval_request ─────────┤
│       │                             │                                        │
│       │                      ┌──────▼──────┐                                 │
│       │                      │ Store       │                                 │
│       │                      │ Approval    │                                 │
│       │                      │ Request     │                                 │
│       │                      └──────┬──────┘                                 │
│       │                             │                                        │
│       │ ◄─── 200 OK ────────────────┤                                        │
│       │      status: requires_action│                                        │
│       │                             │                                        │
│       │   POST /approvals/{id}      │                                        │
│       │ ────────────────────────────►                                        │
│       │      {approve: true}        │                                        │
│       │                             │                                        │
│       │                             │ ───── mcp_approval_response ──────────►│
│       │                             │                                        │
│       │                             │ ◄────── tool result + response ────────┤
│       │                             │                                        │
│       │ ◄─── 200 OK ────────────────┤                                        │
│       │      (final response)       │                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Trigger mechanism

HIL is triggered when:
1. An MCP server is configured with `require_approval != "never"`
2. The tool being invoked is not in the server's `never` list (if using
   `ApprovalFilter`)
3. Llama Stack emits an `mcp_approval_request` output item

When triggered:
1. LCS stores the approval request in the cache database
2. LCS returns HTTP 200 with `status: "requires_action"`
3. Client polls or submits approval via `/approvals/{id}`
4. On approval: LCS submits `mcp_approval_response` to Llama Stack
5. On denial: LCS submits denial and returns graceful message
6. On expiry: LCS returns error on next interaction

### Storage / data model changes

**New table: `approval_requests`**

SQLite schema:
```sql
CREATE TABLE IF NOT EXISTS approval_requests (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    user_id           TEXT NOT NULL,
    server_label      TEXT NOT NULL,
    tool_name         TEXT NOT NULL,
    arguments         TEXT NOT NULL,  -- JSON
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, denied, expired
    created_at        TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    decision_reason   TEXT,
    decided_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_conversation
    ON approval_requests(conversation_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_expires
    ON approval_requests(expires_at) WHERE status = 'pending';
```

PostgreSQL schema:
```sql
CREATE TABLE IF NOT EXISTS approval_requests (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    user_id           TEXT NOT NULL,
    server_label      TEXT NOT NULL,
    tool_name         TEXT NOT NULL,
    arguments         JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,
    decision_reason   TEXT,
    decided_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_conversation
    ON approval_requests(conversation_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_expires
    ON approval_requests(expires_at) WHERE status = 'pending';
```

### Configuration

**YAML config example:**

```yaml
# Global approval TTL (seconds)
approval_ttl_seconds: 300  # Default: 5 minutes

mcp_servers:
  # Example 1: Require approval for all tools
  - name: "untrusted-server"
    url: "https://mcp.example.com"
    require_approval: "always"

  # Example 2: Never require approval (default, backwards compatible)
  - name: "trusted-server"
    url: "https://mcp.trusted.com"
    require_approval: "never"

  # Example 3: Granular control with allow/deny lists
  - name: "github-mcp"
    url: "https://mcp.github.com"
    require_approval:
      always:
        - "create_issue"
        - "create_pull_request"
        - "delete_branch"
      never:
        - "list_repos"
        - "get_issue"
        - "search_code"
```

**Configuration class:**

```python
from typing import Literal, Optional
from pydantic import Field, model_validator
from typing_extensions import Self

class ApprovalFilter(ConfigurationBase):
    """Granular approval control for specific tools.

    Attributes:
        always: Tool names that always require approval.
        never: Tool names that never require approval.
    """

    always: list[str] = Field(
        default_factory=list,
        title="Always require approval",
        description="List of tool names that always require human approval",
    )
    never: list[str] = Field(
        default_factory=list,
        title="Never require approval",
        description="List of tool names that never require approval",
    )

    @model_validator(mode="after")
    def validate_no_overlap(self) -> Self:
        """Ensure no tool appears in both always and never lists."""
        overlap = set(self.always) & set(self.never)
        if overlap:
            raise ValueError(
                f"Tools cannot be in both always and never lists: {overlap}"
            )
        return self


class ModelContextProtocolServer(ConfigurationBase):
    """Model context protocol server configuration."""

    name: str = Field(...)
    url: str = Field(...)
    provider_id: str = Field("model-context-protocol")
    # ... existing fields ...

    require_approval: Literal["always", "never"] | ApprovalFilter = Field(
        "never",
        title="Approval requirement",
        description=(
            "When to require human approval for tool invocations. "
            "'always' requires approval for all tools, 'never' auto-approves, "
            "or use ApprovalFilter for granular control."
        ),
    )
```

### API changes

**New endpoints:**

#### GET /approvals

List pending approval requests for the authenticated user.

Query parameters:
- `conversation_id` (optional): Filter by conversation

Response (200):
```json
{
  "approvals": [
    {
      "id": "apr_abc123",
      "conversation_id": "conv_xyz",
      "server_label": "github-mcp",
      "tool_name": "create_issue",
      "arguments": {"title": "Bug report", "body": "..."},
      "status": "pending",
      "created_at": "2026-04-01T10:00:00Z",
      "expires_at": "2026-04-01T10:05:00Z"
    }
  ]
}
```

#### GET /approvals/{id}

Get a specific approval request.

Response (200):
```json
{
  "id": "apr_abc123",
  "conversation_id": "conv_xyz",
  "server_label": "github-mcp",
  "tool_name": "create_issue",
  "arguments": {"title": "Bug report", "body": "..."},
  "status": "pending",
  "created_at": "2026-04-01T10:00:00Z",
  "expires_at": "2026-04-01T10:05:00Z"
}
```

Response (404): Approval not found or not owned by user
Response (410): Approval expired

#### POST /approvals/{id}

Submit an approval decision.

Request:
```json
{
  "approve": true,
  "reason": "Looks good"
}
```

Response (200):
```json
{
  "id": "apr_abc123",
  "status": "approved",
  "decided_at": "2026-04-01T10:01:30Z"
}
```

Response (404): Approval not found or not owned by user
Response (409): Approval already decided
Response (410): Approval expired

**Modified responses:**

Query and streaming_query endpoints may return:
```json
{
  "conversation_id": "conv_xyz",
  "status": "requires_action",
  "required_action": {
    "type": "mcp_approval",
    "approvals": [
      {
        "id": "apr_abc123",
        "server_label": "github-mcp",
        "tool_name": "create_issue",
        "arguments": {"title": "Bug report", "body": "..."},
        "expires_at": "2026-04-01T10:05:00Z"
      }
    ]
  }
}
```

For streaming, emit an event:
```json
{
  "event": "approval_required",
  "data": {
    "approvals": [...]
  }
}
```

### Error handling

| Scenario | HTTP Status | Error Code | Message |
|----------|-------------|------------|---------|
| Approval not found | 404 | `approval_not_found` | Approval request not found |
| Approval expired | 410 | `approval_expired` | Approval request has expired |
| Already decided | 409 | `approval_already_decided` | Approval has already been {approved\|denied} |
| Not authorized | 403 | `forbidden` | Not authorized to access this approval |
| Invalid request | 422 | `validation_error` | Validation details |

### Security considerations

1. **Authorization**: Users can only access approvals for conversations they
   own. Approval endpoints enforce user_id matching.

2. **TTL expiration**: Pending approvals expire after configurable TTL to
   prevent indefinite resource consumption.

3. **Argument visibility**: Tool arguments are shown to users. Sensitive data
   in arguments (API keys, credentials) could be exposed. Operators should
   configure tools appropriately.

4. **Untrusted annotations**: MCP tool annotations (`destructiveHint`) are not
   used for security decisions. Approval policy is explicit in YAML config.

5. **Rate limiting**: Approval endpoints should be rate-limited to prevent
   abuse (handled by existing rate limiting infrastructure).

### Migration / backwards compatibility

- **No breaking changes**: Default `require_approval="never"` maintains current
  behavior
- **No schema migration**: New `approval_requests` table is created on first
  use
- **No API changes to existing endpoints**: New `status: "requires_action"` is
  additive

## Implementation Suggestions

### Key files and insertion points

| File | What to do |
|------|------------|
| `src/models/config.py` | Add `ApprovalFilter` class, add `require_approval` to `ModelContextProtocolServer`, add `approval_ttl_seconds` to main config |
| `src/utils/responses.py` | Modify `get_mcp_tools()` to pass `require_approval` from config |
| `src/cache/sqlite_cache.py` | Add `approval_requests` table and CRUD methods |
| `src/cache/postgres_cache.py` | Add `approval_requests` table and CRUD methods |
| `src/app/endpoints/approvals.py` | New file: `/approvals` endpoint handlers |
| `src/app/endpoints/query.py` | Handle `mcp_approval_request`, return `requires_action` |
| `src/app/endpoints/streaming_query.py` | Handle approval request events, emit `approval_required` |
| `src/models/requests.py` | Add `ApprovalDecisionRequest` model |
| `src/models/responses.py` | Add `ApprovalResponse`, `RequiresActionResponse` models |

### Insertion point detail

**get_mcp_tools() modification** ([responses.py:687-744](../../../src/utils/responses.py#L687-L744)):

```python
async def get_mcp_tools(...) -> list[InputToolMCP]:
    # ...
    for mcp_server in configuration.mcp_servers:
        # ... existing header resolution ...

        # Determine require_approval value
        require_approval = mcp_server.require_approval
        if isinstance(require_approval, ApprovalFilter):
            # Convert to Llama Stack's ApprovalFilter format
            require_approval = LlamaStackApprovalFilter(
                always=require_approval.always or None,
                never=require_approval.never or None,
            )

        tools.append(
            InputToolMCP(
                type="mcp",
                server_label=mcp_server.name,
                server_url=mcp_server.url,
                require_approval=require_approval,  # Was hardcoded "never"
                headers=headers if headers else None,
                authorization=authorization,
            )
        )
    return tools
```

**Streaming query approval handling** ([streaming_query.py:750-810](../../../src/app/endpoints/streaming_query.py#L750-L810)):

When `output_item.type == "mcp_approval_request"`:
1. Extract approval request details
2. Store in `approval_requests` table via cache backend
3. Yield `approval_required` event to client
4. Track that response is incomplete pending approval

### Config pattern

All config classes extend `ConfigurationBase` which sets `extra="forbid"`.
Use `Field()` with defaults, title, and description. Add
`@model_validator(mode="after")` for cross-field validation if needed.

Example config files go in `examples/`.

### Test patterns

- Framework: pytest + pytest-asyncio + pytest-mock. unittest is banned by ruff.
- Mock Llama Stack client: `mocker.AsyncMock(spec=AsyncLlamaStackClient)`.
- Patch at module level: `mocker.patch("utils.module.function_name", ...)`.
- Async mocking pattern: see `tests/unit/utils/test_shields.py`.
- Config validation tests: see `tests/unit/models/config/`.

**HIL-specific test considerations:**
- Mock `mcp_approval_request` events from Llama Stack
- Test approval storage CRUD operations
- Test TTL expiration logic
- Test authorization checks on approval endpoints
- E2E tests require a mock MCP server that triggers approval requests

## Open Questions for Future Work

- **Batch approvals**: Should clients be able to approve multiple tools at once?
  Deferred to future iteration based on client feedback.
- **Approval delegation**: Can users delegate approval authority to others?
  Out of scope for initial implementation.
- **Audit logging**: Should approval decisions be logged separately from
  standard request logs? Consider in observability work.
- **Runtime allow/deny management**: API to modify allow/deny lists at runtime?
  Deferred; YAML-only for initial release per Decision 3.

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-04-01 | Initial version | LCORE-1589 spike |

## Appendix A: Llama Stack Types Reference

From `llama_stack_api.openai_responses`:

```python
class ApprovalFilter(BaseModel):
    always: list[str] | None = None
    never: list[str] | None = None

class OpenAIResponseInputToolMCP(BaseModel):
    type: Literal["mcp"] = "mcp"
    server_label: str
    server_url: str | None = None
    require_approval: Literal["always"] | Literal["never"] | ApprovalFilter = "never"
    allowed_tools: list[str] | AllowedToolsFilter | None = None
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

## Appendix B: Client Integration Example

**Python client example:**

```python
import requests

# 1. Submit query
response = requests.post("/query", json={"query": "Create an issue for the bug"})
data = response.json()

# 2. Check if approval required
if data.get("status") == "requires_action":
    for approval in data["required_action"]["approvals"]:
        print(f"Tool: {approval['tool_name']}")
        print(f"Args: {approval['arguments']}")

        user_input = input("Approve? (y/n): ")

        # 3. Submit approval
        requests.post(f"/approvals/{approval['id']}", json={
            "approve": user_input.lower() == "y",
            "reason": "User decision"
        })

    # 4. Continue conversation (or re-query)
    # The next query in the same conversation will continue from where it left off
```