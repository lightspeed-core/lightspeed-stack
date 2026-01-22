# Lightspeed Core Stack - Architecture Overview

**Version:** 1.0  
**Last Updated:** January 2026  
**Status:** Living Document

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Core Components](#2-core-components)
- [3. Request Processing Pipeline](#3-request-processing-pipeline)
- [4. Database Architecture](#4-database-architecture)
- [5. API Endpoints](#5-api-endpoints)
- [6. Deployment & Operations](#6-deployment--operations)
- [Appendix](#appendix)

---

## 1. Introduction

### 1.1 What is Lightspeed Core Stack?

**Lightspeed Core Stack (LCORE)** is an enterprise-grade middleware service that provides a robust layer between client applications and AI Large Language Model (LLM) backends. It adds essential enterprise features such as authentication, authorization, quota management, caching, and observability to LLM interactions.

LCore is built on **Llama Stack** - Meta's open-source framework that provides standardized APIs for building LLM applications. Llama Stack offers a unified interface for models, RAG (vector stores), tools, and safety (shields) across different providers. LCore communicates with Llama Stack to orchestrate all LLM operations.

To enhance LLM responses, LCore leverages **RAG (Retrieval-Augmented Generation)**, which retrieves relevant context from vector databases before generating answers. Llama Stack manages the vector stores, and LCore queries them to inject relevant documentation, knowledge bases, or previous conversations into the LLM prompt.

### 1.2 Key Features

- **Multi-Provider Support**: Works with multiple LLM providers (Ollama, OpenAI, Watsonx, etc.)
- **Enterprise Security**: Authentication, authorization (RBAC), and secure credential management
- **Resource Management**: Token-based quota limits and usage tracking
- **Conversation Management**: Multi-turn conversations with history and caching
- **RAG Integration**: Retrieval-Augmented Generation for context-aware responses
- **Tool Orchestration**: Model Context Protocol (MCP) server integration
- **Observability**: Prometheus metrics, structured logging, and health checks
- **Agent-to-Agent**: A2A protocol support for multi-agent collaboration

### 1.3 System Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Client Applications                   │
│  (Web UI, CLI, VS Code Extension, Mobile Apps, etc.)    │
└────────────────────┬────────────────────────────────────┘
                     │ REST/A2A/JSON-RPC
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  LCore (This Service)                   │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Enterprise Layer                         │  │
│  │  • Authentication & Authorization (RBAC)          │  │
│  │  • Quota & Rate Limiting                          │  │
│  │  • Caching & Conversation Management              │  │
│  │  • Metrics & Observability                        │  │
│  └───────────────────────────────────────────────────┘  │
│                         ▼                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Request Processing                       │  │
│  │  • LLM Orchestration (via Llama Stack)            │  │
│  │  • Tool Integration (MCP servers)                 │  │
│  │  • RAG & Context Management                       │  │
│  └───────────────────────────────────────────────────┘  │
│                         ▼                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Storage Layer                            │  │
│  │  • 4 Separate Databases                           │  │
│  │    (User, Cache, Quota, A2A State)                │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
          ┌──────────────────┐
          │   Llama Stack    │
          │  (LLM Backend)   │
          │                  │
          │  • Models & LLMs │
          │  • RAG Stores    │
          │  • Shields       │
          └────────┬─────────┘
                   │ (manages & invokes)
                   ▼
          ┌──────────────────┐
          │  MCP Servers     │
          │  (Remote HTTP)   │
          └──────────────────┘
```

---

## 2. Core Components

This section describes the major functional components that make up LCore. Each component handles a specific aspect of the system's operation.

### 2.1 Entry Points & Lifecycle Management

**Primary Files:** `lightspeed_stack.py`, `app/main.py`, `app/routers.py`

**Purpose:** Orchestrates application startup, shutdown, and request routing.

**Key Responsibilities:**
- **CLI Entry Point**: Parse command-line arguments and route to operations (serve, config generation, config dump)
- **FastAPI Application**: Initialize the web framework with OpenAPI documentation
- **Middleware Stack**: Set up Cross-Origin Resource Sharing (CORS), metrics tracking, and global exception handling
- **Lifecycle Management**: 
  - **Startup**: Load configuration, initialize Llama Stack client, load MCP server configuration and register all defined servers with Llama Stack to build the tools list, establish database connections
  - **Shutdown**: Clean up A2A storage resources (database connections and other resources are cleaned up automatically by Python's context managers)
- **Router Registration**: Mount all endpoint routers (query, conversation, model info, auth, metrics, A2A, feedback, admin, mcp_auth)

**Note:** All configured MCP servers must be running and accessible at startup time for LCore to initialize successfully.

---

### 2.2 Configuration System (`configuration.py`, `models/config.py`)

**Purpose:** Load, validate, and provide access to service configuration from YAML files

**Configuration Files:**

LCore requires two main configuration files:

1. **LCore Configuration** (`lightspeed-stack.yaml`):
   - Service settings (host, port, logging, CORS)
   - Authentication and authorization methods
   - Database connections (user DB, cache, quota, A2A)
   - MCP server endpoints and credentials
   - Quota limits and schedules
   - User data collection preferences
   - Default models and system prompts

2. **Llama Stack Configuration** (`run.yaml`):
   - Required for both library and server modes
   - Defines LLM providers, models, RAG stores, shields
   - See [Llama Stack documentation](https://llama-stack.readthedocs.io/) for details

**Configuration Validation:**
- Pydantic models validate configuration structure at startup
- Invalid configurations prevent service from starting
- Type checking ensures correct data types
- MCP authorization headers validated against authentication method

---

### 2.3 Authentication System (`authentication/`)

**Purpose:** Verify the identity of incoming requests

**Authentication Providers:**

| Provider | Use Case | Token Handling |
|----------|----------|----------------|
| **No Auth** | Development, testing | No token (empty string) |
| **No Auth + Token** | Testing with token passthrough | Bearer token passed through |
| **Kubernetes** | K8s service accounts | K8s service account token validated and forwarded |
| **Red Hat SSO** | Red Hat environments | X-RH-Identity header (no separate token) |
| **API Key** | API key authentication | API key from Authorization header |
| **JWK/JWT** | JWT tokens | JWT validated and forwarded |

**Authentication Result (AuthTuple):**

All authentication modules return a standardized 4-tuple: `(user_id, username, roles, token)`
- `user_id` (str): Unique user identifier
- `username` (str): Human-readable username  
- `roles` (list[str]): User roles for authorization checks
- `token` (str): Original auth token extracted from request, forwarded to Llama Stack and backend services

**Note:** LCore does not generate tokens - it extracts the client's original token from the request (typically `Authorization` header) and forwards it to backend services.

---

### 2.4 Authorization System (`authorization/`)

**Purpose:** Enforce role-based access control (RBAC) on actions

**Key Components:**

**`middleware.py`:**
- `@authorize(action: Action)` decorator
- Attaches to endpoint functions
- Raises HTTPException(403) if unauthorized

**`resolvers.py`:**
- Maps roles to allowed actions
- Configurable via optional `authorization.yaml` file (defaults to built-in mappings if not provided)
- Supports action inheritance and wildcards

**Authorization Actions:**

The system defines 30+ actions that can be authorized. Examples (see `docs/auth.md` for complete list):

**Query Actions:**
- `QUERY` - Execute non-streaming queries
- `STREAMING_QUERY` - Execute streaming queries

**Conversation Management:**
- `LIST_CONVERSATIONS` - List user's conversations
- `GET_CONVERSATION` - Get conversation details
- `DELETE_CONVERSATION` - Delete conversations

**Administrative Actions:**
- `ADMIN` - Administrative operations
- `FEEDBACK` - Submit user feedback

**Agent-to-Agent Protocol:**
- `A2A_JSONRPC` - A2A protocol access

**Metadata Operations:**
- `LIST_MODELS`, `LIST_SHIELDS`, `LIST_TOOLS`, `LIST_PROVIDERS`

**How Authorization Works:**
1. Each endpoint is decorated with required action (e.g., `@authorize(Action.QUERY)`)
2. User's roles are extracted from AuthTuple
3. Authorization module checks if any user role has permission for the action
4. Request proceeds if authorized, returns 403 Forbidden if not

---

### 2.5 Llama Stack Client (`client.py`)

**Purpose:** Communicate with the Llama Stack backend service for LLM operations

**Llama Stack APIs Used:**
- **Models**: List available LLM models
- **Responses**: Generate LLM responses (OpenAI-compatible)
- **Conversations**: Manage conversation history
- **Shields**: List and apply guardrails (content filtering, safety checks)
- **Vector Stores**: Access RAG databases for context injection
- **Toolgroups**: Register MCP servers as tools

---

### 2.6 Quota Management (`quota/`)

**Purpose:** Enforce token usage limits and track consumption

**Components:**

**Quota Limiters:**
- **`user_quota_limiter.py`**: Per-user token limits
- **`cluster_quota_limiter.py`**: Cluster-wide limits (shared across all users)
- **`revokable_quota_limiter.py`**: Base implementation with revoke capability

**Token Usage Tracking:**
- **`token_usage_history.py`**: Historical usage per (user, provider, model)
- Supports analytics and billing

**Background Jobs:**
- **`runners/quota_scheduler.py`**: Background thread that periodically resets/increases quotas based on configured periods (e.g., daily, weekly, monthly)
- Runs SQL UPDATE statements to modify quota limits when time periods expire
- Maintains database connection and reconnects on failures

**Quota Enforcement Flow:**

1. **Before LLM Call:**
   - Check if user has available quota
   - Raises `QuotaExceedError` if quota exhausted
   - Request is blocked with 429 status code

2. **After LLM Call:**
   - Count input and output tokens from LLM response
   - Record token usage in Token Usage History table
   - Consume tokens from user's quota
   - Update quota counters

3. **On Error:**
   - If LLM call fails, no tokens are consumed
   - Quota remains unchanged
   - User can retry the request

---

### 2.7 Caching System (`cache/`)

**Purpose:** Store full conversation transcripts for retrieval, debugging, and compliance

When an LLM response is received, the system creates a `CacheEntry` containing the query, response, referenced documents (RAG URLs), provider/model metadata, and timestamps. This entry is stored in the cache database for conversation retrieval (`GET /conversations/{id}`), debugging, analytics, and compliance auditing.

**Implementations:**

- **PostgreSQL** (`postgres_cache.py`) - Production multi-worker deployments with persistent database storage
- **SQLite** (`sqlite_cache.py`) - Single-worker or development environments with file-based storage
- **In-Memory** (`in_memory_cache.py`) - Testing and ephemeral use cases with no persistence
- **No-Op** (`noop_cache.py`) - Disables caching entirely

---

### 2.8 Metrics System (`metrics/`)

**Purpose:** Export Prometheus-compatible metrics for observability and monitoring

**Metric Categories:**

**API Metrics:**
- Total API calls by endpoint and status code
- Response duration histograms
- Request rates and latencies

**LLM Metrics:**
- Total LLM calls by provider and model
- LLM call failures and error rates
- LLM call duration
- Token usage (input/output tokens per model)

**Quota Metrics:**
- Quota limits and available quota by subject type
- Quota consumption rates

**Shield Metrics:**
- Guardrail violations by shield type

**Metrics Endpoint:**
- Exposed at `GET /metrics` in Prometheus format
- Can be scraped by Prometheus or compatible monitoring systems

---

### 2.9 MCP Integration (`utils/mcp_*`)

**Purpose:** Enable LLMs to call external tools via Model Context Protocol (MCP) servers

MCP servers are remote HTTP services that expose tools/capabilities to LLMs (e.g., Kubernetes management, web search, databases, custom business logic).

**How It Works:**

1. **Configuration:** MCP servers are defined in the config file with name, URL, and authorization headers
2. **Registration at Startup:** LCore tells Llama Stack about each MCP server by calling `toolgroups.register()` - this makes the MCP server's tools available in Llama Stack's tool registry
3. **Query Processing:** When processing a query, LCore determines which tools to make available to the LLM and finalizes authorization headers (e.g., merging client-provided tokens with configured headers)
4. **Tool Execution:** When the LLM calls a tool, Llama Stack routes the request to the appropriate MCP server URL with the finalized authorization headers

**Authorization:**
- Supports tokens from files, environment variables, or direct values
- Special `"kubernetes"` value uses K8s service account token (validated at startup)
- Special `"client"` value allows client-provided authentication via MCP-HEADERS (see below)
- Startup validation ensures `"kubernetes"` only used with K8s authentication

**Client-Provided Authentication (MCP-HEADERS):**

Clients can provide their own authentication tokens for specific MCP servers using the `MCP-HEADERS` request header. This is used when MCP servers are configured with `"client"` as the authorization value. 

Use `GET /v1/mcp-auth/client-options` to discover which servers accept client authentication and what header names they expect.

**Limitations:**
- Only remote HTTP/HTTPS endpoints supported

---

### 2.10 A2A Protocol Support (`app/endpoints/a2a.py`, `a2a_storage/`)

**Purpose:** Enable external AI agents to call LCore as an A2A-compatible agent

External agents interact with LCore through a multi-step process:

1. **Discovery:** The agent calls `GET /.well-known/agent.json` to retrieve LCore's capabilities, skills, and supported modes
2. **Message Exchange:** The agent sends messages via `POST /a2a` using JSON-RPC 2.0 format (e.g., `message/send` method) with a `context_id` to identify the conversation
3. **Context Mapping:** The A2A context store maps the external agent's `context_id` to LCore's internal `conversation_id`, enabling multi-turn conversations (storage: PostgreSQL, SQLite, or in-memory)
4. **Query Processing:** LCore processes the message through its standard query pipeline (including LLM calls via Llama Stack) and returns the response to the external agent

External A2A requests go through LCore's standard authentication system (K8s, RH Identity, API Key, etc.).

---

## 3. Request Processing Pipeline

This section illustrates how requests flow through LCore from initial receipt to final response.

### 3.1 Complete Pipeline Overview

Every API request flows through this standardized pipeline:

1. **FastAPI Routing** - Match URL path, parse parameters
2. **Middleware Layer** - CORS validation, metrics timer, exception handling
3. **Authentication** - Extract and validate auth token, return AuthTuple(user_id, username, roles, token)
4. **Authorization** - Check user roles against required action permissions
5. **Endpoint Handler** - Execute business logic (see concrete example below)
6. **Middleware Response** - Update metrics, log response

**Concrete Example:**

Here's how a real query flows through the system:

**User Query:** "How do I scale pods in Kubernetes?"

**Step-by-Step Processing:**

1. **Request Arrives** - `POST /v2/query` with query text and optional conversation_id
2. **Authentication** - Validate JWT token, extract user_id="user123", roles=["developer"]
3. **Authorization** - Check if "developer" role has QUERY action permission ✅
4. **Quota Check** - User has 50,000 tokens available ✅
5. **Model Selection** - Use configured default model (e.g., `meta-llama/Llama-3.1-8B-Instruct`)
6. **Context Building** - Retrieve conversation history, query RAG vector stores for relevant docs, determine available MCP tools
7. **Llama Stack Call** - Send complete request with system prompt, RAG context, MCP tools, and shields
8. **LLM Processing** - Llama Stack generates response, may invoke MCP tools, returns token counts
9. **Post-Processing** - Apply shields, generate conversation summary if new
10. **Store Results** - Save to Cache DB, User DB, consume quota, update metrics
11. **Return Response** - Complete LLM response with referenced documents, token usage, and remaining quota

**Key Takeaways:**
- RAG enhances responses with relevant documentation
- MCP tools allow LLM to interact with real systems
- Every step is tracked for quotas, metrics, and caching
- The entire flow typically completes in 1-3 seconds

---

### 3.2 Error Handling

**Exception Types and HTTP Status Codes:**

- **HTTPException (FastAPI)** - 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests, 500 Internal Server Error
- **QuotaExceedError** - Converted to HTTP 429
- **APIConnectionError** (Llama Stack client) - Converted to HTTP 503 Service Unavailable
- **SQLAlchemyError** (Database) - Converted to HTTP 500

---

## 4. Database Architecture

LCore uses a multi-database strategy to optimize for different data access patterns and lifecycles.

### 4.1 Multi-Database Strategy

The system uses **4 separate databases** for different purposes:

| Database | Purpose | Technology | Size |
|----------|---------|------------|------|
| **User DB** | Conversation metadata | SQLAlchemy ORM | Small |
| **Cache DB** | Full conversation transcripts | psycopg2/sqlite3 | Large |
| **Quota DB** | Token usage and limits | psycopg2/sqlite3 | Medium |
| **A2A DB** | Agent-to-agent protocol state | SQLAlchemy async | Small |

### 4.2 Why Separate Databases?

Each database has different lifecycles, access patterns, and scaling needs:

- **User DB**: Long-term storage, frequent small operations, never deleted
- **Cache DB**: Medium-term storage, large reads/writes, can be purged for compliance
- **Quota DB**: Periodic resets, very frequent updates, scales with API call frequency
- **A2A DB**: Ephemeral storage, async operations, cleared after agent sessions

---

## 5. API Endpoints

This section documents the REST API endpoints exposed by LCore for client interactions.

### 5.1 Core Query Endpoints

**Non-Streaming Query:**
- `POST /v2/query` (Responses API, recommended)
- `POST /query` (Agent API, deprecated)
- Returns complete LLM response with referenced documents, token usage, and quota info

**Streaming Query:**
- `POST /v2/streaming_query` (Responses API, recommended)
- `POST /streaming_query` (Agent API, deprecated)
- Returns LLM response as Server-Sent Events (SSE) stream
- Events: start, token, metadata, end

---

### 5.2 Conversation Management

**List Conversations:** `GET /conversations`
- Returns list of user's conversations with metadata

**Get Conversation:** `GET /conversations/{conversation_id}`
- Returns full conversation history with all messages

**Delete Conversation:** `DELETE /conversations/{conversation_id}`
- Deletes conversation and associated data

---

### 5.3 Information Endpoints

**List Models:** `GET /models`
- Returns available LLM models

**List Providers:** `GET /providers`
- Returns configured LLM providers

**List Tools:** `GET /tools`
- Returns available tools (RAG, MCP servers)

**Discover MCP Client Auth Options:** `GET /v1/mcp-auth/client-options`
- Returns MCP servers that accept client-provided authentication tokens
- Includes header names that need to be provided via MCP-HEADERS

**List Shields:** `GET /shields`
- Returns available guardrails

**List RAG Databases:** `GET /rags`
- Returns configured vector stores

---

### 5.4 Administrative Endpoints

**Health Check:** `GET /health`
- Basic health status

**Readiness Check:** `GET /readiness`
- Checks configuration, Llama Stack, and database connections

**Metrics:** `GET /metrics`
- Prometheus-compatible metrics

**Feedback:** `POST /feedback`
- Submit user feedback (stored as JSON files)

---

### 5.5 A2A Protocol Endpoints

**Agent Card Discovery:** `GET /.well-known/agent.json`
- Returns agent capabilities (A2A protocol standard)

**A2A JSON-RPC:** `POST /a2a`
- Agent-to-agent communication endpoint
- Standard JSON-RPC 2.0 format

---

## 6. Deployment & Operations

LCore supports two deployment modes, each suited for different operational requirements.

### 6.1 Deployment Modes

**Library Mode:**
- Llama Stack runs embedded within LCore process
- No separate Llama Stack service needed
- Direct library calls (no HTTP overhead)
- Lower latency for LLM operations
- Simpler deployment (single process)
- Best for: Development, single-node deployments, environments with limited operational complexity

**Server Mode:**
- LCore and Llama Stack run as two separate processes
- HTTP communication between LCore and Llama Stack
- Independent scaling of each component
- Better resource isolation
- Easier to update/restart components independently
- In Kubernetes: can run as separate pods or as two containers in the same pod (sidecar)
  - **Separate pods**: More isolation, can scale independently
  - **Same pod (sidecar)**: Lower latency (localhost communication), atomic deployment
- Best for: Production, multi-node deployments, when LCore and Llama Stack have different scaling needs

---

## Appendix

### A. Configuration Examples

See the `examples/` directory in the repository root for complete configuration examples.

---

### B. Related Documentation

- [A2A Protocol](./a2a_protocol.md) - Agent-to-Agent communication protocol
- [Authentication & Authorization](./auth.md) - Detailed auth configuration
- [Configuration Guide](./config.md) - Configuration system details
- [Deployment Guide](./deployment_guide.md) - Deployment patterns and best practices
- [RAG Guide](./rag_guide.md) - RAG configuration and usage
- [OpenAPI Specification](./openapi.md) - Complete API reference

---

**End of Architecture Overview**
