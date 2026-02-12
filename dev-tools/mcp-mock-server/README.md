# MCP Mock Server

A lightweight mock Model Context Protocol (MCP) server for local development and testing.

## Purpose

This mock server helps developers:
- Test MCP server authentication without real infrastructure
- Verify authorization headers are correctly sent from Lightspeed Core Stack
- Debug MCP configuration issues locally
- Develop and test MCP-related features
- Test both HTTP and HTTPS connections

**⚠️ Testing Only:** This server is single-threaded and handles requests sequentially. It is designed purely for development and testing purposes, not for production or high-load scenarios.

## Features

- ✅ **Pure Python** - No external dependencies (uses stdlib only)
- ✅ **HTTP & HTTPS** - Runs both protocols simultaneously for comprehensive testing
- ✅ **Header Capture** - Captures and displays all request headers
- ✅ **Debug Endpoints** - Inspect captured headers and request history
- ✅ **MCP Protocol** - Implements MCP endpoints (initialize, tools/list, tools/call)
- ✅ **Request Logging** - Tracks recent requests with timestamps
- ✅ **Self-Signed Certs** - Auto-generates certificates for HTTPS testing
- ✅ **Tool Execution** - Returns mock results for tool/call testing

## Quick Start

### 1. Start the Mock Server

```bash
# Default ports (HTTP: 3000, HTTPS: 3001)
python dev-tools/mcp-mock-server/server.py

# Custom ports (HTTP: 8080, HTTPS: 8081)
python dev-tools/mcp-mock-server/server.py 8080
```

You should see:
```text
======================================================================
MCP Mock Server starting with HTTP and HTTPS
======================================================================
HTTP:  http://localhost:3000
HTTPS: https://localhost:3001
======================================================================
Debug endpoints:
  • /debug/headers  - View captured headers
  • /debug/requests - View request log
MCP endpoints:
  • POST with JSON-RPC (any path)
    - method: "initialize"
    - method: "tools/list"
    - method: "tools/call"
======================================================================
Note: HTTPS uses a self-signed certificate (for testing only)
```

**Note:** The server will automatically generate a self-signed certificate in `dev-tools/mcp-mock-server/.certs/` on first run.

### 2. Configure Lightspeed Core Stack

Create a test secret file:
```bash
echo "Bearer test-secret-token-123" > /tmp/mcp-test-token
```

Add MCP server to your `lightspeed-stack.yaml`:

**For HTTP testing:**
```yaml
mcp_servers:
  - name: "mock-mcp-test-http"
    provider_id: "model-context-protocol"
    url: "http://localhost:3000"
    authorization_headers:
      Authorization: "/tmp/mcp-test-token"
```

**For HTTPS testing:**
```yaml
mcp_servers:
  - name: "mock-mcp-test-https"
    provider_id: "model-context-protocol"
    url: "https://localhost:3001"
    authorization_headers:
      Authorization: "/tmp/mcp-test-token"
```

**Note:** For HTTPS with self-signed certificates, you may need to disable SSL verification in your test environment.

### 3. Test It

Start Lightspeed Core Stack and make a query:
```bash
# In another terminal
uv run make run

# Make a query
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer user-token" \
  -d '{"query": "Test MCP tools"}'
```

### 4. Verify Headers Were Sent

Check the mock server terminal output or visit the debug endpoints:

**For HTTP:**
```bash
curl http://localhost:3000/debug/headers
```

**For HTTPS (with self-signed cert warning):**
```bash
curl -k https://localhost:3001/debug/headers
```

You should see all headers that were sent from the request.

## Debug Endpoints

Both HTTP and HTTPS servers expose the same debug endpoints.

### View All Captured Headers

**HTTP:**
```bash
curl http://localhost:3000/debug/headers
```

**HTTPS:**
```bash
curl -k https://localhost:3001/debug/headers
```

Response:
```json
{
  "last_headers": {
    "Authorization": "Bearer test-secret-token-123",
    "Host": "localhost:3000",
    "User-Agent": "curl/7.64.1",
    "Accept": "*/*",
    "Content-Type": "application/json"
  },
  "request_count": 5
}
```

### View Request History

**HTTP:**
```bash
curl http://localhost:3000/debug/requests
```

**HTTPS:**
```bash
curl -k https://localhost:3001/debug/requests
```

Response:
```json
[
  {
    "timestamp": "2026-01-08T10:30:45.123456",
    "method": "POST",
    "path": "/mcp/v1/list_tools",
    "headers": {
      "Authorization": "Bearer test-secret-token-123"
    }
  }
]
```

## Testing Different Authentication Methods

### Static Token from File
```yaml
mcp_servers:
  - name: "file-auth-test"
    url: "http://localhost:3000"
    authorization_headers:
      Authorization: "/tmp/test-token"
      X-API-Key: "/tmp/api-key"
```

### Kubernetes Token
```yaml
mcp_servers:
  - name: "k8s-auth-test"
    url: "http://localhost:3000"
    authorization_headers:
      Authorization: "kubernetes"
```

The mock server will receive the user's Kubernetes token from the request.

### Client-Provided Token
```yaml
mcp_servers:
  - name: "client-auth-test"
    url: "http://localhost:3000"
    authorization_headers:
      Authorization: "client"
```

Send request with `MCP-HEADERS`:
```bash
curl -X POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer user-k8s-token" \
  -H 'MCP-HEADERS: {"client-auth-test": {"Authorization": "Bearer client-custom-token"}}' \
  -d '{"query": "Test"}'
```

## Usage in E2E Tests

You can use this mock server in automated e2e tests:

```bash
# Start mock server in background
python dev-tools/mcp-mock-server/server.py 3000 &
MCP_PID=$!

# Run tests
make test-e2e

# Cleanup
kill $MCP_PID
```

## Running Tests

The mock server includes its own pytest test suite to verify functionality:

```bash
# Run tests with pytest
uv run pytest dev-tools/mcp-mock-server/test_mock_mcp_server.py -v

# Run tests without verbose output
uv run pytest dev-tools/mcp-mock-server/test_mock_mcp_server.py
```

The test suite automatically:
- Starts the mock server on ports 9000/9001
- Tests HTTP and HTTPS endpoints
- Verifies header capture functionality
- Tests request logging
- Cleans up the server after tests complete

## Troubleshooting

### Mock server not receiving requests
- Check that Lightspeed Core Stack is configured with the correct URL
- Verify the mock server is running on the expected port
- Check firewall/network settings

### Headers not captured
- Ensure the header name matches what's configured
- Check mock server logs for incoming requests
- Use `/debug/requests` endpoint to see all recent requests

### Port already in use
```bash
# Use a different port
python dev-tools/mcp-mock-server/server.py 8080
```

## Limitations

This is a **development/testing tool only**:
- ❌ Not for production use
- ❌ No authentication/security
- ❌ Limited MCP protocol implementation (initialize, tools/list, tools/call only)
- ❌ Single-threaded (one request at a time)
- ❌ Mock responses only (not real tool execution)

For production, use real MCP servers.

