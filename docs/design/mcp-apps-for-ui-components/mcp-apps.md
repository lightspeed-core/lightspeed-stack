# MCP Apps Integration Design

## Summary

This document outlines the design for integrating [MCP Apps](https://modelcontextprotocol.io/docs/extensions/apps) support into Lightspeed Core Stack (LCS). MCP Apps enable MCP servers to return interactive UI components (charts, tables, dashboards) that render directly in conversation streams, replacing text-only responses with rich, interactive visualizations.

**Key Goal:** Enable Lightspeed to act as an MCP Host capable of discovering, fetching, and returning UI resources with full HTML content from MCP servers that support the MCP Apps extension.

**Chosen Approach:** Extend Llama Stack with Resources API (see [llama-stack issue #5430](https://github.com/llamastack/llama-stack/issues/5430))

**Implementation Strategy:**
1. Contribute/wait for Resources API implementation in llama-stack
2. Upgrade llama-stack dependencies when available
3. Fetch UI resources **inline during query processing** via `client.resources.read()`
4. Include full HTML content directly in query response `ui_resource.content` field

**Key Benefit:** Single request flow - clients receive tool results and UI resources together, eliminating the need for separate endpoints and additional round trips.

This approach minimizes custom code in Lightspeed while providing maximum value to the broader llama-stack community.

## Background

### Current State

Lightspeed Core Stack already supports:
- MCP server registration (static via config, dynamic via API)
- Tool discovery from MCP servers via Llama Stack
- Tool invocation with result capture in text format
- MCP authentication (file-based, K8s, client-provided, OAuth, header propagation)

**Limitations:**
- Tools return only text/JSON results
- Complex data (performance metrics, resource lists, cost analysis) returned as "text walls"
- No support for interactive UI components

### MCP Apps Protocol Overview

Based on [official MCP Apps documentation](https://modelcontextprotocol.io/docs/extensions/apps):

**Core Concepts:**
1. **UI Resources**: HTML/JavaScript interfaces served via `ui://` URI scheme
2. **Tool Metadata**: Tools declare UI capabilities via `_meta.ui.resourceUri` field
3. **Host Rendering**: Clients fetch UI resources and render in sandboxed iframes
4. **Bidirectional Communication**: postMessage-based JSON-RPC protocol between UI and host

**Example Tool with UI:**
```json
{
  "name": "visualize_data",
  "description": "Visualize data as an interactive chart",
  "inputSchema": { ... },
  "_meta": {
    "ui": {
      "resourceUri": "ui://charts/interactive"
    }
  }
}
```

**Protocol Flow:**
```
1. LLM selects tool with _meta.ui.resourceUri
2. Host fetches UI resource from MCP server (ui:// → HTML)
3. Host renders HTML in sandboxed iframe
4. UI initializes with ui/initialize handshake
5. Tool result pushed to UI via postMessage
6. UI can call tools back via tools/call requests
```

### Problem Statement

**User Request:**
> "The goal of this RFE is to integrate support for the MCP Apps extension into Lightspeed core. This will allow Lightspeed developers to move beyond plain text responses by returning interactive UI components—such as charts, tables, and dashboards—that render directly within the conversation stream."

**Example Use Cases:**
- Kubernetes cluster metrics → Interactive dashboards instead of JSON dumps
- Real-time monitoring → Live-updating dashboards

## Architecture Analysis

### Current Lightspeed Query Flow

```
┌──────────────┐
│ Client (UI)  │
└──────┬───────┘
       │ POST /v1/query
       ↓
┌────────────────────────────────┐
│ Lightspeed Core Stack          │
│  /app/endpoints/query.py       │
│   - prepare_responses_params() │
│   - build_mcp_headers()        │
└──────┬─────────────────────────┘
       │ Responses API call
       ↓
┌────────────────────────────────┐
│ Llama Stack (0.5.2)            │
│  - Model inference             │
│  - MCP tool orchestration      │
└──────┬─────────────────────────┘
       │ MCP protocol (SSE)
       ↓
┌────────────────────────────────┐
│ MCP Server (e.g., kube-mcp)    │
│  - Tool execution              │
│  - Returns text/JSON results   │
└────────────────────────────────┘
```

### Integration Challenges

**Challenge 1: Llama Stack Version**
- Current version: `llama-stack==0.5.2`, `llama-stack-api==0.5.2`
- MCP Apps announced: January 26, 2026
- **Issue**: llama-stack 0.5.2 likely predates MCP Apps support
- **Evidence**: No `ui_resource` fields in current API, no resources endpoint usage

**Challenge 2: UI Resource Fetching**
- MCP Apps requires fetching `ui://` resources from MCP servers
- Current code only interacts with Llama Stack, not directly with MCP servers
- **Need**: Direct MCP protocol implementation or Llama Stack upgrade

**Challenge 3: Response Model Extension**
- Current `ToolResultSummary.content` is a string
- **Need**: Additional field for UI resource data (HTML, metadata, permissions)

**Challenge 4: Client Compatibility**
- Lightspeed clients (chat UIs, agents) must handle UI resource rendering
- Requires sandboxed iframe implementation
- **Scope**: This design focuses on backend; client implementation is separate

## Design 

### Extend Llama Stack with Resources API 

**Approach:** Contribute Resources API support to llama-stack (via [issue #5430](https://github.com/llamastack/llama-stack/issues/5430)), then upgrade and integrate

**Implementation Plan:**

1. **Phase 1: Llama Stack Enhancement**
   - Implement Resources API in llama-stack based on [issue #5430](https://github.com/llamastack/llama-stack/issues/5430)
   - Add `list_mcp_resources()` and `read_mcp_resource()` functions to `mcp.py`
   - Expose `/v1/resources/list` and `/v1/resources/read` endpoints
   - Release new llama-stack version with MCP Apps support

2. **Phase 2: Lightspeed Integration**
   - Upgrade `llama-stack` and `llama-stack-client` dependencies
   - Implement `ToolDefinitionCache` to store `_meta.ui` fields
   - Extend `ToolResultSummary` with `ui_resource` field (includes full HTML content)
   - Modify `build_tool_call_summary()` to fetch UI resources inline during query processing

**Architecture:**
```
┌──────────────┐
│ Client (UI)  │
└──────┬───────┘
       │ POST /v1/query
       ↓
┌────────────────────────────────┐
│ Lightspeed Core Stack          │
│  1. Process query via Llama    │
│  2. Detect tool with _meta.ui  │
│  3. Call resources API inline  │ ← Fetch during query processing
│  4. Include HTML in response   │
└──────┬─────────────────────────┘
       │ POST /v1/resources/read
       ↓
┌────────────────────────────────┐
│ Llama Stack (Resources API)    │
│  - read_mcp_resource()         │ ← Core implementation
│  - Handle SSE/HTTP transports  │
└──────┬─────────────────────────┘
       │ resources/read (MCP protocol)
       ↓
┌────────────────────────────────┐
│ MCP Server (e.g., kube-mcp)    │
│  - Return UI resource HTML     │
└────────────────────────────────┘
```

**Pros:**
- Minimal custom code in Lightspeed
- Leverages official llama-stack implementation
- Maintains clean architectural layer separation
- Reuses existing auth/session management from llama-stack
- Community benefit: MCP Apps support for all llama-stack users

**Cons:**
- Depends on llama-stack development timeline
- Requires coordination with llama-stack maintainers


### Data Model Changes

The primary heavy lifting for resource retrieval will be handled by the Llama Stack Resources API. Lightspeed simply calls `client.resources.read()` during query processing to fetch UI content inline.

1.1 UI Resource Metadata

We will introduce a `UIResourceMetadata` model to encapsulate the details required for the frontend to render interactive components.

```python
class UIResourceMetadata(BaseModel):
    """UI resource content for MCP Apps."""
    resource_uri: str         # e.g., ui://server/path
    server_name: str          # Hosting MCP server
    content: str              # HTML content (or base64 if binary)
    mime_type: str = "text/html"  # Content type
    is_binary: bool = False   # Whether content is base64-encoded
```

1.2 Extended Tool Result Summary

The existing `ToolResultSummary` will be updated to include an optional `ui_resource` field. This will signal to the frontend that a tool output has an associated interactive interface.

**Current Model** (in `src/utils/types.py`):
```python
class ToolResultSummary(BaseModel):
    """Model representing a result from a tool call."""

    id: str
    status: str
    content: str
    type: str
    round: int
```

**Extended Model**:
```python
class ToolResultSummary(BaseModel):
    """Model representing a result from a tool call."""

    id: str
    status: str
    content: str
    type: str
    round: int
    ui_resource: Optional[UIResourceMetadata] = Field(
        None,
        description="UI resource metadata for MCP Apps (if tool supports interactive UI)"
    )
```

**Field Behavior**:
- `ui_resource` is optional (defaults to `None`)
- Only populated when tool definition contains `_meta.ui.resourceUri`
- Contains full HTML content, not just metadata (inline fetching approach)
- Clients should check if field is present before attempting to render UI component

1.3 Tool Definition Cache

**Cache Invalidation Strategy:**

The cache needs to stay synchronized with MCP server tool definitions. Several strategies are considered:

| Strategy | Trigger | Pros | Cons |
|----------|---------|------|------|
| **On-Demand (Recommended)** | Refresh on every `/v1/tools` call | Simple, always fresh, no stale data | Higher latency on tools list endpoint |
| **TTL-based** | Refresh if cache older than N seconds | Lower latency, still relatively fresh | May serve stale data briefly |
| **Manual Refresh** | Admin API `/v1/tools/refresh` | Full control, on-demand | Requires manual intervention |
| **Webhook** | MCP server notifies on changes | Instant updates | Requires MCP server support (not standard) |

**Recommendation:** **On-Demand Refresh** - Update cache on every `GET /v1/tools` call

**Rationale:**
- `/v1/tools` endpoint already calls `client.toolgroups.list()` which fetches fresh data
- Tool listings are not latency-sensitive (typically called once at session start)
- Guarantees cache consistency without added complexity
- No risk of stale metadata causing incorrect UI resource references

**Implementation:**

```python
"""Tool definition caching for MCP Apps metadata lookup."""

from typing import Any, Optional
from datetime import datetime
from utils.types import Singleton

class ToolDefinitionCache(metaclass=Singleton):
    """Cache for tool definitions with _meta.ui information.

    Cache is refreshed on-demand when update_from_toolgroups() is called,
    typically during GET /v1/tools requests.
    """

    _tools: dict[str, dict[str, Any]] = {}
    _last_update: Optional[datetime] = None

    def update_from_toolgroups(self, toolgroups: list[Any]) -> None:
        """Update cache from Llama Stack toolgroups response.

        Args:
            toolgroups: List of toolgroup objects from client.toolgroups.list()
        """
        # Clear existing cache
        self._tools.clear()

        # Iterate toolgroups and cache tools with their metadata
        for toolgroup in toolgroups:
            if hasattr(toolgroup, 'tools'):
                for tool in toolgroup.tools:
                    # Store full tool definition including _meta
                    self._tools[tool.name] = {
                        "name": tool.name,
                        "description": tool.description,
                        "_meta": tool.metadata if hasattr(tool, 'metadata') else {},
                    }

        self._last_update = datetime.utcnow()

    def get_tool_metadata(self, tool_name: str) -> Optional[dict[str, Any]]:
        """Get cached tool definition with metadata.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool definition dict with _meta field, or None if not found
        """
        return self._tools.get(tool_name)

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last cache update.

        Returns:
            Datetime of last update, or None if never updated
        """
        return self._last_update

    def clear(self) -> None:
        """Clear the tool cache."""
        self._tools.clear()
        self._last_update = None
```

2. Implementation Roadmap

The rollout can be done in two phases following the release of the Llama Stack Resources API.

**Phase 1: Llama Stack Integration**

Upgrade llama-stack and llama-stack-client dependencies. This phase establishes the foundation for calling `client.resources.read()` to fetch UI resources.

**Phase 2: Response Enrichment**

The response pipeline will be modified to detect UI-capable tools and fetch their HTML content:

**Step 1: Update `/v1/tools` endpoint to populate cache**

```python
# In src/app/endpoints/tools.py

from utils.tool_cache import ToolDefinitionCache

@router.get("/tools", ...)
async def list_tools(...):
    # Existing code
    toolgroups_response = await client.toolgroups.list()

    # NEW: Refresh cache on every tools list request (on-demand invalidation)
    ToolDefinitionCache().update_from_toolgroups(toolgroups_response.data)

    # Rest of existing code
    return ListToolsResponse(...)
```

**Cache Invalidation:**
- Cache refreshes on every `GET /v1/tools` call
- Ensures metadata is always in sync with MCP server state
- No risk of stale `_meta.ui` references

**Step 2: Fetch UI resources inline during query processing**

**Implementation Example:**

```python
# In src/utils/responses.py - build_tool_call_summary()

async def build_tool_call_summary(
    output_item: ResponseOutput,
    tool_cache: Optional[ToolDefinitionCache] = None,
    mcp_server_url: Optional[str] = None,
) -> tuple[Optional[ToolCallSummary], Optional[ToolResultSummary]]:
    # ... existing code ...

    if item_type == "mcp_call":
        mcp_call_item = cast(MCPCall, output_item)

        # Build standard tool result
        tool_result = ToolResultSummary(
            id=mcp_call_item.call_id,
            status="success",
            content=result_content,
            type="mcp_call",
            round=current_round,
        )

        # NEW: Check for UI resource and fetch inline
        if tool_cache:
            tool_def = tool_cache.get_tool_metadata(mcp_call_item.name)
            if tool_def and "_meta" in tool_def and "ui" in tool_def["_meta"]:
                resource_uri = tool_def["_meta"]["ui"].get("resourceUri")
                if resource_uri and mcp_server_url:
                    try:
                        # Fetch UI resource from llama-stack
                        from client import client
                        resource_response = await client.resources.read(
                            mcp_endpoint={"uri": mcp_server_url},
                            uri=resource_uri,
                        )

                        # Include full content in response
                        tool_result.ui_resource = UIResourceMetadata(
                            resource_uri=resource_uri,
                            server_name=extract_server_name(mcp_server_url),
                            content=resource_response.content,
                            mime_type=resource_response.mime_type,
                            is_binary=resource_response.is_binary,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to fetch UI resource {resource_uri}: {e}")
                        # Continue without ui_resource - tool result still valid

        return tool_call, tool_result
```

**Key Simplification:**
UI resources are fetched **during query processing** and included directly in the response. No separate endpoint needed - the client receives everything in one request.

3. API Specification

**Modified Query Response (POST /v1/query)**

The system will enrich tool results with the full UI resource content fetched from llama-stack.

**Example Response:**

```json
{
  "response": "Here are the namespaces in an interactive table:",
  "tool_results": [
    {
      "id": "call-abc",
      "status": "success",
      "content": "{\"namespaces\": [\"default\", \"kube-system\"]}",
      "type": "mcp_call",
      "round": 1,
      "ui_resource": {
        "resource_uri": "ui://kube-mcp/namespaces-table",
        "server_name": "kube-mcp",
        "content": "<!DOCTYPE html><html>...<script type=\"module\">import { App } from '@modelcontextprotocol/ext-apps'...</script></html>",
        "mime_type": "text/html",
        "is_binary": false
      }
    }
  ]
}
```

**Benefits of Inline Content:**
- **Single request**: Client receives tool result + UI in one response
- **Simpler auth**: No need for client to authenticate twice
- **Atomic rendering**: All data needed arrives together
- **No extra endpoints**: Eliminates `/v1/mcp-ui-resources` complexity

3.1. Bidirectional Communication Architecture

**Key Insight:** Lightspeed-stack is **NOT involved** in the bidirectional communication between the client and the MCP Apps UI. This communication happens entirely client-side via postMessage.

**Communication Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Initial Query                                           │
│                                                                  │
│  Client App → POST /v1/query → Lightspeed-stack                │
│  Response includes: tool_result.ui_resource.content (HTML)      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Client Renders UI (Lightspeed-stack done)              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Client Application (Browser/Desktop)                     │  │
│  │                                                           │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ Sandboxed iframe                                    │  │  │
│  │  │ (ui_resource.content rendered)                      │  │  │
│  │  │                                                      │  │  │
│  │  │ <html>                                               │  │  │
│  │  │   import { App } from '@mcp/ext-apps'               │  │  │
│  │  │                                                      │  │  │
│  │  │   app.ontoolresult = (result) => {                  │  │  │
│  │  │     renderTable(result.content) // Display data     │  │  │
│  │  │   }                                                  │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  Client JS receives tool_result.content                  │  │
│  │  Client sends to iframe via postMessage ─────────────────┤  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Step 3: UI Calls Tool (Client → Lightspeed, NOT iframe direct) │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ iframe                                                  │    │
│  │   app.callTool("get_pod_details", {name: "pod-1"})  ──┐│    │
│  └────────────────────────────────────────────────────────│┘    │
│                                                            │     │
│  Client JS receives postMessage ←─────────────────────────┘     │
│  Client makes NEW HTTP request ↓                                │
│                                                                  │
│  POST /v1/query (with new tool call) → Lightspeed-stack        │
│  Response includes new tool result                              │
│  Client sends to iframe via postMessage                         │
└─────────────────────────────────────────────────────────────────┘
```

**Lightspeed-stack's Responsibilities:**

| Responsibility | Lightspeed-stack | Client Application |
|----------------|------------------|-------------------|
| Fetch HTML from llama-stack | ✅ Yes | ❌ No |
| Include HTML in response | ✅ Yes | ❌ No |
| Render iframe | ❌ No | ✅ Yes |
| Handle postMessage events | ❌ No | ✅ Yes |
| Send tool results to iframe | ❌ No | ✅ Yes |
| Receive tool calls from iframe | ❌ No | ✅ Yes |
| Execute tool calls | ✅ Yes (via /v1/query) | ❌ No |

**Key Points:**

1. **Lightspeed-stack is stateless**: No WebSocket, no SSE connection to client, no postMessage handling
2. **UI communicates with client, not server**: All postMessage happens between iframe and client JS
3. **Tool calls from UI = new HTTP requests**: When UI calls a tool, client makes a fresh `POST /v1/query`
4. **Client implements MCP Apps protocol**: Client must use `@modelcontextprotocol/ext-apps` library or equivalent

**Client Implementation Example:**

```javascript
// Client-side code (NOT lightspeed-stack)
const response = await fetch('/v1/query', {
  method: 'POST',
  body: JSON.stringify({ query: 'List namespaces' })
});

const data = await response.json();

// If tool result has UI resource
if (data.tool_results[0].ui_resource) {
  const iframe = document.createElement('iframe');
  iframe.sandbox = 'allow-scripts allow-same-origin';
  iframe.srcdoc = data.tool_results[0].ui_resource.content;
  document.body.appendChild(iframe);

  // Listen for tool calls from UI
  window.addEventListener('message', async (event) => {
    if (event.source === iframe.contentWindow) {
      const message = JSON.parse(event.data);

      if (message.method === 'tools/call') {
        // Make NEW request to lightspeed-stack
        const toolResult = await fetch('/v1/query', {
          method: 'POST',
          body: JSON.stringify({
            query: `Execute tool ${message.params.name} with ${JSON.stringify(message.params.arguments)}`
          })
        });

        // Send result back to iframe
        iframe.contentWindow.postMessage(
          JSON.stringify({ id: message.id, result: toolResult }),
          '*'
        );
      }
    }
  });

  // Send initial tool result to iframe
  iframe.contentWindow.postMessage(
    JSON.stringify({
      method: 'ui/toolResult',
      params: { content: data.tool_results[0].content }
    }),
    '*'
  );
}
```

**Why This Architecture?**

- **Stateless backend**: Lightspeed-stack remains a simple REST API, no WebSocket overhead
- **Client flexibility**: Different clients (web, desktop, mobile) can implement postMessage handling differently
- **Security**: Iframe sandbox prevents UI from directly accessing lightspeed-stack APIs
- **Standard HTTP**: Tool calls from UI are just normal query requests

4. Security Considerations

**Client-Side Sandbox Isolation**
- UI resources MUST be rendered in sandboxed iframes
- Recommended sandbox attributes: `sandbox="allow-scripts allow-same-origin"`
- CSP headers to restrict external resource loading

**Server-Side Validation**
- MCP servers are trusted (pre-registered in config)
- UI resources fetched with same auth as tool execution
- Rate limiting applied at query level (no separate endpoint to limit)

**Content Trust Model**
- HTML content comes from registered MCP servers only
- No user-provided or untrusted HTML content
- Respect `_meta.ui.csp` from tool definition for additional restrictions

5. Testing Strategy

**Unit Tests:**
- `test_tool_cache.py` - Tool definition caching and invalidation
- `test_ui_resource_enrichment.py` - ToolResultSummary.ui_resource population with inline HTML
- `test_llama_stack_resource_client.py` - Mock llama-stack resources API calls

**Integration Tests:**
- Test full query flow with MCP Apps-enabled tool
- Verify QueryResponse includes ui_resource with full HTML content
- Verify tool results without `_meta.ui` don't include ui_resource field

**E2E Tests (Behave):**
```gherkin
Feature: MCP Apps UI Resource Integration

  Scenario: Query tool with UI resource returns inline HTML
    Given an MCP server "test-mcp" is registered
    And the tool "visualize_data" has ui resource "ui://test-mcp/chart"
    When I send a query "visualize my data"
    Then the response includes tool_result with ui_resource
    And ui_resource.resource_uri is "ui://test-mcp/chart"
    And ui_resource.content contains "<html>"
    And ui_resource.content contains "@modelcontextprotocol/ext-apps"
    And ui_resource.mime_type is "text/html"

  Scenario: Query tool without UI resource omits ui_resource field
    Given an MCP server "test-mcp" is registered
    And the tool "simple_tool" has no ui resource
    When I send a query "run simple tool"
    Then the response includes tool_result without ui_resource field
```

### Open Questions

**Q1: Llama Stack Implementation Timeline**
- Status: Proposed via [llama-stack issue #5430](https://github.com/llamastack/llama-stack/issues/5430)
- **Action:** Monitor issue for maintainer feedback and implementation timeline

**Q2: Client Capabilities**
- How do clients declare MCP Apps support?
- Should `/v1/query` check client capabilities before including ui_resource?
- **Action:** Define client capability negotiation mechanism


## References

- [MCP Apps Official Documentation](https://modelcontextprotocol.io/docs/extensions/apps)
- [MCP Apps GitHub Repository](https://github.com/modelcontextprotocol/ext-apps/)
- [MCP Apps Blog Post (Jan 26, 2026)](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [MCP Apps Build Guide](https://modelcontextprotocol.io/extensions/apps/build)
- [MCP Apps API Documentation](https://apps.extensions.modelcontextprotocol.io/api/)
- [Llama Stack Resources API Proposal (Issue #5430)](https://github.com/llamastack/llama-stack/issues/5430)
- [Lightspeed Core Stack Demo (MCP Integration)](demo.md)

## Appendix A: Example MCP Server with UI

**Tool Definition:**
```json
{
  "name": "k8s_pod_metrics",
  "description": "Get pod resource metrics",
  "inputSchema": {
    "type": "object",
    "properties": {
      "namespace": {"type": "string"}
    }
  },
  "_meta": {
    "ui": {
      "resourceUri": "ui://kube-mcp/pod-metrics-dashboard"
    }
  }
}
```

**UI Resource (ui://kube-mcp/pod-metrics-dashboard):**
```html
<!DOCTYPE html>
<html>
<head>
  <title>Pod Metrics Dashboard</title>
  <script type="module">
    import { App } from 'https://esm.sh/@modelcontextprotocol/ext-apps@1.1.2';

    const app = new App();
    await app.connect();

    app.ontoolresult = (result) => {
      const metrics = JSON.parse(result.content);
      renderChart(metrics);
    };

    function renderChart(data) {
      // D3.js / Chart.js visualization
    }
  </script>
</head>
<body>
  <div id="dashboard"></div>
</body>
</html>
```
