# Getting Started

This guide starts Lightspeed Core Stack (LCS) locally with OGX embedded as a
Python library. In this mode a single LCS process listens on one port, usually
`8080`.

For containerized OGX service mode, see the
[deployment guide](../user_doc/deployment_guide.md) and
[container orchestration guide](../devel_doc/container_orchestration.md).

## Prerequisites

1. Python 3.12, 3.13, or 3.14, as defined by `pyproject.toml`
1. `pip`
1. `uv`
1. `jq` and `curl`
1. An API key for the provider in your OGX profile, for example
   `OPENAI_API_KEY`

Install the command-line tools if needed:

```bash
pip install --user uv
sudo dnf install curl jq
```

On macOS, use Homebrew for the system tools:

```bash
brew install uv jq
```

## Install Dependencies

Clone the repository with submodules, then install the development and OGX
library dependencies from the project root:

```bash
git clone --recursive https://github.com/lightspeed-core/lightspeed-stack.git
cd lightspeed-stack
uv sync --group dev --group ogxlibdev
```

If you already cloned without submodules, initialize them before running
examples that depend on provider submodules:

```bash
git submodule update --init
```

If you plan to use OpenTelemetry tracing with in-process PII redaction, also
download the spaCy model:

```bash
uv run python -m spacy download en_core_web_lg
```

## OGX Configuration

OGX needs a runnable profile. The repository includes a default example at
[examples/run.yaml](../../examples/run.yaml). Copy or reference this file when
you create the LCS configuration below.

## LCS Configuration For Library Mode

Create a file named lightspeed-stack.yaml with this content.

```yaml
name: Lightspeed Core Service (LCS)
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
ogx:
  use_as_library_client: true
  # Unified mode (recommended): the run.yaml created above is consumed as
  # the synthesis profile. The legacy library_client_config_path setup is
  # deprecated and removed in 0.8 — see the migration guide:
  # docs/user_doc/deployment_guide.md#migrating-from-the-legacy-two-file-configuration
  config:
    profile: run.yaml
user_data_collection:
  feedback_enabled: true
  feedback_storage: "/tmp/data/feedback"
  transcripts_enabled: true
  transcripts_storage: "/tmp/data/transcripts"

authentication:
  module: "noop"
```

## Start LCS

1. Export OpenAI key by using the following command:
    ```bash
    export OPENAI_API_KEY="sk-foo-bar-baz"
    ```
1. Run the following command
    ```bash
    uv run src/lightspeed_stack.py -c lightspeed-stack.yaml
    ```
1. Wait for the startup log line that says the application is ready.

## Check If The Service Runs

```bash
curl localhost:8080/v1/models | jq .
```

```json
{
  "models": [
    {
      "identifier": "gpt-4-turbo",
      "metadata": {},
      "api_model_type": "llm",
      "provider_id": "openai",
      "type": "model",
      "provider_resource_id": "gpt-4-turbo",
      "model_type": "llm"
    }
  ]
}
```

## Configuring MCP Servers

Lightspeed developers can quickly enable external tool calling using MCP servers in LCS. MCP (Model Context Protocol) is a standard for exposing external tools in a structured way so AI agents can call them reliably. An MCP server hosts one or more tools and exposes them over a network endpoint. In LCS, the AI agent can leverage these servers to execute tools: LCS routes tool calls to the appropriate MCP server and uses the tool output to generate more accurate responses.

Each MCP server provides a list of tools along with structured metadata, including name, description, and inputSchema. Using the standard `tools/list` method, LCS automatically fetches this metadata so the AI agent can evaluate user prompts and dynamically select the appropriate tool for a given request. For more details, see the [MCP documentation](https://modelcontextprotocol.io/docs/learn/architecture#how-this-works-in-ai-applications).

The following step-by-step guide shows how to set up and integrate MCP servers into LCS:

#### Step 1: Run your MCP servers
MCP servers host one or more tools and expose them over a network endpoint. They can be run locally for development or hosted externally for production.

#### Step 2: Configure LCS to know about your MCP servers
MCP servers must be defined in the `mcp_servers` section of your `lightspeed-stack.yaml`.
Example (all MCP servers running locally):

```yaml
mcp_servers:
  - name: "filesystem-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3000"
  - name: "git-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3001"
  - name: "database-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3002"
```

**Important**: MCP servers defined in `lightspeed-stack.yaml` or registered dynamically via the API (see [Dynamic MCP Server Management](#dynamic-mcp-server-management-via-api)) are available to the AI agents. Tools configured in the OGX `run.yaml` are not accessible to LCS agents.

#### Step 3: Pass authentication or metadata via MCP headers (optional)

Some MCP servers require authentication tokens, API keys, or other metadata. These can be passed **per request** using the `MCP-HEADERS` HTTP header. LCS will forward these headers when invoking the tool, allowing the MCP server to authenticate requests or receive additional context.
Example:

```bash
curl -X POST "http://localhost:8080/v1/query" \
  -H "Content-Type: application/json" \
  -H "MCP-HEADERS: {\"filesystem-tools\": {\"Authorization\": \"Bearer token123\"}}" \
  -d '{"query": "List files in /tmp"}'
```

#### Step 4: Verify connectivity
After starting the MCP servers and updating `lightspeed-stack.yaml`, test by sending a prompt to the AI agent. LCS evaluates the prompt against available tools' metadata, selects the appropriate tool, calls the corresponding MCP server, and uses the result to generate more accurate agent response.

### Dynamic MCP Server Management via API

In addition to static configuration in `lightspeed-stack.yaml`, MCP servers can be registered, listed, and removed at runtime through the REST API. This is useful for development, testing, or scenarios where MCP servers are provisioned dynamically.

When authorization is enabled, callers need the following permissions:
- `REGISTER_MCP_SERVER` for `POST /v1/mcp-servers`
- `LIST_MCP_SERVERS` for `GET /v1/mcp-servers`
- `DELETE_MCP_SERVER` for `DELETE /v1/mcp-servers/{name}`

#### Register an MCP server

```bash
curl -X POST "http://localhost:8080/v1/mcp-servers" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-dynamic-tools",
    "url": "http://localhost:9000/mcp",
    "provider_id": "model-context-protocol"
  }'
```

Response (201 Created):
```json
{
  "name": "my-dynamic-tools",
  "url": "http://localhost:9000/mcp",
  "provider_id": "model-context-protocol",
  "message": "MCP server 'my-dynamic-tools' registered successfully"
}
```

Optional fields in the request body:
- `authorization_headers` (object): Headers to send to the MCP server (e.g., `{"Authorization": "Bearer token123"}`).
- `headers` (array): List of HTTP header names to forward from incoming requests to this MCP server.
- `timeout` (integer): Request timeout in seconds.

#### List all MCP servers

```bash
curl "http://localhost:8080/v1/mcp-servers"
```

Response (200 OK):
```json
{
  "servers": [
    {
      "name": "filesystem-tools",
      "url": "http://localhost:3000",
      "provider_id": "model-context-protocol",
      "source": "config"
    },
    {
      "name": "my-dynamic-tools",
      "url": "http://localhost:9000/mcp",
      "provider_id": "model-context-protocol",
      "source": "api"
    }
  ]
}
```

Each server has a `source` field indicating how it was registered: `"config"` for servers defined in `lightspeed-stack.yaml`, or `"api"` for servers registered via the REST API.

#### Delete a dynamically registered MCP server

```bash
curl -X DELETE "http://localhost:8080/v1/mcp-servers/my-dynamic-tools"
```

Response (200 OK):
```json
{
  "name": "my-dynamic-tools",
  "message": "MCP server 'my-dynamic-tools' unregistered successfully"
}
```

**Note:** Only dynamically registered servers (source `"api"`) can be deleted via the API. Attempting to delete a statically configured server returns 403 Forbidden. Dynamically registered servers do not persist across service restarts.
