# A2A (Agent-to-Agent) Protocol Integration

This document describes the A2A (Agent-to-Agent) protocol implementation in Lightspeed Core Stack, which enables standardized communication between AI agents.

## Overview

The A2A protocol is an open standard for agent-to-agent communication that allows different AI agents to discover, communicate, and collaborate with each other. Lightspeed Core Stack implements the A2A protocol to expose its AI capabilities to other agents and systems.

### Key Concepts

- **Agent Card**: A JSON document that describes an agent's capabilities, skills, and how to interact with it
- **Task**: A unit of work that an agent can execute, with states like `submitted`, `working`, `completed`, `failed`, `input_required`
- **Message**: Communication between agents containing text or other content parts
- **Artifact**: Output produced by an agent during task execution

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        A2A Client                               │
│                  (A2A Inspector, Other Agents)                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │ JSON-RPC over HTTP
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  A2A Endpoints                           │   │
│  │  /.well-known/agent.json  - Agent Card Discovery         │   │
│  │  /a2a                     - JSON-RPC Handler             │   │
│  │  /a2a/health              - Health Check                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 A2AAgentExecutor                         │   │
│  │  - Handles task execution                                │   │
│  │  - Converts Responses API events to A2A events           │   │
│  │  - Manages multi-turn conversations                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Llama Stack Client                      │   │
│  │  - Responses API (streaming responses)                   │   │
│  │  - Tools, Shields, RAG integration                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Endpoints

### Agent Card Discovery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/agent.json` | GET | Returns the agent card (standard A2A discovery path) |
| `/.well-known/agent-card.json` | GET | Returns the agent card (alternate path) |

### A2A JSON-RPC

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/a2a` | POST | Main JSON-RPC endpoint for A2A protocol |
| `/a2a` | GET | Agent card retrieval via GET |
| `/a2a/health` | GET | Health check endpoint |

## Configuration

### Agent Card Configuration

The agent card can be configured in two ways:

#### Option 1: External YAML File (Recommended)

Reference an external agent card configuration file using `customization.agent_card_path`:

```yaml
customization:
  agent_card_path: agent_card.yaml
```

Create a separate `agent_card.yaml` file with the agent card configuration:

```yaml
# agent_card.yaml
name: "Lightspeed AI Assistant"
description: "An AI assistant for OpenShift and Kubernetes"
protocolVersion: "0.3.0"  # A2A protocol version (default: "0.3.0")
provider:
  organization: "Red Hat"
  url: "https://redhat.com"
skills:
  - id: "openshift-qa"
    name: "OpenShift Q&A"
    description: "Answer questions about OpenShift and Kubernetes"
    tags: ["openshift", "kubernetes", "containers"]
    inputModes: ["text/plain"]
    outputModes: ["text/plain"]
    examples:
      - "How do I create a deployment in OpenShift?"
      - "What is a pod in Kubernetes?"
  - id: "troubleshooting"
    name: "Troubleshooting"
    description: "Help diagnose and fix issues with OpenShift clusters"
    tags: ["troubleshooting", "debugging", "support"]
    inputModes: ["text/plain"]
    outputModes: ["text/plain"]
capabilities:
  streaming: true
  pushNotifications: false
  stateTransitionHistory: false
defaultInputModes: ["text/plain"]
defaultOutputModes: ["text/plain"]
security:
  - bearer: []
security_schemes:
  bearer:
    type: http
    scheme: bearer
```

#### Option 2: Inline Configuration

Alternatively, configure the agent card directly in the main configuration file via `customization.agent_card_config`:

```yaml
customization:
  agent_card_config:
    name: "My AI Assistant"
    description: "An AI assistant for helping with various tasks"
    protocolVersion: "0.3.0"  # A2A protocol version (default: "0.3.0")
    provider:
      organization: "My Organization"
      url: "https://myorg.example.com"
    skills:
      - id: "general-qa"
        name: "General Q&A"
        description: "Answer general questions about various topics"
        tags: ["qa", "general"]
        inputModes: ["text/plain"]
        outputModes: ["text/plain"]
        examples:
          - "What is the capital of France?"
          - "Explain how photosynthesis works"
      - id: "code-assistance"
        name: "Code Assistance"
        description: "Help with coding questions and debugging"
        tags: ["coding", "development"]
        inputModes: ["text/plain"]
        outputModes: ["text/plain"]
    capabilities:
      streaming: true
      pushNotifications: false
      stateTransitionHistory: false
    defaultInputModes: ["text/plain"]
    defaultOutputModes: ["text/plain"]
    security:
      - bearer: []
    security_schemes:
      bearer:
        type: http
        scheme: bearer
```

### Service Base URL

The agent card URL is constructed from the service configuration:

```yaml
service:
  base_url: "https://my-lightspeed-service.example.com"
```

If `base_url` is not set, it defaults to `http://localhost:8080`. Note that the actual port depends on your service configuration (e.g., `8090` if configured differently).

### Authentication

A2A endpoints require authentication. Configure authentication as described in [auth.md](auth.md):

```yaml
authentication:
  module: jwk  # or k8s, noop
  jwk_config:
    url: "https://auth.example.com/.well-known/jwks.json"
```

### Authorization

The A2A endpoint uses the `A2A_JSONRPC` action. Configure access rules:

```yaml
authorization:
  access_rules:
    - role: "user"
      actions:
        - A2A_JSONRPC
```

### Persistent State Storage (Multi-Worker Deployments)

By default, A2A state (task store and context-to-conversation mappings) is stored in memory. This works well for single-worker deployments but causes issues in multi-worker deployments where:

- Subsequent requests may hit different workers
- Task state and conversation history are lost between workers
- State is lost on service restarts

For production multi-worker deployments, configure persistent storage using the `a2a_state` section:

#### In-Memory Storage (Default)

```yaml
a2a_state: {}
```

This is the default. Suitable for single-worker deployments or development.

#### SQLite Storage

```yaml
a2a_state:
  sqlite:
    db_path: "/var/lib/lightspeed/a2a_state.db"
```

SQLite is suitable for:
- Single-worker deployments that need persistence across restarts
- Multi-worker deployments with a shared filesystem (e.g., NFS, EFS)

#### PostgreSQL Storage

```yaml
a2a_state:
  postgres:
    host: "postgres.example.com"
    port: 5432
    db: "lightspeed"
    user: "lightspeed"
    password: "secret"
    ssl_mode: "require"
```

PostgreSQL is recommended for:
- Multi-worker deployments with multiple replicas
- High-availability production deployments
- Scenarios requiring horizontal scaling

#### What Gets Persisted

The A2A state storage persists:

1. **Task Store**: All A2A task objects, enabling task state queries and resumption
2. **Context-to-Conversation Mappings**: Maps A2A `contextId` to Llama Stack `conversation_id` for multi-turn conversations

This ensures that:
- Multi-turn conversations work correctly across workers
- Task state is queryable regardless of which worker handles the request
- Service restarts don't lose conversation context

## Agent Card Structure

The agent card describes the agent's capabilities:

```json
{
  "name": "Lightspeed AI Assistant",
  "description": "AI assistant for OpenShift and Kubernetes",
  "version": "1.0.0",
  "url": "https://example.com/a2a",
  "documentation_url": "https://example.com/docs",
  "protocol_version": "0.3.0",
  "provider": {
    "organization": "Red Hat",
    "url": "https://redhat.com"
  },
  "skills": [
    {
      "id": "openshift-qa",
      "name": "OpenShift Q&A",
      "description": "Answer questions about OpenShift",
      "tags": ["openshift", "kubernetes"],
      "input_modes": ["text/plain"],
      "output_modes": ["text/plain"]
    }
  ],
  "capabilities": {
    "streaming": true,
    "push_notifications": false,
    "state_transition_history": false
  },
  "default_input_modes": ["text/plain"],
  "default_output_modes": ["text/plain"],
  "security": [{"bearer": []}],
  "security_schemes": {
    "bearer": {
      "type": "http",
      "scheme": "bearer"
    }
  }
}
```

**Note:** The `protocol_version` field can be configured via the `protocolVersion` setting in your agent card configuration (see [Agent Card Configuration](#agent-card-configuration) section above).

## How the Executor Works

### A2AAgentExecutor

The `A2AAgentExecutor` class implements the A2A `AgentExecutor` interface:

1. **Receives A2A Request**: Extracts user input from the A2A message
2. **Creates Query Request**: Builds an internal `QueryRequest` with conversation context
3. **Calls Llama Stack**: Uses the Responses API to get streaming responses
4. **Converts Events**: Transforms Responses API streaming chunks to A2A events
5. **Manages State**: Tracks task state and publishes status updates

### Event Flow

```text
A2A Request
    │
    ▼
┌─────────────────────┐
│ Extract User Input  │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Create/Resume Task  │──► TaskSubmittedEvent
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Call Llama Stack    │──► TaskStatusUpdateEvent (working)
│ Responses API       │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Stream Response     │──► TaskStatusUpdateEvent (working, with deltas)
│ Chunks              │──► TaskStatusUpdateEvent (tool calls)
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Response Complete   │──► TaskArtifactUpdateEvent (final content)
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ Finalize Task       │──► TaskStatusUpdateEvent (completed/failed)
└─────────────────────┘
```

### Task States

| State | Description |
|-------|-------------|
| `submitted` | Task has been received and queued |
| `working` | Task is being processed |
| `completed` | Task finished successfully |
| `failed` | Task failed with an error |
| `input_required` | Agent needs additional input from the user |
| `auth_required` | Authentication is required to continue |

### Multi-Turn Conversations

The A2A implementation supports multi-turn conversations:

1. Each A2A `contextId` maps to a Llama Stack `conversation_id`
2. The mapping is stored in the configured A2A context store (memory, SQLite, or PostgreSQL)
3. Subsequent messages with the same `contextId` continue the conversation
4. Conversation history is preserved across turns

For multi-worker deployments, configure persistent storage (see [Persistent State Storage](#persistent-state-storage-multi-worker-deployments)) to ensure context mappings are shared across all workers.

## Testing with A2A Inspector

[A2A Inspector](https://github.com/a2aproject/a2a-inspector) is a tool for inspecting, debugging, and validating A2A agents.

### Prerequisites

1. Start your Lightspeed service:
   ```bash
   uv run python -m runners.uvicorn
   ```

2. Ensure the service is accessible (e.g., `http://localhost:8090`)

### Installing A2A Inspector

**Requirements:** Python 3.10+, uv, Node.js, and npm

1. **Clone the repository**:
   ```bash
   git clone https://github.com/a2aproject/a2a-inspector.git
   cd a2a-inspector
   ```

2. **Install dependencies**:
   ```bash
   # Python dependencies
   uv sync

   # Node.js dependencies
   cd frontend
   npm install
   cd ..
   ```

3. **Run the inspector**:

   **Option A - Local Development:**
   ```bash
   chmod +x scripts/run.sh  # First time only
   bash scripts/run.sh
   ```
   Access at: `http://127.0.0.1:5001`

   **Option B - Docker:**
   ```bash
   docker build -t a2a-inspector .
   docker run -d -p 8080:8080 a2a-inspector
   ```
   Access at: `http://127.0.0.1:8080`

### Using A2A Inspector

1. **Connect to Agent**:
   - Open the inspector UI in your browser
   - Enter the agent card URL: `http://localhost:<PORT>/.well-known/agent.json` (e.g., `http://localhost:8090/.well-known/agent.json`)
   - If authentication is required, configure the bearer token

2. **Discover Agent**:
   - The inspector will fetch and display the agent card
   - You'll see the agent's skills and capabilities

3. **Send Messages**:
   - Use the message input to send queries
   - For streaming, select "Stream" mode
   - Watch real-time status updates and responses

### Example: Testing with curl

> **Note:** The examples below use port `8090`. Adjust to match your configured service port.

#### 1. Fetch Agent Card

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8090/.well-known/agent.json
```

#### 2. Send a Message (Non-Streaming)

```bash
curl -X POST http://localhost:8090/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "user",
        "parts": [
          {"type": "text", "text": "What is Kubernetes?"}
        ]
      }
    }
  }'
```

#### 3. Stream a Message

```bash
curl -X POST http://localhost:8090/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "user",
        "parts": [
          {"type": "text", "text": "Explain pods in Kubernetes"}
        ]
      }
    }
  }'
```

#### 4. Continue a Conversation

Use the `contextId` from a previous response:

```bash
curl -X POST http://localhost:8090/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-002",
        "contextId": "previous-context-id-here",
        "role": "user",
        "parts": [
          {"type": "text", "text": "How do I create one?"}
        ]
      }
    }
  }'
```

> **Important:** The `contextId` must be placed inside the `message` object, not at the `params` level. This is required by the A2A protocol specification for the server to correctly identify and continue the conversation.

### Message Metadata

A2A messages support an optional `metadata` field that can be used to pass additional parameters to control request routing and behavior. The following metadata fields are supported:

| Field | Type | Description |
|-------|------|-------------|
| `model` | `string` | Specify the LLM model to use for this request (e.g., `"gpt-4"`, `"llama3.1"`) |
| `provider` | `string` | Specify the LLM provider to use (e.g., `"openai"`, `"watsonx"`) |
| `vector_store_ids` | `list[string]` | Specify which vector stores to query for RAG. If not provided, all available vector stores are queried |

#### Example: Using Metadata

```bash
curl -X POST http://localhost:8090/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "user",
        "parts": [
          {"type": "text", "text": "What is a deployment in OpenShift?"}
        ],
        "metadata": {
          "model": "llama3.1",
          "provider": "together",
          "vector_store_ids": ["ocp_docs", "knowledge_base"]
        }
      }
    }
  }'
```

#### Python Example with Metadata

```python
payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
        "message": {
            "messageId": "msg-001",
            "role": "user",
            "parts": [{"type": "text", "text": "Explain pods"}],
            "metadata": {
                "model": "gpt-4",
                "provider": "openai",
                "vector_store_ids": ["kubernetes_docs"]
            }
        }
    }
}
```

> **Note:** If `model` and `provider` are not specified in metadata, the default model and provider configured in the service will be used. If `vector_store_ids` is not specified, all available vector stores will be queried for RAG.

### Example: Python Client

```python
import httpx
import json

BASE_URL = "http://localhost:8090"
TOKEN = "your-bearer-token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Fetch agent card
response = httpx.get(
    f"{BASE_URL}/.well-known/agent.json",
    headers=headers
)
agent_card = response.json()
print(f"Agent: {agent_card['name']}")

# Send a message
payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
        "message": {
            "messageId": "msg-001",
            "role": "user",
            "parts": [{"type": "text", "text": "Hello, what can you do?"}]
        }
    }
}

response = httpx.post(
    f"{BASE_URL}/a2a",
    headers=headers,
    json=payload
)
result = response.json()
print(json.dumps(result, indent=2))
```

### Example: Streaming with Python

```python
import httpx
import json

BASE_URL = "http://localhost:8090"
TOKEN = "your-bearer-token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}

payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
        "message": {
            "messageId": "msg-001",
            "role": "user",
            "parts": [{"type": "text", "text": "Explain Kubernetes architecture"}]
        }
    }
}

with httpx.stream(
    "POST",
    f"{BASE_URL}/a2a",
    headers=headers,
    json=payload,
    timeout=300.0
) as response:
    for line in response.iter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:])
            result = data.get("result", {})
            event_kind = result.get("kind")
            if event_kind == "status-update":
                status = result.get("status", {})
                state = status.get("state")
                message = status.get("message", {})
                text = ""
                for part in message.get("parts", []):
                    if part.get("kind") == "text":
                        text += part.get("text", "")
                if text:
                    print(text, end="", flush=True)
            elif event_kind == "artifact-update":
                artifact = result.get("artifact", {})
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        print(part.get("text", ""))
```

## Status Update Handling

### How Status Updates Work

During task execution, the agent sends status updates via `TaskStatusUpdateEvent`:

1. **Initial Status**: When a task starts, a `working` status is sent with metadata (model, conversation_id)

2. **Text Deltas**: As the LLM generates text, each token/chunk is sent as a `working` status with the delta text in the message

3. **Tool Calls**: When the agent calls tools (RAG, MCP servers), status updates indicate the tool being called

4. **Final Status**: When complete, a `completed` or `failed` status is sent

### TaskResultAggregator

The `TaskResultAggregator` class tracks the overall task state:

- Collects status updates during streaming
- Determines the final task state based on priority:
  1. `failed` (highest priority)
  2. `auth_required`
  3. `input_required`
  4. `working` (default during processing)
- Ensures intermediate updates show `working` state to prevent premature client termination

### Example Status Update Flow

Each SSE event is wrapped in a JSON-RPC response with `id`, `jsonrpc`, and `result` fields. The `result.kind` field indicates the event type:

```json
// 1. Task submitted (kind: "task")
{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","id":"task-1","kind":"task","status":{"state":"submitted"}}}

// 2. Working with metadata (kind: "status-update")
{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","kind":"status-update","metadata":{"model":"llama3.1"},"status":{"state":"working"},"taskId":"task-1"}}

// 3. Tool call notification
{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","kind":"status-update","status":{"message":{"kind":"message","messageId":"msg-1","parts":[{"kind":"text","text":"Calling tool: my_tool"}],"role":"agent"},"state":"working"},"taskId":"task-1"}}

// 4. Text streaming (multiple events with text chunks)
{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","kind":"status-update","status":{"message":{"kind":"message","messageId":"msg-2","parts":[{"kind":"text","text":"Hello"}],"role":"agent"},"state":"working"},"taskId":"task-1"}}

{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","kind":"status-update","status":{"message":{"kind":"message","messageId":"msg-3","parts":[{"kind":"text","text":" world!"}],"role":"agent"},"state":"working"},"taskId":"task-1"}}

// 5. Final artifact (kind: "artifact-update", complete response)
{"id":"1","jsonrpc":"2.0","result":{"artifact":{"artifactId":"art-1","parts":[{"kind":"text","text":"Hello world!"}]},"contextId":"ctx-1","kind":"artifact-update","lastChunk":true,"taskId":"task-1"}}

// 6. Completion (final: true)
{"id":"1","jsonrpc":"2.0","result":{"contextId":"ctx-1","final":true,"kind":"status-update","status":{"state":"completed"},"taskId":"task-1"}}
```

## Troubleshooting

### Common Issues

1. **Agent Card Not Found (404)**
   - Ensure `agent_card_config` is configured in your YAML
   - Check that the service is running and accessible

2. **Authentication Failed (401)**
   - Verify your bearer token is valid
   - Check authentication configuration

3. **Authorization Failed (403)**
   - Ensure your role has `A2A_JSONRPC` action permission
   - Check authorization rules in configuration

4. **Connection Timeout**
   - Streaming responses have a 300-second timeout
   - Check network connectivity to Llama Stack

5. **No Response from Agent**
   - Verify Llama Stack is running and accessible
   - Check logs for errors in the executor

### Debug Logging

Enable debug logging to see detailed A2A processing:

```yaml
service:
  color_log: true
```

Check logs for entries from `app.endpoints.health` logger.

## Protocol Version

The A2A protocol version can be configured in the agent card configuration file using the `protocolVersion` field. If not specified, it defaults to **0.3.0**.

To set a specific protocol version, add it to your agent card configuration:

```yaml
# In agent_card.yaml or customization.agent_card_config
protocolVersion: "0.3.0"
```

The protocol version is included in the agent card response and indicates which version of the A2A protocol specification the agent implements.

## References

- [A2A Protocol Specification](https://github.com/google/A2A)
- [Llama Stack Documentation](https://llama-stack.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
