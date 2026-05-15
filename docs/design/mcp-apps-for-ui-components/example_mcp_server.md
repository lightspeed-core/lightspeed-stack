**Example MCP Server Implementing MCP Apps pattern:**

```python
from mcp.server import Server
from mcp.types import Tool, TextContent, Resource
import mcp.server.stdio

server = Server("example-dashboard-server")

# Step 1: Define tool with _meta.ui.resourceUri
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_metrics",
            description="Get system metrics with interactive dashboard",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeframe": {
                        "type": "string",
                        "enum": ["1h", "24h", "7d"],
                        "default": "1h"
                    }
                }
            },
            # MCP Apps metadata - declares UI resource
            _meta={
                "ui": {
                    "resourceUri": "ui://example-dashboard-server/metrics-dashboard"
                }
            }
        )
    ]

# Step 2: Implement the tool (returns data)
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_metrics":
        timeframe = arguments.get("timeframe", "1h")

        # Return raw data as JSON
        metrics_data = {
            "cpu": [45, 52, 48, 61, 55],
            "memory": [2.1, 2.3, 2.2, 2.5, 2.4],
            "timeframe": timeframe
        }

        return [TextContent(
            type="text",
            text=str(metrics_data)
        )]

# Step 3: Implement resource handler (returns UI)
@server.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="ui://example-dashboard-server/metrics-dashboard",
            name="Metrics Dashboard",
            mimeType="text/html",
            description="Interactive metrics visualization"
        )
    ]

@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "ui://example-dashboard-server/metrics-dashboard":
        # Return HTML/JavaScript UI component
        return """<!DOCTYPE html>
<html>
<head>
    <title>Metrics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script type="module">
        import { App } from 'https://esm.sh/@modelcontextprotocol/ext-apps@1.1.2';

        const app = new App();
        await app.connect();

        // Receive data from tool result
        app.ontoolresult = (result) => {
            const data = JSON.parse(result.content);
            renderChart(data);
        };

        function renderChart(data) {
            const ctx = document.getElementById('metricsChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['T-4', 'T-3', 'T-2', 'T-1', 'Now'],
                    datasets: [
                        {
                            label: 'CPU %',
                            data: data.cpu,
                            borderColor: 'rgb(75, 192, 192)',
                            tension: 0.1
                        },
                        {
                            label: 'Memory GB',
                            data: data.memory,
                            borderColor: 'rgb(255, 99, 132)',
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: {
                            display: true,
                            text: `Metrics (${data.timeframe})`
                        }
                    }
                }
            });

            // User interaction - call tool to refresh
            document.getElementById('refreshBtn').onclick = async () => {
                const timeframe = document.getElementById('timeframe').value;
                const result = await app.callTool('get_metrics', { timeframe });
                renderChart(JSON.parse(result.content));
            };
        };
    </script>
</head>
<body>
    <h1>System Metrics Dashboard</h1>
    <select id="timeframe">
        <option value="1h">Last Hour</option>
        <option value="24h">Last 24 Hours</option>
        <option value="7d">Last 7 Days</option>
    </select>
    <button id="refreshBtn">Refresh</button>
    <canvas id="metricsChart" width="400" height="200"></canvas>
</body>
</html>"""

    raise ValueError(f"Unknown resource: {uri}")

# Run server
async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )
```

**Key Pattern Elements:**

1. **Tool Definition** (`@server.list_tools()`):
   - Tool has `_meta.ui.resourceUri` pointing to UI resource
   - Tool returns data as JSON/text

2. **Resource Definition** (`@server.list_resources()`):
   - Declares available UI resources with `ui://` URIs
   - Specifies MIME type (typically `text/html`)

3. **Resource Implementation** (`@server.read_resource()`):
   - Returns complete HTML/JavaScript UI component
   - UI uses `@modelcontextprotocol/ext-apps` for bidirectional communication
   - `app.ontoolresult` receives data from tool execution
   - `app.callTool()` enables UI to call tools back (e.g., refresh button)

**Flow:**
1. LLM calls `get_metrics` tool
2. Host sees `_meta.ui.resourceUri` in tool definition
3. Host fetches UI via `read_resource(uri="ui://example-dashboard-server/metrics-dashboard")`
4. Host renders HTML in sandboxed iframe
5. UI receives tool result via postMessage
6. User clicks "Refresh" → UI calls `get_metrics` again via host