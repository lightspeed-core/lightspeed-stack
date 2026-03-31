# MCP Apps Integration Design

## Summary

This document outlines the design for integrating [MCP Apps](https://modelcontextprotocol.io/docs/extensions/apps) support into Lightspeed Core Stack (LCS). MCP Apps enable MCP servers to return interactive UI components (charts, tables, dashboards) that render directly in conversation streams, replacing text-only responses with rich, interactive visualizations.

**Key Goal:** Enable Lightspeed to act as an MCP Host capable of discovering, fetching, and returning UI resource references from MCP servers that support the MCP Apps extension.

**Chosen Approach:** - Extend Llama Stack with Resources API** (see [llama-stack issue #5430](https://github.com/llamastack/llama-stack/issues/5430))

**Implementation Strategy:**
1. Contribute/wait for Resources API implementation in llama-stack
2. Upgrade llama-stack dependencies when available
3. Add minimal proxy endpoint in Lightspeed to expose UI resource fetching to clients
4. Optionally enrich tool results with UI metadata from tool definitions

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
   - Add UI resource proxy endpoint: `GET /v1/mcp-ui-resources/{server_name}?path=...`
   - Endpoint calls llama-stack's `/v1/resources/read` internally
   - Extend `ToolResultSummary` with `ui_resource` field (metadata only)
   - Optionally enrich tool results with `_meta.ui` from tool definitions

**Architecture:**
```
┌──────────────┐
│ Client (UI)  │
└──────┬───────┘
       │ GET /v1/mcp-ui-resources/{server}?path=...
       ↓
┌────────────────────────────────┐
│ Lightspeed Core Stack          │
│  - Validate server registration│
│  - Build auth headers           │
│  - Call llama-stack resources  │ ← Minimal proxy logic
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

The primary heavy lifting for resource retrieval will be handled by the Llama Stack Resources API, allowing Lightspeed to remain a lightweight proxy.

1.1 UI Resource Metadata

We will introduce a `UIResourceMetadata` model to encapsulate the details required for the frontend to render interactive components.

```python
class UIResourceMetadata(BaseModel):
    """Metadata about a UI resource for MCP Apps."""
    resource_uri: str    # e.g., ui://server/path
    server_name: str     # Hosting MCP server
    fetch_url: str       # Internal proxy endpoint
```

1.2 Extended Tool Result Summary

The existing `ToolResultSummary` will be updated to include an optional ui_resource field. This will signal to the frontend that a tool output has an associated interactive interface.

2. Implementation Roadmap
The rollout can be done in three distinct phases following the release of the Llama Stack Resources API.

Phase 1: Llama Stack Integration

Upgrade llama-stack and llama-stack-client dependencies. This phase will establish the foundation for calling `list_mcp_resources()` and `read_mcp_resource()` internally.

Phase 2: Response Enrichment

The response pipeline will be modified in this phase. `build_tool_call_summary` will be modified to detect UI-capable tools and inject the `UIResourceMetadata` into the final response.

Phase 3: UI Resource Proxy

A dedicated proxy endpoint will be created to serve assets securely.

Step 3.1: GET `/v1/mcp-ui-resources/{server_name}` route implementation.

Step 3.2: Develop the fetcher utility to retrieve, decode (Base64), and return HTML content from the Llama Stack.

4. API Specification

4.1 Modified Query Response (POST /v1/query)

The system will enrich tool results with a pointer to the interactive UI.

Example Response Payload:

```json
{
  "response": "Here are the namespaces in an interactive table:",
  "tool_results": [
    {
      "id": "call-abc",
      "type": "mcp_call",
      "ui_resource": {
        "resource_uri": "ui://kube-mcp/namespaces-table",
        "server_name": "kube-mcp",
        "fetch_url": "/v1/mcp-ui-resources/kube-mcp?path=kube-mcp/namespaces-table"
      }
    }
  ]
}
```

4.2 New Resource Proxy Endpoint

A new endpoint will be introduced in Lightspeed-stack to fetch the actual UI component assets.

```
GET /v1/mcp-ui-resources/{server_name}

Parameter: path (The UI resource path without the ui:// prefix).

Security: Enforces Bearer token authentication and validates the request against registered MCP servers.

Response: Returns text/html content compatible with the @modelcontextprotocol/ext-apps library.
```

### Security Considerations

**1. Sandbox Isolation (Client-Side)**
- UI resources MUST be rendered in sandboxed iframes
- Sandbox attributes: `sandbox="allow-scripts allow-same-origin"`
- CSP headers to restrict external resource loading

**2. Server Validation**
- Validate server_name is registered MCP server
- Apply same authentication as tool calls
- Rate limit UI resource fetches

**3. Content Security**
- MCP servers are trusted (pre-registered)
- UI resources are signed/verified by MCP server
- No user-provided HTML content

**4. CORS Handling**
- UI resources may load external libraries (e.g., Chart.js)
- Respect `_meta.ui.csp` from tool definition
- Proxy can inject CSP headers

### Testing Strategy

**Unit Tests:**
- `test_tool_cache.py` - Tool definition caching
- `test_ui_resource_enrichment.py` - ToolResultSummary.ui_resource population
- `test_mcp_ui_fetcher.py` - UI resource fetching (mocked MCP server)

**Integration Tests:**
- Test full query flow with MCP Apps-enabled tool
- Verify QueryResponse includes ui_resource metadata
- Test /v1/mcp-ui-resources endpoint with real MCP server

**E2E Tests (Behave):**
```gherkin
Feature: MCP Apps UI Resource Fetching

  Scenario: Query tool with UI resource returns metadata
    Given an MCP server "test-mcp" is registered
    And the tool "visualize_data" has ui resource "ui://test-mcp/chart"
    When I send a query "visualize my data"
    Then the response includes tool_result with ui_resource.resource_uri "ui://test-mcp/chart"
    And ui_resource.fetch_url is "/v1/mcp-ui-resources/test-mcp?path=test-mcp/chart"

  Scenario: Fetch UI resource returns HTML
    Given an MCP server "test-mcp" is registered
    When I GET "/v1/mcp-ui-resources/test-mcp?path=test-mcp/chart"
    Then the response is HTML content
    And the content includes MCP Apps SDK script
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
