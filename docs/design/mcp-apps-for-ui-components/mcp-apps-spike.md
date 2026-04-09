# Spike for MCP Apps Integration

## Overview

**The problem**: Lightspeed Core Stack currently supports MCP tool calling but tools return only text/JSON results. Complex data like Kubernetes cluster metrics, real-time dashboards, or cost analysis are returned as "text walls" that are difficult to visualize. The [MCP Apps extension](https://modelcontextprotocol.io/docs/extensions/apps) (announced January 26, 2026) enables MCP servers to return interactive UI components (charts, tables, dashboards) that render directly in conversation streams, but llama-stack (the intermediary layer) lacks two critical APIs: (1) Resources API to fetch UI components, and (2) Tool Invocation API for bidirectional communication.

**The recommendation**: Contribute both APIs to llama-stack (via [issue #5430](https://github.com/llamastack/llama-stack/issues/5430) for Resources API and [issue #5512](https://github.com/llamastack/llama-stack/issues/5512) for Tool Invocation), then integrate into Lightspeed by fetching UI resources inline during query processing and exposing `/v1/tools/invoke` for direct tool calls. This approach minimizes custom code in Lightspeed while providing MCP Apps support to the broader llama-stack community.

**PoC validation**: Successfully tested MCP integration with kubernetes-mcp-server. No PoC built for UI resource fetching yet - blocked on llama-stack Resources API implementation.

## Decisions for Product Owner

These are the high-level decisions that determine scope, approach, and cost. Each has a recommendation — please confirm or override.

### Decision 1: Which implementation approach for MCP Apps support?

When a tool declares a UI resource via `_meta.ui.resourceUri`, how should Lightspeed fetch and return it?

| Option | Description | Complexity | Dependency |
|--------|-------------|------------|------------|
| **A** | Extend llama-stack Resources API, integrate in Lightspeed | Low (Lightspeed), Medium (llama-stack) | External (llama-stack maintainers) |
| **B** | Direct MCP protocol implementation in Lightspeed | High | None |
| **C** | Hybrid: Metadata only, client fetches directly | Medium | None |

See [Background: Design alternatives](#design-alternatives) for full pros/cons.

**Recommendation**: **Option A** (Extend llama-stack). Maintains architectural separation, provides value to broader community, leverages existing MCP infrastructure in llama-stack. Requires coordination with llama-stack maintainers but avoids duplicating complex MCP protocol logic.

### Decision 2: UI resource delivery - separate endpoint vs inline?

How should UI resource HTML be delivered to clients?

| Approach | Flow | Round trips | Complexity |
|----------|------|-------------|------------|
| **Inline** | Fetch during query, include in response | 1 | Low |
| **Separate endpoint** | Return metadata, client fetches HTML separately | 2 | Medium |

**Recommendation**: **Inline fetching**. Client receives tool result and UI HTML in one response, eliminating extra endpoint, authentication handling, and latency. Simpler client implementation.

### Decision 3: Tool definition cache invalidation strategy?

Tool definitions contain `_meta.ui.resourceUri` metadata. When should the cache refresh?

| Strategy | Trigger | Pros | Cons |
|----------|---------|------|------|
| **On-demand** | Every `/v1/tools` call | Always fresh, simple | Higher latency on tools list endpoint |
| **TTL-based** | Refresh if cache older than N seconds | Lower latency | May serve stale data |
| **Manual** | Admin API `/v1/tools/refresh` | Full control | Requires intervention |
| **Webhook** | MCP server notifies on changes | Instant updates | Not standard MCP feature |

See [Background: Cache invalidation](#cache-invalidation-analysis) for full analysis.

**Recommendation**: **On-demand refresh**. `/v1/tools` already fetches fresh data from llama-stack, so cache update adds minimal overhead. Guarantees no stale `_meta.ui` references. Tools endpoint is not latency-sensitive (called once per session).

## Technical Decisions

Architecture-level and implementation-level decisions.

### Decision 4: Where to store UI resource HTML?

After fetching from llama-stack, should we cache the HTML content?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** | No caching, fetch every time | Simple, always fresh | Extra llama-stack call per query |
| **B** | Cache in conversation cache | Reduces calls | UI resources rarely reused across queries |
| **C** | Short-lived in-memory cache | Handles rerenders | Complexity for minimal benefit |

**Recommendation**: **A** (no caching). UI resources are tool-specific and typically rendered once per tool invocation. Caching adds complexity without meaningful performance gain. If needed later, can add as optimization.

### Decision 5: Error handling for UI resource fetch failures?

What if `client.resources.read()` fails during query processing?

| Option | Behavior |
|--------|----------|
| **A** | Fail entire query | User sees error, no partial result |
| **B** | Log warning, omit `ui_resource` field | Tool result still returned, just no UI |
| **C** | Retry with backoff | Adds latency |

**Recommendation**: **B** (graceful degradation). Tool result is still valuable without the UI component. Log the failure for debugging. Client can still render the text/JSON result.

### Decision 6: MCP server URL resolution for resource fetching?

When building `build_tool_call_summary()`, how do we determine which MCP server to fetch the UI resource from?

| Option | Description |
|--------|-------------|
| **A** | Infer from tool name prefix | Assumes naming convention |
| **B** | Store in tool metadata during cache | Requires schema change |
| **C** | Pass from query endpoint | Available from existing context |

**Recommendation**: **C**. MCP server URL is already known in the query flow context. Pass it to `build_tool_call_summary()` as a parameter.

### Decision 7: Bidirectional communication handling?

MCP Apps UIs communicate bidirectionally with the host via postMessage. Where does this communication happen?

| Component | Role |
|-----------|------|
| **Lightspeed-stack** | Delivers HTML content in response, then done (stateless) |
| **Client application** | Renders iframe, handles ALL postMessage communication |

**Key Clarification:** Lightspeed-stack is **NOT involved** in bidirectional communication. This happens entirely client-side.

**Flow:**
1. Client sends query → Lightspeed returns HTML in `ui_resource.content`
2. Client renders iframe with HTML
3. Client sends tool result to iframe via postMessage (client-side only)
4. If UI calls a tool → Client makes NEW `POST /v1/tools/invoke` to Lightspeed
5. Client sends new result to iframe (client-side only)

**Why this matters:**
- Lightspeed-stack remains stateless (no WebSocket, no SSE to clients)
- Clients must implement postMessage handling (using `@modelcontextprotocol/ext-apps` library)
- Tool calls from UI use direct invocation endpoint `/v1/tools/invoke` (not `/v1/query`)
- Direct invocation is deterministic, fast, and token-free (see [llama-stack issue #5512](https://github.com/llamastack/llama-stack/issues/5512))

**Recommendation**: Document this clearly so clients know they're responsible for postMessage implementation. See design doc section 3.1 for full architecture.

### Decision 8: Client compatibility - how to handle CLI vs web clients?

Lightspeed-stack serves multiple client types with different UI capabilities:

| Client | Interface | Can Render MCP Apps? |
|--------|-----------|---------------------|
| OpenShift Lightspeed | Web (Console) | ✅ Yes |
| Ansible Lightspeed | Web/VS Code | ✅ Probably |
| RHEL Lightspeed | CLI (terminal) | ❌ No (text-only) |

**Problem:** CLI clients cannot render HTML/iframes. What do we do with `ui_resource` field?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A** | Always include `ui_resource` | Simple, no negotiation needed, graceful degradation | Wastes bandwidth for CLI clients |
| **B** | Conditional via header (`X-MCP-Apps-Support: true`) | No wasted bandwidth, explicit capability | Adds complexity, requires client changes |
| **C** | Configuration-based per client | Admin control | Requires client identification mechanism |

**Analysis:**

**Option A (Always Include):**
- CLI clients simply ignore `ui_resource` field (JSON spec allows this)
- Tool result `content` always present (CLI gets usable text)
- No capability negotiation needed
- HTML content is small (~10-50KB), bandwidth not a concern
- Future-proof: clients can opt-in without server changes

**Option B (Header-based):**
```http
POST /v1/query
X-MCP-Apps-Support: true
```
- Lightspeed only includes `ui_resource` if header present
- Saves bandwidth but adds conditional logic
- Requires updating all web clients to send header

**Option C (Config-based):**
- Admin configures which client types get `ui_resource`
- Requires client identification (User-Agent? API key?)
- Less flexible than per-request headers

**Recommendation**: **Option A** (Always include `ui_resource`)

**Rationale:**
- **Simplicity**: No capability negotiation in v1
- **Backward compatible**: Existing clients ignore unknown fields
- **Graceful degradation**: CLI clients use `content`, web clients use `ui_resource`
- **Bandwidth**: 10-50KB HTML not a bottleneck (tool results can be much larger)
- **Progressive enhancement**: Web clients get richer UX without breaking CLI

**Client behavior:**
```python
# Web client - renders UI
if response.tool_results[0].ui_resource:
    render_iframe(ui_resource.content)
else:
    display_text(tool_results[0].content)

# CLI client - ignores UI
print(response.tool_results[0].content)  # ui_resource ignored
```

**Future enhancement:** If bandwidth becomes an issue, add `X-MCP-Apps-Support` header in v2 without breaking changes.

## Proposed JIRAs

Each JIRA includes an agentic tool instruction pointing to the spec doc (not this spike).

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement llama-stack Resources API for MCP Apps support

**Description**: Implement the Resources API in llama-stack as proposed in [issue #5430](https://github.com/llamastack/llama-stack/issues/5430). This adds `list_mcp_resources()` and `read_mcp_resource()` functions that leverage the existing MCP Python SDK (v1.23.0+) to fetch UI resources from MCP servers.

**Scope**:

- Add `list_mcp_resources()` function to `src/llama_stack/providers/utils/tools/mcp.py`
- Add `read_mcp_resource()` function to handle `ui://` URI fetching
- Create API models in `llama_stack_api/resources/`: `Resource`, `ListResourcesResponse`, `ReadResourceResponse`
- Implement `ModelContextProtocolResourcesImpl` provider
- Add FastAPI routes: `/v1/resources/list` and `/v1/resources/read`
- Handle both text (HTML) and binary resources with base64 encoding
- Add unit tests for resource functions
- Add integration tests with test MCP server
- Update llama-stack documentation

**Acceptance criteria**:

- `list_mcp_resources()` returns list of resources from MCP server
- `read_mcp_resource(uri="ui://server/path")` returns HTML content
- Binary resources are base64-encoded in response
- OAuth/Bearer token authentication works (reusing existing MCP auth logic)
- Unit tests cover success and error cases
- Integration test with real MCP server verifies end-to-end flow
- PR submitted to llama-stack repository and merged

**Agentic tool instruction**:

```text
Read the full implementation proposal in https://github.com/llamastack/llama-stack/issues/5430.

Key files to create/modify in llama-stack repo:
- src/llama_stack/providers/utils/tools/mcp.py (add functions)
- src/llama_stack_api/resources/models.py (new file)
- src/llama_stack_api/resources/api.py (new file)
- src/llama_stack/providers/remote/resources/model_context_protocol.py (new file)
- src/llama_stack_api/resources/fastapi_routes.py (new file)

The MCP SDK already supports resources API:
  await session.list_resources()
  await session.read_resource(uri)

Just need to expose this via llama-stack's HTTP API.

To verify:
1. Start test MCP server with @mcp.resource() decorator
2. Call POST /v1/resources/read with mcp_endpoint and uri
3. Verify HTML content returned in response
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement llama-stack Tool Invocation API for MCP Apps bidirectional communication

**Description**: Implement direct tool invocation endpoint in llama-stack as proposed in [issue #5512](https://github.com/llamastack/llama-stack/issues/5512). This enables MCP Apps UIs to call tools programmatically without LLM overhead, supporting bidirectional communication.

**Scope**:

- Expose existing `invoke_tool()` method from `ToolRuntime` protocol as HTTP endpoint
- Add FastAPI route `POST /v1/tools/invoke` to `llama_stack_api/tools/fastapi_routes.py`
- Create request/response models: `InvokeToolRequest`, `InvokeToolResponse`
- Pass through authorization headers to tool runtime
- Handle errors gracefully (return error in response, not HTTP 500)
- Add unit tests for endpoint
- Add integration tests with MCP server
- Update llama-stack documentation

**Acceptance criteria**:

- `POST /v1/tools/invoke` endpoint accepts `tool_name` and `arguments`
- Endpoint calls `ToolRuntimeRouter.invoke_tool()` internally
- Response includes `result` field with tool output
- Authorization headers passed through to MCP servers
- Error responses include descriptive `error` field
- Unit tests cover success and error cases
- Integration test verifies end-to-end tool invocation
- PR submitted to llama-stack repository and merged

**Agentic tool instruction**:

```text
Read the full implementation proposal in https://github.com/llamastack/llama-stack/issues/5512.

Key files to create/modify in llama-stack repo:
- src/llama_stack_api/tools/models.py (add InvokeToolRequest, InvokeToolResponse)
- src/llama_stack_api/tools/fastapi_routes.py (add POST /tools/invoke route)
- src/llama_stack_api/tools/api.py (update if needed)

The internal invoke_tool() method already exists in ToolRuntimeRouter.
Just need to expose it via HTTP endpoint.

To verify:
1. Start llama-stack with test MCP server
2. Call POST /v1/tools/invoke with tool_name and arguments
3. Verify result returned in response
4. Test with invalid tool name, verify error field populated
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Upgrade llama-stack dependencies to version with Resources API and Tool Invocation

**Description**: Upgrade `llama-stack` and `llama-stack-client` dependencies to the version that includes Resources API and Tool Invocation API support. This unblocks MCP Apps implementation in Lightspeed.

**Scope**:

- Update `pyproject.toml` with new llama-stack version
- Run `uv sync` to update lockfile
- Verify no breaking changes in existing MCP tool calling
- Update any code affected by API changes (if any)
- Run full test suite (unit, integration, E2E)

**Acceptance criteria**:

- `pyproject.toml` specifies llama-stack version with Resources API and Tool Invocation API
- `client.resources` attribute exists and is callable
- `client.tools.invoke` method exists and is callable
- All existing tests pass (no regressions)
- `uv run make verify` passes (linters)

**Agentic tool instruction**:

```text
Read the "Phase 1: Llama Stack Upgrade" section in docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files: pyproject.toml.

Steps:
1. Update llama-stack and llama-stack-client versions
2. Run: uv sync
3. Run: uv run make test-unit && uv run make test-integration
4. Fix any breaking changes (check llama-stack changelog)
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement ToolDefinitionCache for storing tool metadata

**Description**: Create a singleton cache to store tool definitions including `_meta.ui` fields. This cache enables looking up UI resource URIs when building tool result summaries.

**Scope**:

- Create `src/utils/tool_cache.py` with `ToolDefinitionCache` class
- Implement `update_from_toolgroups()` to populate cache from llama-stack response
- Implement `get_tool_metadata()` to retrieve tool definition by name
- Implement `get_last_update()` to track cache freshness
- Implement `clear()` for testing

**Acceptance criteria**:

- `ToolDefinitionCache()` returns same instance (singleton)
- `update_from_toolgroups()` correctly extracts tool metadata including `_meta` fields
- `get_tool_metadata("tool_name")` returns tool definition or `None`
- Unit tests cover all public methods
- Type annotations complete (pyright passes)

**Agentic tool instruction**:

```text
Read the "Tool Definition Cache" section in docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to create: src/utils/tool_cache.py.

Follow the Singleton pattern from src/utils/types.py.
The cache schema is shown in the design doc section 1.3.

To verify:
1. Instantiate cache twice, verify same instance
2. Call update_from_toolgroups() with mock data
3. Call get_tool_metadata(), verify returned data matches
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Update /v1/tools endpoint to populate tool cache

**Description**: Modify the `/v1/tools` endpoint to refresh the `ToolDefinitionCache` on every request, implementing the on-demand cache invalidation strategy.

**Scope**:

- Import `ToolDefinitionCache` in `src/app/endpoints/tools.py`
- After `client.toolgroups.list()` call, invoke `cache.update_from_toolgroups()`
- Ensure cache is updated before response is returned
- No change to response model (cache is internal)

**Acceptance criteria**:

- Every `GET /v1/tools` call refreshes the cache
- Cache contains all tools with their `_meta` fields
- Existing functionality unchanged (response model same)
- Integration test verifies cache is populated after tools list

**Agentic tool instruction**:

```text
Read the "Phase 2: Response Enrichment - Step 1" section in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to modify: src/app/endpoints/tools.py.

Insertion point: After line where client.toolgroups.list() is called.
Add: ToolDefinitionCache().update_from_toolgroups(toolgroups_response.data)

To verify:
1. Start lightspeed-stack
2. Call GET /v1/tools
3. Check logs for cache update (add debug log)
4. Verify cache contains tool metadata
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Extend ToolResultSummary model with ui_resource field

**Description**: Add `UIResourceMetadata` model and extend `ToolResultSummary` to include an optional `ui_resource` field containing full HTML content and metadata.

**Scope**:

- Add `UIResourceMetadata` class to `src/utils/types.py` with fields: `resource_uri`, `server_name`, `content`, `mime_type`, `is_binary`
- Add `ui_resource: Optional[UIResourceMetadata]` field to `ToolResultSummary`
- Update `src/models/responses.py` if needed
- Update OpenAPI examples to show ui_resource field

**Acceptance criteria**:

- `UIResourceMetadata` class has all required fields with correct types
- `ToolResultSummary.ui_resource` is optional (defaults to `None`)
- Pydantic validation passes for all field types
- `uv run make verify` passes (type checking)
- OpenAPI spec reflects new field

**Agentic tool instruction**:

```text
Read the "Data Model Changes - 1.1 UI Resource Metadata" section in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to modify: src/utils/types.py, src/models/responses.py.

The exact schema is provided in the design doc.
Follow existing Pydantic patterns in the codebase.

To verify:
1. Create a UIResourceMetadata instance with test data
2. Create a ToolResultSummary with ui_resource field populated
3. Serialize to JSON, verify all fields present
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement inline UI resource fetching in build_tool_call_summary

**Description**: Modify `build_tool_call_summary()` in `src/utils/responses.py` to detect tools with `_meta.ui.resourceUri`, fetch UI resource HTML from llama-stack's Resources API, and include it in the `ToolResultSummary`.

**Scope**:

- Modify `build_tool_call_summary()` signature to accept `tool_cache` and `mcp_server_url` parameters
- After building standard `ToolResultSummary`, check tool cache for `_meta.ui` field
- If `resourceUri` present, call `await client.resources.read()` to fetch HTML
- Handle errors gracefully (log warning, omit ui_resource if fetch fails)
- Populate `ui_resource` field with full HTML content

**Acceptance criteria**:

- Tool results with `_meta.ui.resourceUri` include `ui_resource` field in response
- Tool results without `_meta.ui` omit `ui_resource` field (remains `None`)
- Fetch failures logged but don't break query response
- Unit tests cover both success and failure cases
- Integration test with real MCP server verifies HTML content returned

**Agentic tool instruction**:

```text
Read the "Phase 2: Response Enrichment - Step 2: Implementation Example" section in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to modify: src/utils/responses.py (build_tool_call_summary function).

The code example is provided in the design doc. Key points:
1. Add tool_cache and mcp_server_url parameters
2. Check tool_cache.get_tool_metadata() for _meta.ui
3. Call client.resources.read() with mcp_endpoint and resource_uri
4. Wrap in try/except to handle failures gracefully

To verify:
1. Start kubernetes-mcp-server with a tool that has _meta.ui
2. Send query that invokes the tool
3. Verify response includes ui_resource with HTML content
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Wire tool cache and MCP server URL through query flow

**Description**: Update the query flow to pass `tool_cache` and `mcp_server_url` parameters through to `build_tool_call_summary()` so UI resources can be fetched during response building.

**Scope**:

- Modify `build_turn_summary()` to accept and pass `tool_cache` parameter
- Modify `prepare_responses_params()` to extract MCP server URL from configuration
- Pass MCP server URL through to `build_tool_call_summary()`
- Update both `/v1/query` and `/v1/streaming_query` endpoints

**Acceptance criteria**:

- `build_tool_call_summary()` receives non-None `tool_cache` and `mcp_server_url`
- MCP server URL correctly resolved from configuration
- Both streaming and non-streaming endpoints work
- All existing tests pass (no regressions)

**Agentic tool instruction**:

```text
Read the "Phase 2: Response Enrichment" section in docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to modify: src/utils/responses.py, src/app/endpoints/query.py, src/app/endpoints/streaming_query.py.

Threading the parameters:
1. In query.py and streaming_query.py: Get tool_cache instance and mcp_server_url
2. Pass to build_turn_summary()
3. In build_turn_summary(): Pass to build_tool_call_summary()

MCP server URL is available in configuration.mcp_servers (match by server name).

To verify: Run integration test that exercises full query flow with MCP tool.
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add unit tests for tool cache and UI resource enrichment

**Description**: Write comprehensive unit tests for `ToolDefinitionCache` and the UI resource enrichment logic in `build_tool_call_summary()`.

**Scope**:

- Create `tests/unit/utils/test_tool_cache.py`
  - Test singleton behavior
  - Test update_from_toolgroups() with various tool metadata
  - Test get_tool_metadata() with existing and missing tools
  - Test cache invalidation (clear and refresh)
- Update `tests/unit/utils/test_responses.py`
  - Test build_tool_call_summary() with tool that has ui_resource
  - Test build_tool_call_summary() with tool without ui_resource
  - Test graceful degradation when resources.read() fails

**Acceptance criteria**:

- All new tests pass
- Code coverage for tool_cache.py >= 80%
- Mock `client.resources.read()` in unit tests (no real MCP calls)
- Tests follow existing pytest patterns in codebase

**Agentic tool instruction**:

```text
Read the "Testing Strategy - Unit Tests" section in docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to create: tests/unit/utils/test_tool_cache.py.
Key files to modify: tests/unit/utils/test_responses.py.

Follow existing test patterns:
- Use pytest fixtures from conftest.py
- Use mocker.AsyncMock for llama-stack client
- Check MOCK_AUTH pattern in existing test files

To verify: uv run make test-unit
Coverage target: 80% for new code
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add integration tests for MCP Apps end-to-end flow

**Description**: Write integration tests that verify the complete MCP Apps flow: tool execution, UI resource fetching, and response enrichment with inline HTML content.

**Scope**:

- Create integration test in `tests/integration/endpoints/test_query_mcp_apps.py`
- Use real MCP server (or mock SSE server simulating MCP Apps)
- Verify tool result includes `ui_resource` field with HTML content
- Verify tools without `_meta.ui` don't include `ui_resource`
- Test both `/v1/query` and `/v1/streaming_query` endpoints

**Acceptance criteria**:

- Integration test creates MCP server with UI-capable tool
- Test sends query that invokes the tool
- Test asserts response includes `ui_resource.content` with HTML
- Test verifies `ui_resource.mime_type` is "text/html"
- Test coverage >= 10% (per project standards)

**Agentic tool instruction**:

```text
Read the "Testing Strategy - Integration Tests" section in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to create: tests/integration/endpoints/test_query_mcp_apps.py.

Use tests/common/mcp.py helper:
- make_mcp_server() to create test MCP server with @mcp.resource() decorator
- Follow pattern from existing integration tests

To verify: uv run make test-integration
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Add E2E tests for MCP Apps using behave

**Description**: Create end-to-end behavioral tests using behave framework that verify MCP Apps functionality from a user perspective.

**Scope**:

- Create `tests/e2e/features/mcp_apps.feature` with Gherkin scenarios
- Implement step definitions in `tests/e2e/features/steps/`
- Test scenarios:
  1. Query tool with UI resource returns inline HTML
  2. Query tool without UI resource omits ui_resource field
- Use real kubernetes-mcp-server or test MCP server

**Acceptance criteria**:

- Feature file follows Gherkin syntax
- All scenarios pass when run with `uv run make test-e2e`
- Step definitions reuse existing common steps where possible
- Tests added to `tests/e2e/test_list.txt`

**Agentic tool instruction**:

```text
Read the "Testing Strategy - E2E Tests" section in docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to create: tests/e2e/features/mcp_apps.feature, tests/e2e/features/steps/mcp_apps_steps.py.

Follow existing behave patterns:
- See tests/e2e/features/query.feature for examples
- Reuse steps from tests/e2e/features/steps/common.py
- Add new test to tests/e2e/test_list.txt

To verify: uv run make test-e2e
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Update OpenAPI specification with MCP Apps changes

**Description**: Update the OpenAPI spec to reflect new `UIResourceMetadata` and `ToolResultSummary.ui_resource` fields, including examples showing MCP Apps responses.

**Scope**:

- Update `docs/openapi.json` (or regenerate from code if auto-generated)
- Add schema definition for `UIResourceMetadata`
- Update `ToolResultSummary` schema with `ui_resource` field
- Add example response showing tool result with ui_resource
- Verify spec passes OpenAPI validation

**Acceptance criteria**:

- OpenAPI spec includes `UIResourceMetadata` schema
- `ToolResultSummary` shows `ui_resource` as optional field
- Example responses demonstrate MCP Apps use case
- Spec passes validation (e.g., via Swagger validator)

**Agentic tool instruction**:

```text
Read the "API Specification - Modified Query Response" section in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to modify: docs/openapi.json.

If OpenAPI spec is auto-generated from code:
1. Run the generation command (check Makefile or docs)
2. Verify new fields appear in spec

If manually maintained:
1. Add UIResourceMetadata schema definition
2. Update ToolResultSummary to include ui_resource field
3. Add example from design doc section 3

To verify: Validate spec with Swagger Editor or similar tool.
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Implement /v1/tools/invoke endpoint for direct tool invocation

**Description**: Add `POST /v1/tools/invoke` endpoint to lightspeed-stack that enables direct tool invocation for MCP Apps bidirectional communication. This endpoint passes through to llama-stack's tool invocation API.

**Scope**:

- Create request model `InvokeToolRequest` in `src/models/requests.py` with fields: `tool_name`, `arguments`
- Create response model `InvokeToolResponse` in `src/models/responses.py` with fields: `tool_name`, `result`, `error`
- Add `POST /tools/invoke` endpoint to `src/app/endpoints/tools.py`
- Apply `@authorize(Action.INVOKE_TOOL)` decorator for RBAC
- Accept and pass through MCP headers via `mcp_headers_dependency`
- Call `client.tools.invoke()` with tool name, arguments, and MCP headers
- Handle errors gracefully (return error in response, not HTTP exception)
- Add OpenAPI response documentation

**Acceptance criteria**:

- `POST /v1/tools/invoke` endpoint accepts JSON body with `tool_name` and `arguments`
- Endpoint requires authentication (same as `/v1/query`)
- RBAC enforces `INVOKE_TOOL` action permission
- MCP headers (OAuth, Bearer tokens) passed through to llama-stack
- Successful invocation returns tool result in response
- Failed invocation returns descriptive error message (not HTTP 500)
- OpenAPI spec includes new endpoint with examples
- `uv run make verify` passes

**Agentic tool instruction**:

```text
Read the "Direct Tool Invocation Endpoint" section (3.4) and "Implementation Roadmap - Step 3"
in docs/design/mcp-apps-for-ui-components/mcp-apps.md.

Key files to create/modify:
- src/models/requests.py (add InvokeToolRequest)
- src/models/responses.py (add InvokeToolResponse)
- src/app/endpoints/tools.py (add invoke_tool_endpoint function)
- src/models/config.py (add Action.INVOKE_TOOL if needed)

The endpoint implementation is shown in the design doc. Key points:
1. Use existing patterns from query.py (auth, mcp_headers, client access)
2. Call await client.tools.invoke(tool_name=..., arguments=..., extra_headers=...)
3. Wrap in try/except to return errors gracefully

To verify:
1. Start lightspeed-stack with kubernetes-mcp-server
2. Call POST /v1/tools/invoke with tool_name="list_namespaces" and arguments={}
3. Verify result contains namespace list
4. Test with invalid tool name, verify error field populated
```

---

<!-- type: Task -->
<!-- key: LCORE-???? -->
### LCORE-???? Document MCP Apps feature and client integration guide

**Description**: Create user-facing documentation explaining MCP Apps support, how to enable it, and how clients should handle `ui_resource` fields in responses and implement bidirectional communication.

**Scope**:

- Create `docs/features/mcp-apps.md` with:
  - Overview of MCP Apps extension
  - How Lightspeed supports UI resources
  - Example response with ui_resource field
  - Client implementation guide (rendering HTML in sandboxed iframe)
  - Bidirectional communication via `/v1/tools/invoke` endpoint
  - Security considerations for rendering untrusted HTML
- Update main README or feature index to link to MCP Apps docs

**Acceptance criteria**:

- Documentation includes complete example with request and response
- Security guidelines cover iframe sandboxing
- Link to MCP Apps official docs for reference
- Documentation passes markdown linting

**Agentic tool instruction**:

```text
Read the "Summary", "API Specification", and "Bidirectional Communication" sections in
docs/design/mcp-apps-for-ui-components/mcp-apps.md.
Key files to create: docs/features/mcp-apps.md.

Include:
1. Feature overview
2. Example response showing ui_resource field
3. Client rendering guide (sandboxed iframe pattern from section 4)
4. Bidirectional communication via POST /v1/tools/invoke
5. Example client code for handling tool calls from UI
6. Link to https://modelcontextprotocol.io/docs/extensions/apps

Follow existing docs/ structure and markdown style.

To verify: uv run make verify (checks markdown linting)
```

## Background

### Design alternatives

Based on research of llama-stack architecture, MCP Apps specification, and existing MCP integration in Lightspeed, three design approaches were considered:

**Option A: Extend llama-stack with Resources API (Recommended)**

Contribute Resources API support to llama-stack (proposed via [issue #5430](https://github.com/llamastack/llama-stack/issues/5430)), then integrate in Lightspeed by calling `client.resources.read()`.

| Pros | Cons |
|------|------|
| Minimal custom code in Lightspeed | Depends on llama-stack maintainer acceptance |
| Maintains architectural layer separation | Timeline uncertain (external dependency) |
| Reuses existing MCP session management | Must wait for release |
| Benefits broader llama-stack community | Requires coordination |
| Leverages MCP SDK (v1.23.0+) already has resources support | |

**Option B: Direct MCP protocol implementation**

Bypass llama-stack, implement MCP client directly in Lightspeed for resource fetching.

| Pros | Cons |
|------|------|
| Full control, no external dependency | High complexity (SSE, postMessage, protocol) |
| Can optimize for Lightspeed use cases | Duplicates llama-stack functionality |
| Immediate implementation | Maintenance burden (keep sync with MCP spec) |
| | Breaks architectural separation |

**Option C: Metadata only, client-side fetching**

Return only `ui_resource.resource_uri` metadata, clients fetch HTML directly from MCP servers.

| Pros | Cons |
|------|------|
| Minimal Lightspeed changes | Clients must implement MCP protocol |
| Lazy loading of UI resources | Auth complexity (clients need MCP credentials) |
| Client controls caching | Inconsistent client implementations |
| | Exposes MCP server URLs to clients |

**Verdict**: Option A provides the best balance of architectural cleanliness, community benefit, and long-term maintainability, despite the external dependency risk.

### Cache invalidation analysis

Tool definitions contain `_meta.ui.resourceUri` that must be cached for lookup during response building. Cache invalidation strategies considered:

| Strategy | Mechanism | Freshness | Complexity | Overhead |
|----------|-----------|-----------|------------|----------|
| On-demand | Refresh on every `/v1/tools` call | Always fresh | Low | Minimal (already fetching from llama-stack) |
| TTL-based | Refresh if cache age > N seconds | Eventually consistent | Medium | Timer/timestamp management |
| Manual | Admin API endpoint `/v1/tools/refresh` | Stale until manual trigger | Medium | Requires human intervention |
| Webhook | MCP server push notifications | Real-time | High | Not standard MCP feature |

**Analysis**:

- **On-demand** wins because `/v1/tools` already calls `client.toolgroups.list()` which fetches fresh data from llama-stack. The cache update adds negligible overhead (in-memory dict write). Tools endpoint is called once at session start, not latency-sensitive.
- **TTL-based** adds complexity (timers, race conditions) for minimal benefit. Risk of serving stale `_meta.ui` references if MCP server changes tool definitions.
- **Manual** requires operational overhead and creates risk of stale cache if forgotten.
- **Webhook** not supported by MCP protocol - would require custom extension.

**Verdict**: On-demand refresh is simplest, safest, and sufficient for the use case.

### MCP Apps protocol overview

From [official MCP Apps documentation](https://modelcontextprotocol.io/docs/extensions/apps):

1. **Tool declares UI via metadata**:
   ```json
   {
     "name": "visualize_data",
     "_meta": {
       "ui": {
         "resourceUri": "ui://charts/interactive"
       }
     }
   }
   ```

2. **Resources API**: MCP servers expose `resources/list` and `resources/read` operations
3. **UI content**: HTML/JavaScript fetched via `ui://` URI scheme
4. **Rendering**: Clients render in sandboxed iframes
5. **Communication**: bidirectional postMessage JSON-RPC protocol

**MCP Python SDK support** (v1.23.0+):
```python
from mcp import ClientSession

async with session:
    # List resources
    resources = await session.list_resources()

    # Read resource content
    content = await session.read_resource("ui://server/dashboard")
```

llama-stack just needs to expose this existing SDK functionality via its API.

## PoC Results

**Completed**: MCP integration testing with kubernetes-mcp-server

- Successfully registered MCP server in `lightspeed-stack.yaml`
- Documented 21 Kubernetes tools discovered via `list_mcp_tools`
- Verified proper authentication (SSE endpoint: `http://localhost:8081/sse`)


**Not completed**: UI resource fetching PoC

- Blocked on llama-stack Resources API implementation
- Issue filed: [llama-stack#5430](https://github.com/llamastack/llama-stack/issues/5430)
- Cannot proceed until llama-stack releases Resources API support

**Important divergences from production design**:

N/A - no PoC built for UI resources yet. 

## Appendix A: llama-stack Resources API proposal

Full proposal submitted as [llama-stack issue #5430](https://github.com/llamastack/llama-stack/issues/5430).

**Key implementation points**:

1. **New functions in `src/llama_stack/providers/utils/tools/mcp.py`**:
   - `list_mcp_resources()` - discover UI resources from MCP server
   - `read_mcp_resource()` - fetch HTML content via `ui://` URI

2. **New API models in `llama_stack_api/resources/`**:
   - `Resource(BaseModel)` - resource metadata
   - `ListResourcesResponse` - list operation response
   - `ReadResourceResponse` - read operation response with content

3. **New provider**: `ModelContextProtocolResourcesImpl`
   - Leverages existing MCP SDK: `session.list_resources()`, `session.read_resource()`
   - Handles OAuth/Bearer tokens same as existing tool implementation

4. **FastAPI routes**:
   - `POST /v1/resources/list` - list resources from MCP server
   - `POST /v1/resources/read` - read resource by URI

**Timeline**: Pending llama-stack maintainer response. No milestone assigned yet.

## Appendix B: Existing MCP integration in Lightspeed

Current MCP support:

**Configuration** (`lightspeed-stack.yaml`):
```yaml
mcp_servers:
  - name: "kube-mcp"
    url: "http://localhost:8081/sse"
```

**Critical learning**: SSE endpoint URL **must** include `/sse` suffix. Without it, connection fails.

**Tool discovery**:
- 21 tools discovered from kubernetes-mcp-server
- Categories: namespaces, deployments, pods, services, configmaps, secrets, logs, etc.
- Tool metadata includes `name`, `description`, `input_schema`
- **Missing**: `_meta.ui` field (kubernetes-mcp-server doesn't support MCP Apps yet)

**Authentication**: File-based, K8s, OAuth, header propagation all supported for MCP servers.

**Tool invocation**: Working end-to-end via Llama Stack `invoke_mcp_tool()`.

## Appendix C: MCP Apps platform adoption

As of January 2026 announcement:

**Supported platforms**:
- ✅ Claude (Anthropic)
- ✅ ChatGPT (OpenAI)
- ✅ VS Code (via MCP extension)
- ✅ Goose
- ✅ Postman
- ✅ MCPJam

**SDK support**:
- ✅ MCP Python SDK v1.23.0+ includes `session.list_resources()`, `session.read_resource()`
- ❌ llama-stack does not expose resources API (yet)

**Lightspeed position**: By adding MCP Apps support, Lightspeed joins the leading AI platforms in supporting interactive UI components from MCP servers.

## Appendix D: Bidirectional communication and security

**Important:** See design doc section 3.1 "Bidirectional Communication Architecture" for complete details.

### Client Responsibilities

The client application (NOT lightspeed-stack) is responsible for:

1. **Rendering iframe**: Use sandboxed iframe with `ui_resource.content`
2. **postMessage handling**: Listen for messages from iframe
3. **Sending tool results**: Push tool result data to iframe via postMessage
4. **Receiving tool calls**: When UI calls a tool, make NEW `POST /v1/query` request to lightspeed-stack
5. **MCP Apps protocol**: Implement using `@modelcontextprotocol/ext-apps` library or equivalent

### Security Considerations

From MCP Apps specification and industry best practices:

**Client-side rendering requirements**:

1. **Sandboxed iframes**: `sandbox="allow-scripts allow-same-origin"`
2. **CSP headers**: Restrict external resource loading
3. **postMessage validation**: Verify message origin before processing
4. **No direct eval()**: Parse UI-to-host messages as JSON only

**Server-side validation** (Lightspeed's responsibility):

1. **Trusted sources only**: UI resources only fetched from registered MCP servers
2. **No user-provided HTML**: HTML comes from pre-configured MCP servers, not user input
3. **Authentication propagation**: Same auth as tool execution applies to resource fetching
4. **Rate limiting**: Applied at query level (no separate endpoint)

**Trust model**:

- MCP servers are **trusted** (pre-registered by admin in `lightspeed-stack.yaml`)
- HTML content is **signed/verified by MCP server** (MCP protocol responsibility)
- Clients must **not trust** UI resource HTML with host privileges (hence sandboxed iframe)

**Recommended client implementation**:

```javascript
// Render ui_resource.content in sandboxed iframe
const iframe = document.createElement('iframe');
iframe.sandbox = 'allow-scripts allow-same-origin';
iframe.srcdoc = uiResource.content; // HTML from Lightspeed response

// Handle postMessage communication
window.addEventListener('message', (event) => {
  // Verify origin matches expected MCP Apps context
  if (event.source === iframe.contentWindow) {
    // Handle MCP Apps protocol messages
    handleMCPAppsMessage(JSON.parse(event.data));
  }
});
```

## Appendix E: Reference sources

- [MCP Apps Official Documentation](https://modelcontextprotocol.io/docs/extensions/apps)
- [MCP Apps GitHub Repository](https://github.com/modelcontextprotocol/ext-apps/)
- [MCP Apps Blog Post (Jan 26, 2026)](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [MCP Python SDK Resources API](https://github.com/modelcontextprotocol/python-sdk#resources)
- [llama-stack MCP Integration](https://github.com/llamastack/llama-stack/tree/main/src/llama_stack/providers/utils/tools)
- [llama-stack Resources API Proposal (Issue #5430)](https://github.com/llamastack/llama-stack/issues/5430)
