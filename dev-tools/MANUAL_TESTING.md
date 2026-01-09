# Manual Testing Guide for MCP Authorization

This guide walks through testing the MCP server authorization feature using the mock MCP server.

## Prerequisites

### 1. Create Test Secret File

```bash
echo "Bearer test-secret-token-12345" > /tmp/lightspeed-mcp-test-token
```

### 2. Start Mock MCP Server

```bash
# Terminal 1: Start mock MCP server on HTTP port 9000
python3 dev-tools/mcp-mock-server/server.py 9000
```

Verify the server starts and shows the HTTP endpoint.

### 3. Install Library Mode Dependencies

The test configuration uses Llama Stack in library mode, which requires additional dependencies:

```bash
uv pip install emoji langdetect aiosqlite pythainlp asyncpg nltk 'mcp>=1.23.0' matplotlib 'sqlalchemy[asyncio]' chardet scikit-learn faiss-cpu pillow 'datasets>=4.0.0' psycopg2-binary pandas pypdf pymongo redis tree_sitter requests
```

**Note:** These dependencies are needed for Llama Stack's inline providers (agents, vector_io, eval, etc.) to work in library mode. This is a one-time installation.

### 4. Start Lightspeed Core

```bash
# Terminal 2: Start Lightspeed Core with test config (Llama Stack runs as library)
# Make sure OPENAI_API_KEY is set first!
export OPENAI_API_KEY="your-api-key-here"
uv run src/lightspeed_stack.py --config dev-tools/test-configs/mcp-mock-test.yaml
```

Wait for Lightspeed Core to start (you should see "Application startup complete").

**Note:** The test configuration uses Llama Stack in library mode with a dedicated test config (`dev-tools/test-configs/llama-stack-mcp-test.yaml`), so you don't need to start it separately!

---

## Test: All Three Authorization Types in One Request

The test configuration defines **3 MCP servers**, which means **every query will contact all 3 servers** to discover their tools. This allows us to test all three authorization types in a single request.

### Step 1: Make a Query Request

```bash
# Terminal 3: Make test query with all required headers
curl -X POST http://localhost:8080/v1/streaming_query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-k8s-token" \
  -H 'MCP-HEADERS: {"mock-client-auth": {"Authorization": "Bearer my-client-token"}}' \
  -d '{"query": "Test all MCP auth types"}'
```

**What This Tests:**
- **`mock-file-auth`**: Uses static token from `/tmp/lightspeed-mcp-test-token`
- **`mock-k8s-auth`**: Forwards the Kubernetes token from your `Authorization` header
- **`mock-client-auth`**: Uses the client-provided token from `MCP-HEADERS`

### Step 2: Verify All Three Auth Types Worked

Check the mock server terminal output. You should see **6 requests total** (2 per server: initialize + list_tools):

1. **First pair (mock-file-auth)**:
   - `Authorization: Bearer test-secret-token-12345`
   
2. **Second pair (mock-k8s-auth)**:
   - `Authorization: Bearer my-k8s-token`
   
3. **Third pair (mock-client-auth)**:
   - `Authorization: Bearer my-client-token`

Or check the debug endpoint:

```bash
curl http://localhost:9000/debug/requests | jq
```

### Expected Result

The mock server should return unique tool names for each auth type:
- `mock_tool_file` - from `mock-file-auth`
- `mock_tool_k8s` - from `mock-k8s-auth`  
- `mock_tool_client` - from `mock-client-auth`

Check the Lightspeed Core logs, you should see:
```
DEBUG    Configured 3 MCP tools: ['mock-file-auth', 'mock-k8s-auth', 'mock-client-auth']
```

### Step 3: View Request History

```bash
curl http://localhost:9000/debug/requests | jq
```

This will show all 6 requests with their respective Authorization headers.

---

## Additional Test Scenarios

### Test Without Client Headers

Test what happens when you don't provide `MCP-HEADERS`:

```bash
curl -X POST http://localhost:8080/v1/streaming_query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-k8s-token" \
  -d '{"query": "Test without client headers"}'
```

**Expected Result:**
- `mock-file-auth`: ✅ Works (static token)
- `mock-k8s-auth`: ✅ Works (uses your k8s token)
- `mock-client-auth`: ⚠️ **Skipped** (required auth header not available - see warning in logs)

## Cleanup

Stop all services (Ctrl+C in each terminal):
1. Terminal 1: Mock MCP server
2. Terminal 2: Lightspeed Core (includes Llama Stack)

Remove test secret:
```bash
rm /tmp/lightspeed-mcp-test-token
```

## Troubleshooting

### Missing OPENAI_API_KEY
- Error: "API key not found" or authentication errors
- Solution: Set the environment variable before starting Lightspeed Core
  ```bash
  export OPENAI_API_KEY="your-api-key-here"
  ```

### Lightspeed Core startup errors
- Check that `dev-tools/test-configs/llama-stack-mcp-test.yaml` exists and is valid
- Verify OPENAI_API_KEY is set
- Check the logs for specific error messages

### Mock server not receiving requests
- Verify mock server is running: `curl http://localhost:9000/debug/headers`
- Check Lightspeed Core logs for errors
- Ensure config file path is correct

### Headers not captured
- Check mock server output for incoming requests
- Verify the secret file exists and is readable
- Check that the MCP server name matches in config and MCP-HEADERS

### Connection refused
- Ensure all services are running on expected ports (9000, 8080)
- Check firewall settings
