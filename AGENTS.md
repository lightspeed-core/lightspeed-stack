# Lightspeed Core Stack Development Guide

## Project Overview
Lightspeed Core Stack (LCS) is an AI-powered assistant built on FastAPI that provides answers using LLM services, agents, and RAG databases. It integrates with Llama Stack for AI operations.

## Development Environment
- **Python**: Check `pyproject.toml` for supported Python versions
- **Package Manager**: uv (use `uv run` for all commands)
- **Required Commands**:
  - `uv run make format` - Format code (black + ruff)
  - `uv run make verify` - Run all linters (black, pylint, pyright, ruff, docstyle, check-types)

## Code Architecture & Patterns

### Project Structure

```
src/
├── app/                                          # FastAPI application
│   ├── endpoints/                                # REST API endpoints
│   │   ├── a2a_openapi.py                        # OpenAPI-only metadata for A2A JSON-RPC routes
│   │   ├── a2a.py                                # Handler for A2A (Agent-to-Agent) protocol endpoints using Responses API
│   │   ├── authorized.py                         # Handler for REST API call to authorized endpoint
│   │   ├── config.py                             # Handler for REST API call to retrieve service configuration
│   │   ├── conversations_v1.py                   # Handler for REST API calls to manage conversation history using Conversations API
│   │   ├── conversations_v2.py                   # Handler for REST API calls to manage conversation history
│   │   ├── feedback.py                           # Handler for REST API endpoint for user feedback
│   │   ├── health.py                             # Handlers for health REST API endpoints
│   │   ├── info.py                               # Handler for REST API call to provide info
│   │   ├── mcp_auth.py                           # Handler for REST API calls related to MCP server authentication
│   │   ├── mcp_servers.py                        # Handler for REST API calls to dynamically manage MCP servers
│   │   ├── metrics.py                            # Handler for REST API call to provide metrics
│   │   ├── models.py                             # Handler for REST API call to list available models
│   │   ├── prompts.py                            # Handler for REST API calls to manage Llama Stack stored prompt templates
│   │   ├── providers.py                          # Handler for REST API calls to list and retrieve available providers
│   │   ├── query.py                              # Handler for REST API call to provide answer to query using Response API
│   │   ├── rags.py                               # Handler for REST API calls to list and retrieve available RAGs
│   │   ├── responses.py                          # Handler for REST API call to provide answer using Responses API (LCORE specification)
│   │   ├── responses_telemetry.py                # Splunk telemetry helpers for the Responses API endpoint
│   │   ├── rlsapi_v1.py                          # Handler for RHEL Lightspeed rlsapi v1 REST API endpoints
│   │   ├── root.py                               # Handler for the / endpoint
│   │   ├── saved_prompts.py                      # Handler for REST API calls to manage saved prompts
│   │   ├── shields.py                            # Handler for REST API call to list available shields
│   │   ├── streaming_query.py                    # Streaming query handler using Responses API
│   │   ├── stream_interrupt.py                   # Endpoint for interrupting in-progress streaming query requests
│   │   ├── tools.py                              # Handler for REST API call to list available tools from MCP servers
│   │   └── vector_stores.py                      # Handler for REST API calls to manage vector stores and files
│   ├── database.py                               # Database engine management
│   ├── routers.py                                # All REST API routers
│   └── main.py                                   # Application entry point
├── a2a_storage/                                  # A2A protocol persistent storage
│   ├── context_store.py                          # Abstract base class for context stores
│   ├── in_memory_context_store.py                # In-memory implementation
│   ├── sqlite_context_store.py                   # SQLite implementation
│   ├── postgres_context_store.py                 # PostgreSQL implementation
│   └── storage_factory.py                        # Factory for creating stores
├── authentication/                               # Authentication modules (k8s, jwk, noop, rh-identity)
│   ├── api_key_token.py                          # Authentication flow for FastAPI endpoints with a provided API key
│   ├── interface.py                              # Abstract base class for all authentication method implementations
│   ├── jwk_token.py                              # Manage authentication flow for FastAPI endpoints with JWK based JWT auth
│   ├── k8s.py                                    # Manage authentication flow for FastAPI endpoints with K8S/OCP
│   ├── noop.py                                   # Manage authentication flow for FastAPI endpoints with no-op auth
│   ├── noop_with_token.py                        # Manage authentication flow for FastAPI endpoints with no-op auth and provided user token
│   ├── rh_identity.py                            # Red Hat Identity header authentication for FastAPI endpoints
│   ├── trusted_proxy.py                          # Trusted-proxy authentication module for requests forwarded by a K8s proxy
│   └── utils.py                                  # Authentication utility functions
├── authorization/                                # Authorization middleware & resolvers
│   ├── azure_token_manager.py                    # Azure Entra ID token manager for Azure OpenAI authentication
│   ├── middleware.py                             # Authorization middleware and decorators
│   └── resolvers.py                              # Authorization resolvers for role evaluation and access control
├── cache/                                        # Conversation cache implementations
│   ├── cache.py                                  # Abstract class that is parent for all cache implementations
│   ├── cache_entry.py                            # Model for conversation history cache entry
│   ├── cache_error.py                            # Any exception that can occur during cache operations
│   ├── cache_factory.py                          # Cache factory class
│   ├── in_memory_cache.py                        # In-memory cache implementation
│   ├── noop_cache.py                             # No-operation cache implementation
│   ├── postgres_cache.py                         # PostgreSQL cache implementation
│   └── sqlite_cache.py                           # Cache that uses SQLite to store cached values
├── data/                                         # Built-in default Llama Stack baseline for unified-mode synthesis
│   └── default_run.yaml                          # The starting point when a unified `lightspeed-stack.yaml` select default baseline
├── quota/                                        # Quota limiter and token usage tracking
│   ├── cluster_quota_limiter.py                  # Simple cluster quota limiter where quota is fixed for the whole cluster
│   ├── connect_pg.py                             # PostgreSQL connection handler
│   ├── connect_sqlite.py                         # SQLite connection handler
│   ├── quota_exceed_error.py                     # Any exception that can occur when a user does not have enough tokens available
│   ├── quota_limiter.py                          # Abstract class that is the parent for all quota limiter implementations
│   ├── quota_limiter_factory.py                  # Quota limiter factory class
│   ├── revokable_quota_limiter.py                # Simple quota limiter where quota can be revoked
│   ├── sql.py                                    # SQL commands used by quota management package
│   ├── token_usage_history.py                    # Class with implementation of storage for token usage history
│   └── user_quota_limiter.py                     # Simple user quota limiter where each user has a fixed quota
├── metrics/                                      # Prometheus metrics
│   ├── __init__.py                               # Metrics module for Lightspeed Core Stack
│   ├── recording.p                               # Recording helpers for Prometheus metricsy
│   └── utils.py                                  # Utility functions for metrics handling
├── runners/                                      # Runners for various LCore subsystems
│   ├── quota_scheduler.py                        # User and cluster quota scheduler runner
│   └── uvicorn.py                                # Uvicorn runner
├── models/                                       # Pydantic models
│   ├── api/                                      # REST API models
│   │   ├── requests/                             # REST API request models
│   │   │   ├── __init__.py                       # Concrete REST API request models grouped by domain
│   │   │   ├── catalog.py                        # Request models for catalog-related endpoints
│   │   │   ├── conversations.py                  # Request models for conversation endpoints
│   │   │   ├── feedback.py                       # Request models for feedback endpoints
│   │   │   ├── mcp_servers.py                    # Request models for MCP server registration
│   │   │   ├── prompts.py                        # Request models for prompt template endpoints
│   │   │   ├── query.py                          # Request models for query and streaming interrupt endpoints
│   │   │   ├── responses_openai.py               # Request model for the OpenAI-compatible Responses API
│   │   │   ├── rlsapi.py                         # Models for rlsapi v1 REST API requests
│   │   │   └── vector_stores.py                  # Request models for vector store and file endpoints
│   │   └── responses/                            # HTTP response models
│   │       ├── constants.py                      # OpenAPI description strings and shared example-label lists for API responses
│   │       ├── error/                            # Error responses
│   │       │   ├── bad_request.py                # OpenAPI-aligned error response models: HTTP 400 Bad Request
│   │       │   ├── bases.py                      # Base Pydantic types for OpenAPI-aligned structured API error responses
│   │       │   ├── conflict.py                   # OpenAPI-aligned error response models: HTTP 409 Conflict
│   │       │   ├── content_too_large.py          # OpenAPI-aligned error response models: HTTP 413 Payload Too Large
│   │       │   ├── forbidden.py                  # OpenAPI-aligned error response models: HTTP 403 Forbidden
│   │       │   ├── internal.py                   # OpenAPI-aligned error response models: HTTP 500 Internal Server Error
│   │       │   ├── not_found.py                  # OpenAPI-aligned error response models: HTTP 404 Not Found
│   │       │   ├── service_unavailable.py        # OpenAPI-aligned error response models: HTTP 503 Service Unavailable
│   │       │   ├── too_many_requests.py          # OpenAPI-aligned error response models: HTTP 429 Too Many Requests
│   │       │   ├── unauthorized.py               # OpenAPI-aligned error response models: HTTP 401 Unauthorized
│   │       │   └── unprocessable_entity.py       # OpenAPI-aligned error response models: HTTP 422 Unprocessable Entity
│   │       └── successful/                       # Successful responses
│   │           ├── bases.py                      # Base classes for successful API response models
│   │           ├── catalog.py                    # Successful response bodies for catalog-style endpoints
│   │           ├── configuration.py              # Successful response model for the configuration endpoint
│   │           ├── conversations.py              # Successful responses for conversation CRUD and listing
│   │           ├── feedback.py                   # Successful responses for feedback and feedback status endpoints
│   │           ├── mcp_servers.py                # Successful responses for MCP server registration and listing
│   │           ├── probes.py                     # Successful probe-related API responses (info, readiness, liveness, status, auth)
│   │           ├── prompts.py                    # Successful responses for stored prompt templates
│   │           ├── query.py                      # Successful response models for synchronous query and streaming query documentation
│   │           ├── responses_openai.py           # Successful response model for the OpenAI-compatible Responses API
│   │           ├── rlsapi.py                     # Models for rlsapi v1 REST API responses
│   │           ├── saved_prompts.py              # Successful responses for saved prompts configuration
│   │           └── vector_stores.py              # Successful responses for vector stores and vector store files
│   ├── common/                                   # Shared cross-layer models
│   │   ├── agents/                               # Streaming payload models and event type exports
│   │   │   ├── stream_payloads.py                # Typed JSON bodies for SSE streaming events
│   │   │   └── turn_accumulator.py               # Mutable per-turn state for agent response processing
│   │   ├── responses/                            # Shared models for the OpenAI-compatible Responses API pipeline
│   │   │   ├── contexts.py                       # Context objects for the responses endpoint pipeline and streaming query generators.
│   │   │   ├── responses_api_params.py           # Request parameter model for Llama Stack responses API calls
│   │   │   ├── responses_conversation_context.py # Conversation resolution result model for the OpenAI-compatible responses endpoint
│   │   │   └── types.py                          # Type aliases for OpenAI-compatible Responses API input shapes
│   │   ├── conversation.py                       # Conversation list rows, metadata, and simplified turn/message shapes for APIs
│   │   ├── feedback.py                           # Predefined feedback categories for AI response quality signals
│   │   ├── health.py                             # Health-related shared models for readiness and diagnostics
│   │   ├── mcp.py                                # MCP server metadata models shared by registration and list responses
│   │   ├── moderation.py                         # Shield moderation outcomes for the responses pipeline
│   │   ├── query.py                              # Shared query-related request primitives
│   │   ├── transcripts.py                        # Pydantic models for persisted query/response transcript entries
│   │   └── turn_summary.py                       # RAG context, chunks, document refs, tool summaries, and per-turn aggregation
│   ├── compaction.py                             # Pydantic models for conversation compaction
│   ├── config.py                                 # Model with service configuration
│   ├── database/                                 # Database models
│   │   ├── base.py                               # Base model for SQLAlchemy ORM classes
│   │   ├── conversations.py                      # User conversation models
│   │   └── saved_prompts.py                      # User saved prompt models
│   └── __init__.py                               # Database models package
├── observability/                                # Observability module for telemetry and event collection
│   ├── formats/                                  # Event format builders for Splunk telemetry
│   │   ├── responses.py                          # Event builders for Responses API Splunk format
│   │   └── rlsapi.py                             # Event builders for rlsapi v1 Splunk format
│   └── splunk.py                                 # Async Splunk HEC client for sending telemetry events
├── pydantic_ai_lightspeed/                       # Pydantic AI integrations/extensions for Lightspeed Core Stack
│   ├── capabilities/                             # Pluggable capabilities for pydantic-ai agents in Lightspeed
│   │   ├── question_validity/                    # Question validity capability for agent input validation
│   │   │   └── _capability.py                    # Question validity capability for filtering off-topic user queries
│   │   └── redaction/                            # PII redaction capability for Pydantic AI agents
│   │       ├── capability.py                     # Pydantic AI capability for PII redaction of model messages
│   │       └── core.py                           # Core redaction logic for PII detection and replacement
│   └── llamastack/                               # Pydantic AI provider for Llama Stack
│       ├── _model.py                             # Custom OpenAI Responses model that works around Llama Stack streaming quirks
│       ├── _provider.py                          # Llama Stack provider implementation for Pydantic AI
│       └── _transport.py                         # httpx transport that routes OpenAI-compatible requests through a Llama Stack library client
├── telemetry/                                    # Telemetry module for configuration snapshot collection
│   └── configuration_snapshot.py                 # Configuration snapshot with PII masking for telemetry
├── utils/                                        # Utility functions
│   ├── agents/                                   # Agent streaming and non streaming helpers
│   │   ├── query.py                              # Non-streaming agent helpers and shared turn-summary builders for agent runs
│   │   ├── streaming.py                          # Agent streaming helpers for the streaming_query flow
│   │   └── tool_processor.py                     # Process and record pydantic-ai tool parts during agent stream dispatch
│   ├── checks.py                                 # Checks that are performed to configuration options
│   ├── common.py                                 # Common utilities for the project
│   ├── compaction.py                             # Conversation compaction — partitioning, summarization, additive fold-up
│   ├── config_dumper.py                          # Function to dump the configuration schema into OpenAPI-compatible format
│   ├── connection_decorator.py                   # Decorator that makes sure the object is 'connected' according to it's connected predicate
│   ├── conversation_compaction.py                # Runtime integration of conversation compaction into the request flow
│   ├── conversations.py                          # Utilities for conversations
│   ├── degraded_mode.py                          # Degraded mode state tracking
│   ├── endpoints.py                              # Utility functions for endpoint handlers
│   ├── json_schema_updater.py                    # Function to transform a JSON Schema-like dictionary into an OpenAPI-compatible schema
│   ├── llama_stack_version.py                    # Check if the Llama Stack version is supported by the LCS
│   ├── markdown_repair.py                        # Utilities for repairing truncated markdown content
│   ├── mcp_auth_headers.py                       # Utilities for resolving MCP server authorization headers
│   ├── mcp_headers.py                            # MCP headers handling
│   ├── mcp_oauth_probe.py                        # Probe MCP servers for OAuth and raise 401 with WWW-Authenticate when required
│   ├── models_dumper.py                          # Function to dump the schema of all data models into OpenAPI-compatible format
│   ├── openapi_schema_dumper.py                  # Utility function to dump schema with list of models into OpenAPI-compatible JSON format
│   ├── prompts.py                                # Utility functions for system prompts
│   ├── pydantic_ai_helpers.py                    # Helpers for running Pydantic AI agents against Llama Stack (Responses API compatibility)
│   ├── query.py                                  # Utility functions for working with queries
│   ├── quota_utils.py                            # Quota handling helper functions
│   ├── reranker.py                               # Reranker utilities for RAG chunk reranking
│   ├── responses.py                              # Utility functions for processing Responses API output
│   ├── rh_identity.py                            # Utility functions for extracting RH Identity context for telemetry
│   ├── shields.py                                # Utility functions for working with Llama Stack shields
│   ├── streaming_sse.py                          # SSE formatting helpers for streaming query responses
│   ├── stream_interrupts.py                      # Stream interrupt registry and persistence utilities
│   ├── suid.py                                   # Session ID utility functions
│   ├── token_counter.py                          # Helper classes to count tokens sent and received by the LLM
│   ├── token_estimator.py                        # Pre-LLM-call token estimation
│   ├── tool_formatter.py                         # Utility functions for formatting and parsing MCP tool descriptions
│   ├── transcripts.py                            # Transcript handling
│   ├── types.py                                  # Common types for the project
│   └── vector_search.py                          # Vector search utilities for query endpoints
├── sentry.py                                     # Sentry error tracking initialization and configuration
├── lightspeed_stack.py                           # Entry point to the Lightspeed Core Stack REST API service
├── llama_stack_configuration.py                  # Llama Stack configuration enrichment and synthesis
├── log.py                                        # Log utilities
├── client.py                                     # Llama Stack client wrapper (Singleton)
├── configuration.py                              # Config management (Singleton)
├── constants.py                                  # Shared (final) constants
└── version.py                                    # Service version that is read by project manager tools
```

### Coding Standards

#### Imports & Dependencies
- Use absolute imports for internal modules: `from authentication import get_auth_dependency`
- FastAPI dependencies: `from fastapi import APIRouter, HTTPException, Request, status, Depends`
- Llama Stack imports: `from llama_stack_client import AsyncLlamaStackClient`
- **ALWAYS** check `pyproject.toml` for existing dependencies before adding new ones
- **ALWAYS** verify current library versions in `pyproject.toml` rather than assuming versions
- Check `constants.py` for shared constants before defining new ones

#### Module Standards
- All modules start with descriptive docstrings explaining purpose
- Use `logger = get_logger(__name__)` from `log.py` for module logging
- Package `__init__.py` files contain brief package descriptions
- Central `constants.py` for shared constants with descriptive comments
- Type aliases defined at module level for clarity
- Use Final[type] as type hint for all constants

#### Configuration
- All config uses Pydantic models extending `ConfigurationBase`
- Base class sets `extra="forbid"` to reject unknown fields
- Use `@field_validator` and `@model_validator` for custom validation
- Type hints: `Optional[FilePath]`, `PositiveInt`, `SecretStr`

#### Function Standards
- **Documentation**: All functions require docstrings with brief descriptions
- **Type Annotations**: Complete type annotations for parameters and return types
  - Use `typing_extensions.Self` for model validators
  - Union types: `str | int` (modern syntax)
  - Optional: `Optional[Type]`
- **Naming**: Use snake_case with descriptive, action-oriented names (get_, validate_, check_)
- **Return Values**: **CRITICAL** - Avoid in-place parameter modification anti-patterns:
  ```python
  # ❌ BAD: Modifying parameter in-place
  def process_data(input_data: Any, result_dict: dict) -> None:
      result_dict[key] = value  # Anti-pattern

  # ✅ GOOD: Return new data structure
  def process_data(input_data: Any) -> dict:
      result_dict = {}
      result_dict[key] = value
      return result_dict
  ```
- **Async Functions**: Use `async def` for I/O operations and external API calls
- **Error Handling**:
  - Use FastAPI `HTTPException` with appropriate status codes for API endpoints
  - Handle `APIConnectionError` from Llama Stack

#### Logging Standards
- Use `from log import get_logger` and module logger pattern: `logger = get_logger(__name__)`
- Standard log levels with clear purposes:
  - `logger.debug()` - Detailed diagnostic information
  - `logger.info()` - General information about program execution
  - `logger.warning()` - Something unexpected happened or potential problems
  - `logger.error()` - Serious problems that prevented function execution

#### Class Standards
- **Documentation**: All classes require descriptive docstrings explaining purpose
- **Naming**: Use PascalCase with descriptive names and standard suffixes:
  - `Configuration` for config classes
  - `Error`/`Exception` for custom exceptions
  - `Resolver` for strategy pattern implementations
  - `Interface` for abstract base classes
- **Pydantic Models**: Extend `ConfigurationBase` for config, `BaseModel` for data models
- **Abstract Classes**: Use ABC for interfaces with `@abstractmethod` decorators
- **Validation**: Use `@model_validator` and `@field_validator` for Pydantic models
- **Type Hints**: Complete type annotations for all class attributes, use specific types, not `Any`

#### Docstring Standards
- Follow Google Python docstring conventions: https://google.github.io/styleguide/pyguide.html
- Required for all modules, classes, and functions
- Include brief description and detailed sections as needed:
  - `Parameters:` for function parameters
  - `Returns:` for return values
  - `Raises:` for exceptions that may be raised
  - `Attributes:` for class attributes (Pydantic models)


## Testing Framework

### Test Structure
```
tests/
├── unit/                # Unit tests (pytest)
├── integration/         # Integration tests (pytest)
└── e2e/                 # End-to-end tests (behave)
    └── features/        # Gherkin feature files
```

### Testing Framework Requirements
- **Required**: Use pytest for all unit and integration tests
- **Forbidden**: Do not use unittest - pytest is the standard for this project
- **E2E Tests**: Use behave (BDD) framework for end-to-end testing

### Unit Tests (pytest)
- **Fixtures**: Use `conftest.py` for shared fixtures
- **Mocking**: `pytest-mock` for AsyncMock objects
- **Common Pattern**:
  ```python
  @pytest.fixture(name="prepare_agent_mocks")
  def prepare_agent_mocks_fixture(mocker):
      mock_client = mocker.AsyncMock()
      mock_agent = mocker.AsyncMock()
      mock_agent._agent_id = "test_agent_id"
      return mock_client, mock_agent
  ```
- **Auth Mock**: `MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")`
- **Coverage**: Unit tests require 60% coverage, integration 10%
- **Async tests**: Use marker `pytest.mark.asyncio`

### E2E Tests (behave)
- **Framework**: Behave (BDD) with Gherkin feature files
- **Step Definitions**: In `tests/e2e/features/steps/`
- **Common Steps**: Service status, authentication, HTTP requests
- **Test List**: Maintained in `tests/e2e/test_list.txt`

### Test Commands
```bash
uv run make test-unit        # Unit tests with coverage
uv run make test-integration # Integration tests
uv run make test-e2e         # End-to-end tests
```

## Quality Assurance

### Required Before Completion
1. `uv run make format` - Auto-format code
2. `uv run make verify` - Run all linters
3. Create unit tests for new code
4. Ensure tests pass

### Linting Tools
- **black**: Code formatting
- **pylint**: Static analysis (`source-roots = "src"`)
- **pyright**: Type checking
- **ruff**: Fast linter
- **pydocstyle**: Docstring style
- **mypy**: Additional type checking

### Security
- **bandit**: Security issue detection
- Never commit secrets/keys
- Use environment variables for sensitive data

## Key Dependencies
**IMPORTANT**: Always check `pyproject.toml` for current versions rather than relying on this list:
- **FastAPI**: Web framework
- **Llama Stack**: AI integration
- **Pydantic**: Data validation/serialization
- **SQLAlchemy**: Database ORM
- **Kubernetes**: K8s auth integration

## Pull Request Requirements

**PR titles MUST start with a JIRA issue key prefix.** CI enforces this via `pr-title-checker` (config: `.github/pr-title-checker-config.json`).

Allowed prefixes: `LCORE-`, `RSPEED-`, `MGTM-`, `OLS-`, `RHIDP-`, `LEADS-`, `CWFHEALTH-`, `[release/`

- ✅ `RSPEED-2849: add user_agent to ResponsesEventData`
- ❌ `feat(observability): add user_agent to ResponsesEventData`

## Development Workflow
1. Use `uv sync --group dev --group llslibdev` for dependencies
2. Always use `uv run` prefix for commands
3. **ALWAYS** check `pyproject.toml` for existing dependencies and versions before adding new ones
4. Follow existing code patterns in the module you're modifying
5. Write unit tests covering new functionality
6. Run format and verify before completion
