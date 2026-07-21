# Lightspeed Core Stack


---

# 📋 Configuration schema

## A2AStateConfiguration


A2A protocol persistent state configuration.

Configures how A2A task state and context-to-conversation mappings are
stored. For multi-worker deployments, use SQLite or PostgreSQL to ensure
state is shared across all workers.

If no configuration is provided, in-memory storage is used (default).
This is suitable for single-worker deployments but state will be lost
on restarts and not shared across workers.

Attributes:
    sqlite: SQLite database configuration for A2A state storage.
    postgres: PostgreSQL database configuration for A2A state storage.


| Field    | Type | Description                                              |
|----------|------|----------------------------------------------------------|
| sqlite   |      | SQLite database configuration for A2A state storage.     |
| postgres |      | PostgreSQL database configuration for A2A state storage. |


## APIKeyTokenConfiguration


API Key Token configuration.


| Field   | Type   | Description |
|---------|--------|-------------|
| api_key | string |             |


## AccessRule


Rule defining what actions a role can perform.


| Field   | Type   | Description                   |
|---------|--------|-------------------------------|
| role    | string | Name of the role              |
| actions | array  | Allowed actions for this role |


## Action


Available actions in the system.

Note: this is not a real model, just an enumeration of all action names.




## ApprovalFilter


Granular approval control for specific MCP tools.

Attributes:
    always: Tool names that always require human approval before execution.
    never: Tool names that never require approval (pre-approved).


| Field  | Type  | Description                                           |
|--------|-------|-------------------------------------------------------|
| always | array | List of tool names that always require human approval |
| never  | array | List of tool names that never require approval        |


## ApprovalsConfiguration


Configuration for human-in-the-loop approvals.

Attributes:
    approval_timeout_seconds: How long approval requests remain pending
        before expiring.
    approval_retention_days: How long to retain decided approvals for audit
        purposes before cleanup.


| Field                    | Type    | Description                                     |
|--------------------------|---------|-------------------------------------------------|
| approval_timeout_seconds | integer | Seconds before pending approval requests expire |
| approval_retention_days  | integer | Days to retain decided approvals before cleanup |


## AuthenticationConfiguration


Authentication configuration.


| Field                  | Type    | Description                                          |
|------------------------|---------|------------------------------------------------------|
| module                 | string  |                                                      |
| skip_tls_verification  | boolean |                                                      |
| skip_for_health_probes | boolean | Skip authorization for readiness and liveness probes |
| skip_for_metrics       | boolean | Skip authorization for the /metrics endpoint         |
| k8s_cluster_api        | string  |                                                      |
| k8s_ca_cert_path       | string  |                                                      |
| jwk_config             |         |                                                      |
| api_key_config         |         |                                                      |
| rh_identity_config     |         |                                                      |
| trusted_proxy_config   |         |                                                      |


## AuthorizationConfiguration


Authorization configuration.


| Field        | Type  | Description                         |
|--------------|-------|-------------------------------------|
| access_rules | array | Rules for role-based access control |


## AzureEntraIdConfiguration


Microsoft Entra ID authentication attributes for Azure.


| Field         | Type   | Description                                                                                          |
|---------------|--------|------------------------------------------------------------------------------------------------------|
| tenant_id     | string |                                                                                                      |
| client_id     | string |                                                                                                      |
| client_secret | string |                                                                                                      |
| scope         | string | Azure Cognitive Services scope for token requests. Override only if using a different Azure service. |


## ByokRag


BYOK (Bring Your Own Knowledge) RAG configuration.


| Field               | Type    | Description                                                                                                                                                                                        |
|---------------------|---------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| rag_id              | string  | Unique RAG ID                                                                                                                                                                                      |
| rag_type            | string  | Type of RAG database (e.g. 'inline::faiss', 'remote::pgvector').                                                                                                                                   |
| embedding_model     | string  | Embedding model identification                                                                                                                                                                     |
| embedding_dimension | integer | Dimensionality of embedding vectors.                                                                                                                                                               |
| vector_db_id        | string  | Vector database identification.                                                                                                                                                                    |
| db_path             | string  | Path to RAG database. Required for inline::faiss.                                                                                                                                                  |
| score_multiplier    | number  | Multiplier applied to relevance scores from this vector store. Used to weight results when querying multiple knowledge sources. Values > 1 boost this store's results; values &lt;; 1 reduce them. |
| host                | string  | PostgreSQL host for remote::pgvector. Defaults to ${env.POSTGRES_HOST} when rag_type is remote::pgvector.                                                                                          |
| port                | string  | PostgreSQL port for remote::pgvector. Defaults to ${env.POSTGRES_PORT} when rag_type is remote::pgvector.                                                                                          |
| db                  | string  | PostgreSQL database name for remote::pgvector. Defaults to ${env.POSTGRES_DATABASE} when rag_type is remote::pgvector.                                                                             |
| user                | string  | PostgreSQL user for remote::pgvector. Defaults to ${env.POSTGRES_USER} when rag_type is remote::pgvector.                                                                                          |
| password            | string  | PostgreSQL password for remote::pgvector. Defaults to ${env.POSTGRES_PASSWORD} when rag_type is remote::pgvector.                                                                                  |


## CORSConfiguration


CORS configuration.

CORS or 'Cross-Origin Resource Sharing' refers to the situations when a
frontend running in a browser has JavaScript code that communicates with a
backend, and the backend is in a different 'origin' than the frontend.

Useful resources:

  - [CORS in FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
  - [Wikipedia article](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing)
  - [What is CORS?](https://dev.to/akshay_chauhan/what-is-cors-explained-8f1)


| Field             | Type    | Description                                                                                                                                                                                                                                    |
|-------------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| allow_origins     | array   | A list of origins allowed for cross-origin requests. An origin is the combination of protocol (http, https), domain (myapp.com, localhost, localhost.tiangolo.com), and port (80, 443, 8080). Use ['*'] to allow all origins.                  |
| allow_credentials | boolean | Indicate that cookies should be supported for cross-origin requests                                                                                                                                                                            |
| allow_methods     | array   | A list of HTTP methods that should be allowed for cross-origin requests. You can use ['*'] to allow all standard methods.                                                                                                                      |
| allow_headers     | array   | A list of HTTP request headers that should be supported for cross-origin requests. You can use ['*'] to allow all headers. The Accept, Accept-Language, Content-Language and Content-Type headers are always allowed for simple CORS requests. |


## CompactionConfiguration


Configuration for conversation history compaction.

Compaction summarizes older conversation turns when their estimated
token count approaches the context window limit, keeping the
conversation usable instead of failing with HTTP 413. The
configuration here controls when compaction triggers and how much
recent context is preserved verbatim.

Attributes:
    enabled: Master switch. When False, compaction never triggers
        and other fields are inert.
    threshold_ratio: Trigger compaction when estimated input tokens
        exceed this fraction of the model's context window
        (clamped to 0.0..1.0).
    token_floor: Minimum estimated token count before compaction
        can trigger, regardless of threshold_ratio. Prevents
        triggering on very small context windows.
    buffer_turns: Initial number of recent turns to keep verbatim.
        The runtime applies a degrading guard — if these turns
        exceed the available budget, it reduces buffer_turns by
        one repeatedly until the budget fits, down to zero.
    buffer_max_ratio: Hard cap on the fraction of the context
        window the buffer zone may occupy, regardless of
        buffer_turns.


| Field            | Type    | Description                                                                                                 |
|------------------|---------|-------------------------------------------------------------------------------------------------------------|
| enabled          | boolean | When true, older conversation turns are summarized when estimated tokens approach the context window limit. |
| threshold_ratio  | number  | Trigger compaction when estimated tokens exceed this fraction of the model's context window (0.0-1.0).      |
| token_floor      | integer | Minimum token count before compaction can trigger. Prevents triggering on very small context windows.       |
| buffer_turns     | integer | Number of recent turns to keep verbatim.                                                                    |
| buffer_max_ratio | number  | Maximum fraction of context window the buffer zone can occupy, regardless of buffer_turns.                  |


## Configuration


Global service configuration.


| Field                  | Type   | Description                                                                                                                                                                                                                                                                                                             |
|------------------------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| name                   | string | Name of the service. That value will be used in REST API endpoints.                                                                                                                                                                                                                                                     |
| service                |        | This section contains Lightspeed Core Stack service configuration.                                                                                                                                                                                                                                                      |
| llama_stack            |        | This section contains Llama Stack configuration. Lightspeed Core Stack service can call Llama Stack in library mode or in server mode.                                                                                                                                                                                  |
| user_data_collection   |        | This section contains configuration for subsystem that collects user data(transcription history and feedbacks).                                                                                                                                                                                                         |
| database               |        | Configuration for database to store conversation IDs and other runtime data                                                                                                                                                                                                                                             |
| mcp_servers            | array  | MCP (Model Context Protocol) servers provide tools and capabilities to the AI agents. These are configured in this section. Only MCP servers defined in the lightspeed-stack.yaml configuration are available to the agents. Tools configured in the llama-stack run.yaml are not accessible to lightspeed-core agents. |
| authentication         |        | Authentication configuration                                                                                                                                                                                                                                                                                            |
| authorization          |        | Lightspeed Core Stack implements a modular authentication and authorization system with multiple authentication methods. Authorization is configurable through role-based access control. Authentication is handled through selectable modules configured via the module field in the authentication configuration.     |
| customization          |        | It is possible to customize Lightspeed Core Stack via this section. System prompt can be customized and also different parts of the service can be replaced by custom Python modules.                                                                                                                                   |
| inference              |        | One LLM provider and one its model might be selected as default ones. When no provider+model pair is specified in REST API calls (query endpoints), the default provider and model are used.                                                                                                                            |
| conversation_cache     |        |                                                                                                                                                                                                                                                                                                                         |
| compaction             |        | Controls when conversation history is summarized to keep the model's input below the context window limit. Disabled by default — when disabled, requests that exceed the window continue to surface as HTTP 413.                                                                                                        |
| approvals              |        | Settings for human-in-the-loop approval of MCP tool invocations                                                                                                                                                                                                                                                         |
| byok_rag               | array  | BYOK RAG configuration. This configuration can be used to reconfigure Llama Stack through its run.yaml configuration file                                                                                                                                                                                               |
| vector_store_providers | array  | Dynamic vector-store provider capacity for runtime POST /v1/vector-stores creates. Not the same as byok_rag (static registered corpora). When non-empty, exactly one entry must set default: true. Applied in unified synthesis only.                                                                                    |
| a2a_state              |        | Configuration for A2A protocol persistent state storage.                                                                                                                                                                                                                                                                |
| quota_handlers         |        | Quota handlers configuration                                                                                                                                                                                                                                                                                            |
| azure_entra_id         |        |                                                                                                                                                                                                                                                                                                                         |
| rlsapi_v1              |        | Configuration for the rlsapi v1 /infer endpoint used by the RHEL Lightspeed Command Line Assistant (CLA).                                                                                                                                                                                                               |
| splunk                 |        | Splunk HEC configuration for sending telemetry events.                                                                                                                                                                                                                                                                  |
| deployment_environment | string | Deployment environment name (e.g., 'development', 'staging', 'production'). Used in telemetry events.                                                                                                                                                                                                                   |
| rag                    |        | Configuration for all RAG strategies (inline and tool-based).                                                                                                                                                                                                                                                           |
| okp                    |        | OKP provider settings. Only used when 'okp' is listed in rag.inline or rag.tool.                                                                                                                                                                                                                                        |
| reranker               |        | Configuration for neural reranking of RAG chunks using cross-encoder.                                                                                                                                                                                                                                                   |
| skills                 |        | Agent skills configuration. Specifies paths to skill directories.                                                                                                                                                                                                                                                       |


## ConversationHistoryConfiguration


Conversation history configuration.


| Field    | Type   | Description                                                      |
|----------|--------|------------------------------------------------------------------|
| type     | string | Type of database where the conversation history is to be stored. |
| memory   |        | In-memory cache configuration                                    |
| sqlite   |        | SQLite database configuration                                    |
| postgres |        | PostgreSQL database configuration                                |


## CustomProfile


Custom profile customization for prompts and validation.


| Field   | Type   | Description                                       |
|---------|--------|---------------------------------------------------|
| path    | string | Path to Python modules containing custom profile. |
| prompts | object | Dictionary containing map of system prompts       |


## Customization


Service customization.


| Field                       | Type    | Description |
|-----------------------------|---------|-------------|
| profile_path                | string  |             |
| disable_query_system_prompt | boolean |             |
| disable_shield_ids_override | boolean |             |
| system_prompt_path          | string  |             |
| system_prompt               | string  |             |
| agent_card_path             | string  |             |
| agent_card_config           | object  |             |
| custom_profile              |         |             |


## DatabaseConfiguration


Database configuration.


| Field    | Type | Description                       |
|----------|------|-----------------------------------|
| sqlite   |      | SQLite database configuration     |
| postgres |      | PostgreSQL database configuration |


## FaissVectorStoreProvider


Dynamic FAISS vector-store provider (runtime create capacity).


| Field               | Type    | Description                                                                                                                                                         |
|---------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id                  | string  | Llama Stack vector_io provider_id (emitted as-is). Must match ``[a-z0-9_-]+`` and must not start with ``byok_``.                                                     |
| type                | string  | Product type for this dynamic vector-store provider. Must be ``faiss``.                                                                                             |
| embedding_model     | string  | Embedding model identification used for stores created against this provider. Required.                                                                             |
| embedding_dimension | integer | Dimensionality of embedding vectors for this provider. Required.                                                                                                    |
| default             | boolean | When true, this entry drives vector_stores.default_* in the synthesized Llama Stack config. Exactly one entry must set this when vector_store_providers is non-empty. |
| config              |         | FAISS storage settings for this provider.                                                                                                                           |


## FaissVectorStoreProviderConfig


Storage config for a FAISS dynamic vector-store provider.


| Field | Type   | Description                                  |
|-------|--------|----------------------------------------------|
| path  | string | On-disk FAISS/SQLite path for this provider. |


## InMemoryCacheConfig


In-memory cache configuration.


| Field       | Type    | Description                                             |
|-------------|---------|---------------------------------------------------------|
| max_entries | integer | Maximum number of entries stored in the in-memory cache |


## InferenceConfiguration


Inference configuration.


| Field            | Type    | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| default_model    | string  | Identification of default model used when no other model is specified.                                                                                                                                                                                                                                                                                                                                                                                                    |
| default_provider | string  | Identification of default provider used when no other model is specified.                                                                                                                                                                                                                                                                                                                                                                                                 |
| context_windows  | object  | Map of fully-qualified model identifier (e.g., "openai/gpt-4o-mini") to context window size in tokens. Used by the conversation compaction trigger to decide when older turns must be summarized before the input exceeds the window. Models absent from this map have no registered window — callers fall back to their own default or skip the token-based trigger.                                                                                            |
| providers        | array   | Unified-mode synthesis input (Decision S5): a high-level, backend-agnostic list of inference providers the synthesizer expands into Llama Stack provider entries. Lives at the configuration root so it survives a future backend change. A non-empty list signals unified mode. Empty (the default) leaves legacy/remote modes unaffected. The sibling default_model / default_provider keep their query-time routing meaning and are independent of this list. |
| max_infer_iters  | integer | Server-side default for the maximum number of inference iterations a model can perform in a single request. Prevents small models from looping indefinitely on tool calls. Per-request values take precedence over this default. Set to None to disable the limit.                                                                                                                                                                                                       |
| max_tool_calls   | integer | Server-side default for the maximum number of tool calls allowed in a single response. Prevents small models from exhausting the context window with repeated tool calls. Per-request values take precedence over this default. Set to None to disable the limit.                                                                                                                                                                                                  |


## JsonPathOperator


Supported operators for JSONPath evaluation.

Note: this is not a real model, just an enumeration of all supported JSONPath operators.




## JwkConfiguration


JWK (JSON Web Key) configuration.

A JSON Web Key (JWK) is a JavaScript Object Notation (JSON) data structure
that represents a cryptographic key.

Useful resources:

  - [JSON Web Key](https://openid.net/specs/draft-jones-json-web-key-03.html)
  - [RFC 7517](https://www.rfc-editor.org/rfc/rfc7517)


| Field             | Type   | Description                                                    |
|-------------------|--------|----------------------------------------------------------------|
| url               | string | HTTPS URL of the JWK (JSON Web Key) set used to validate JWTs. |
| jwt_configuration |        | JWT (JSON Web Token) configuration                             |


## JwtConfiguration


JWT (JSON Web Token) configuration.

JSON Web Token (JWT) is a compact, URL-safe means of representing
claims to be transferred between two parties.  The claims in a JWT
are encoded as a JSON object that is used as the payload of a JSON
Web Signature (JWS) structure or as the plaintext of a JSON Web
Encryption (JWE) structure, enabling the claims to be digitally
signed or integrity protected with a Message Authentication Code
(MAC) and/or encrypted.

Useful resources:

  - [JSON Web Token](https://en.wikipedia.org/wiki/JSON_Web_Token)
  - [RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)
  - [JSON Web Tokens](https://auth0.com/docs/secure/tokens/json-web-tokens)


| Field          | Type   | Description                                                    |
|----------------|--------|----------------------------------------------------------------|
| user_id_claim  | string | JWT claim name that uniquely identifies the user (subject ID). |
| username_claim | string | JWT claim name that provides the human-readable username.      |
| role_rules     | array  | Rules for extracting roles from JWT claims                     |


## JwtRoleRule


Rule for extracting roles from JWT claims.


| Field    | Type    | Description                                             |
|----------|---------|---------------------------------------------------------|
| jsonpath | string  | JSONPath expression to evaluate against the JWT payload |
| operator |         | JSON path comparison operator                           |
| negate   | boolean | If set to true, the meaning of the rule is negated      |
| value    |         | Value to compare against                                |
| roles    | array   | Roles to be assigned if the rule matches                |


## LlamaStackConfiguration


Llama stack configuration.

Llama Stack is a comprehensive system that provides a uniform set of tools
for building, scaling, and deploying generative AI applications, enabling
developers to create, integrate, and orchestrate multiple AI services and
capabilities into an adaptable setup.

Useful resources:

  - [Llama Stack](https://www.llama.com/products/llama-stack/)
  - [Python Llama Stack client](https://github.com/llamastack/llama-stack-client-python)
  - [Build AI Applications with Llama Stack](https://llamastack.github.io/)


| Field                      | Type    | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
|----------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| url                        | string  | URL to Llama Stack service; used when library mode is disabled. Must be a valid HTTP or HTTPS URL.                                                                                                                                                                                                                                                                                                                                                                                                                              |
| api_key                    | string  | API key to access Llama Stack service                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| use_as_library_client      | boolean | When set to true Llama Stack will be used in library mode, not in server mode (default)                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| library_client_config_path | string  | Path to configuration file used when Llama Stack is run in library mode                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| timeout                    | integer | Timeout in seconds for requests to Llama Stack service. Default is 180 seconds (3 minutes) to accommodate long-running RAG queries.                                                                                                                                                                                                                                                                                                                                                                                             |
| max_retries                | integer | Maximum number of connection attempts before giving up. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod).                                                                                                                                                                                                                                     |
| retry_delay                | integer | Delay in seconds between retry attempts. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod).                                                                                                                                                                                                                                                    |
| allow_degraded_mode        | boolean | If enabled, Lightspeed Core can be started even when Llama Stack is not accessible (valid for server mode only)                                                                                                                                                                                                                                                                                                                                                                                                                 |
| config                     |         | Backend-specific knobs for unified mode, where LCORE synthesizes the Llama Stack run.yaml instead of reading an external file. Holds the baseline selector, an optional profile path, and a raw native_override escape hatch. Backend-agnostic high-level sections (e.g. inference.providers) live at the configuration root, not here. Mutually exclusive with library_client_config_path; that cross-field check lives on the root Configuration model. When set in library mode, library_client_config_path is not required. |


## ModelContextProtocolServer


Model context protocol server configuration.

MCP (Model Context Protocol) servers provide tools and capabilities to the
AI agents. These are configured by this structure. Only MCP servers
defined in the lightspeed-stack.yaml configuration are available to the
agents. Tools configured in the llama-stack run.yaml are not accessible to
lightspeed-core agents.

Useful resources:

- [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)
- [MCP FAQs](https://modelcontextprotocol.io/faqs)
- [Wikipedia article](https://en.wikipedia.org/wiki/Model_Context_Protocol)


| Field                 | Type    | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|-----------------------|---------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| name                  | string  | MCP server name that must be unique                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| provider_id           | string  | MCP provider identification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| url                   | string  | URL of the MCP server                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| authorization_headers | object  | Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 3 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client-provided token in the header. To specify this use a string 'client' instead of the file path. 3. Usage of the oauth token in the header. To specify this use a string 'oauth' instead of the file path. |
| headers               | array   | List of HTTP header names to automatically forward from the incoming request to this MCP server. Headers listed here are extracted from the original client request and included when calling the MCP server. This is useful when infrastructure components (e.g. API gateways) inject headers that MCP servers need, such as x-rh-identity in HCC. Header matching is case-insensitive. These headers are additive with authorization_headers and MCP-HEADERS.                                                |
| require_approval      |         | When to require human approval for tool invocations. 'always' requires approval for all tools, 'never' auto-approves, or use ApprovalFilter for granular control.                                                                                                                                                                                                                                                                                                                                              |
| timeout               | integer | Timeout in seconds for requests to the MCP server. If not specified, the default timeout from Llama Stack will be used. Note: This field is reserved for future use when Llama Stack adds timeout support.                                                                                                                                                                                                                                                                                                     |


## OkpConfiguration


OKP (Offline Knowledge Portal) provider configuration.

Controls provider-specific behaviour for the OKP vector store.
Only relevant when ``"okp"`` is listed in ``rag.inline`` or ``rag.tool``.


| Field              | Type    | Description                                                                                                                                                         |
|--------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| rhokp_url          | string  | Base URL for the OKP server (http or https). Set to `${env.RH_SERVER_OKP}` in YAML to use the environment variable. When unset, the default from constants is used. |
| offline            | boolean | When True, use parent_id for OKP chunk source URLs. When False, use reference_url for chunk source URLs.                                                            |
| chunk_filter_query | string  | Additional OKP filter query applied to every OKP search request. Use Solr boolean syntax, e.g. 'product:ansible AND product:*openshift*'.                           |


## PgvectorVectorStoreProvider


Dynamic pgvector vector-store provider (runtime create capacity).


| Field               | Type    | Description                                                                                                                                                         |
|---------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id                  | string  | Llama Stack vector_io provider_id (emitted as-is). Must match ``[a-z0-9_-]+`` and must not start with ``byok_``.                                                     |
| type                | string  | Product type for this dynamic vector-store provider. Must be ``pgvector``.                                                                                          |
| embedding_model     | string  | Embedding model identification used for stores created against this provider. Required.                                                                             |
| embedding_dimension | integer | Dimensionality of embedding vectors for this provider. Required.                                                                                                    |
| default             | boolean | When true, this entry drives vector_stores.default_* in the synthesized Llama Stack config. Exactly one entry must set this when vector_store_providers is non-empty. |
| config              |         | pgvector connection settings for this provider.                                                                                                                     |


## PgvectorVectorStoreProviderConfig


Storage config for a pgvector dynamic vector-store provider.


| Field    | Type   | Description                                                     |
|----------|--------|-----------------------------------------------------------------|
| host     | string | PostgreSQL host. Defaults to ${env.POSTGRES_HOST}.              |
| port     | string | PostgreSQL port. Defaults to ${env.POSTGRES_PORT}.              |
| db       | string | PostgreSQL database name. Defaults to ${env.POSTGRES_DATABASE}. |
| user     | string | PostgreSQL user. Defaults to ${env.POSTGRES_USER}.              |
| password | string | PostgreSQL password. Defaults to ${env.POSTGRES_PASSWORD}.      |


## PostgreSQLDatabaseConfiguration


PostgreSQL database configuration.

PostgreSQL database is used by Lightspeed Core Stack service for storing
information about conversation IDs. It can also be leveraged to store
conversation history and information about quota usage.

Useful resources:

- [Psycopg: connection classes](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [PostgreSQL connection strings](https://www.connectionstrings.com/postgresql/)
- [How to Use PostgreSQL in Python](https://www.freecodecamp.org/news/postgresql-in-python/)


| Field        | Type    | Description                                                                                                             |
|--------------|---------|-------------------------------------------------------------------------------------------------------------------------|
| host         | string  | Database server host or socket directory                                                                                |
| port         | integer | Database server port                                                                                                    |
| db           | string  | Database name to connect to                                                                                             |
| user         | string  | Database user name used to authenticate                                                                                 |
| password     | string  | Password used to authenticate                                                                                           |
| namespace    | string  | Database namespace                                                                                                      |
| ssl_mode     | string  | SSL mode                                                                                                                |
| gss_encmode  | string  | This option determines whether or with what priority a secure GSS TCP/IP connection will be negotiated with the server. |
| ca_cert_path | string  | Path to CA certificate                                                                                                  |


## QuotaHandlersConfiguration


Quota limiter configuration.

It is possible to limit quota usage per user or per service or services
(that typically run in one cluster). Each limit is configured as a separate
_quota limiter_. It can be of type `user_limiter` or `cluster_limiter`
(which is name that makes sense in OpenShift deployment).


| Field                | Type    | Description                                           |
|----------------------|---------|-------------------------------------------------------|
| sqlite               |         | SQLite database configuration                         |
| postgres             |         | PostgreSQL database configuration                     |
| limiters             | array   | Quota limiters configuration                          |
| scheduler            |         | Quota scheduler configuration                         |
| enable_token_history | boolean | Enables storing information about token usage history |


## QuotaLimiterConfiguration


Configuration for one quota limiter.

There are three configuration options for each limiter:

1. ``period`` is specified in a human-readable form, see
   https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-INTERVAL-INPUT
   for all possible options. When the end of the period is reached, the
   quota is reset or increased.
2. ``initial_quota`` is the value set at the beginning of the period.
3. ``quota_increase`` is the value (if specified) used to increase the
   quota when the period is reached.

There are two basic use cases:

1. When the quota needs to be reset to a specific value periodically (for
   example on a weekly or monthly basis), set ``initial_quota`` to the
   required value.
2. When the quota needs to be increased by a specific value periodically
   (for example on a daily basis), set ``quota_increase``.


| Field          | Type    | Description                                                |
|----------------|---------|------------------------------------------------------------|
| type           | string  | Quota limiter type, either user_limiter or cluster_limiter |
| name           | string  | Human readable quota limiter name                          |
| initial_quota  | integer | Quota set at beginning of the period                       |
| quota_increase | integer | Delta value used to increase quota when period is reached  |
| period         | string  | Period specified in human readable form                    |


## QuotaSchedulerConfiguration


Quota scheduler configuration.


| Field                       | Type    | Description                                                                                                                                                         |
|-----------------------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| period                      | integer | Quota scheduler period specified in seconds                                                                                                                         |
| database_reconnection_count | integer | Database reconnection count on startup. When database for quota is not available on startup, the service tries to reconnect N times with specified delay.           |
| database_reconnection_delay | integer | Database reconnection delay specified in seconds. When database for quota is not available on startup, the service tries to reconnect N times with specified delay. |


## RHIdentityConfiguration


Red Hat Identity authentication configuration.


| Field                 | Type    | Description                                                                                                                          |
|-----------------------|---------|--------------------------------------------------------------------------------------------------------------------------------------|
| required_entitlements | array   | List of all required entitlements.                                                                                                   |
| max_header_size       | integer | Maximum allowed size in bytes for the base64-encoded x-rh-identity header. Headers exceeding this size are rejected before decoding. |


## RagConfiguration


RAG strategy configuration.

Controls which RAG sources are used for inline and tool-based retrieval.

Each strategy lists RAG IDs to include. The special ID ``"okp"`` defined in constants,
activates the OKP provider; all other IDs refer to entries in ``byok_rag``.

Backward compatibility:
    - ``inline`` defaults to ``[]`` (no inline RAG).
    - ``tool`` defaults to ``[]`` (no tool RAG).

If no RAG strategy is defined (inline and tool are empty),
the RAG tool will register all stores available to llama-stack.


| Field  | Type  | Description                                                                                                                                                                            |
|--------|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| inline | array | RAG IDs whose sources are injected as context before the LLM call. Use 'okp' to enable OKP inline RAG. Empty by default (no inline RAG).                                               |
| tool   | array | RAG IDs made available to the LLM as a file_search tool. Use 'okp' to include the OKP vector store. When omitted, all registered BYOK vector stores are used (backward compatibility). |


## RerankerConfiguration


Reranker configuration for RAG chunk reranking.


| Field   | Type    | Description                                                                                                                      |
|---------|---------|----------------------------------------------------------------------------------------------------------------------------------|
| enabled | boolean | When True, reranking applied to RAG chunks. When False, reranking is disabled and original scoring used.                         |
| model   | string  | Cross-encoder model name for reranking RAG chunks. Defaults to 'cross-encoder/ms-marco-MiniLM-L6-v2' from sentence-transformers. |


## RlsapiV1Configuration


Configuration for the rlsapi v1 /infer endpoint.

Settings specific to the RHEL Lightspeed Command Line Assistant (CLA)
stateless inference endpoint. Kept separate from shared configuration
sections so that CLA-specific options do not affect other endpoints.


| Field               | Type    | Description                                                                                                                                                                                                                                                                                |
|---------------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| allow_verbose_infer | boolean | Allow /v1/infer to return extended metadata (tool_calls, rag_chunks, token_usage) when the client sends "include_metadata": true. Should NOT be enabled in production. If production use is needed, consider RBAC-based access control via an Action.RLSAPI_V1_INFER authorization rule.   |
| quota_subject       | string  | Identity field used as the quota subject for /v1/infer. When set, token quota enforcement is enabled for this endpoint. Requires quota_handlers to be configured. "org_id" and "system_id" require rh-identity authentication; falls back to user_id when rh-identity data is unavailable. |


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field   | Type   | Description                                  |
|---------|--------|----------------------------------------------|
| db_path | string | Path to file where SQLite database is stored |


## ServiceConfiguration


Service configuration.

Lightspeed Core Stack is a REST API service that accepts requests on a
specified hostname and port. It is also possible to enable authentication
and specify the number of Uvicorn workers. When more workers are specified,
the service can handle requests concurrently.


| Field        | Type    | Description                                                            |
|--------------|---------|------------------------------------------------------------------------|
| host         | string  | Service hostname                                                       |
| port         | integer | Service port                                                           |
| base_url     | string  | Externally reachable base URL for the service; needed for A2A support. |
| auth_enabled | boolean | Enables the authentication subsystem                                   |
| workers      | integer | Number of Uvicorn worker processes to start                            |
| color_log    | boolean | Enables colorized logging                                              |
| access_log   | boolean | Enables logging of all access information                              |
| tls_config   |         | Transport Layer Security configuration for HTTPS support               |
| root_path    | string  | ASGI root path for serving behind a reverse proxy on a subpath         |
| cors         |         | Cross-Origin Resource Sharing configuration for cross-domain requests  |


## SkillsConfiguration


Agent skills configuration.

Specifies paths to skill directories. Skill metadata (name, description)
is read from SKILL.md frontmatter at startup.

Each path can point to either:
- A directory containing a SKILL.md file (single skill)
- A directory containing subdirectories with SKILL.md files (multiple skills)

Paths are validated at startup to ensure they exist and contain valid SKILL.md files.


| Field | Type  | Description                                                                |
|-------|-------|----------------------------------------------------------------------------|
| paths | array | Paths to skill directories or directories containing skill subdirectories. |


## SplunkConfiguration


Splunk HEC (HTTP Event Collector) configuration.

Splunk HEC allows sending events directly to Splunk over HTTP/HTTPS.
This configuration is used to send telemetry events for inference
requests to the corporate Splunk deployment.

Useful resources:

  - [Splunk HEC Docs](https://docs.splunk.com/Documentation/SplunkCloud)
  - [About HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data)


| Field      | Type    | Description                                                  |
|------------|---------|--------------------------------------------------------------|
| enabled    | boolean | Enable or disable Splunk HEC integration.                    |
| url        | string  | Splunk HEC endpoint URL.                                     |
| token_path | string  | Path to file containing the Splunk HEC authentication token. |
| index      | string  | Target Splunk index for events.                              |
| source     | string  | Event source identifier.                                     |
| timeout    | integer | HTTP timeout in seconds for HEC requests.                    |
| verify_ssl | boolean | Whether to verify SSL certificates for HEC endpoint.         |


## TLSConfiguration


TLS configuration.

Transport Layer Security (TLS) is a cryptographic protocol designed to
provide communications security over a computer network, such as the
Internet. The protocol is widely used in applications such as email,
instant messaging, and voice over IP, but its use in securing HTTPS remains
the most publicly visible.

Useful resources:

  - [FastAPI HTTPS Deployment](https://fastapi.tiangolo.com/deployment/https/)
  - [Transport Layer Security Overview](https://en.wikipedia.org/wiki/Transport_Layer_Security)
  - [What is TLS](https://www.ssltrust.eu/learning/ssl/transport-layer-security-tls)


| Field                | Type   | Description                                                              |
|----------------------|--------|--------------------------------------------------------------------------|
| tls_certificate_path | string | SSL/TLS certificate file path for HTTPS support.                         |
| tls_key_path         | string | SSL/TLS private key file path for HTTPS support.                         |
| tls_key_password     | string | Path to file containing the password to decrypt the SSL/TLS private key. |


## TrustedProxyConfiguration


Configuration for trusted-proxy auth module.


| Field                    | Type   | Description                                                                                                                                                                                                                                                                                                      |
|--------------------------|--------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| user_header              | string | HTTP header containing the forwarded user identity.                                                                                                                                                                                                                                                              |
| allowed_service_accounts | array  | Optional allowlist of Kubernetes ServiceAccount identities permitted to act as trusted proxies. When set to null/omitted, any ServiceAccount with a valid token is accepted. When set to a non-empty list, only the listed ServiceAccounts are allowed. An empty list behaves the same as null (no restriction). |


## TrustedProxyServiceAccount


A Kubernetes ServiceAccount identity for trusted-proxy allowlist.


| Field     | Type   | Description                                 |
|-----------|--------|---------------------------------------------|
| namespace | string | Kubernetes namespace of the ServiceAccount. |
| name      | string | Name of the Kubernetes ServiceAccount.      |


## UnifiedInferenceProvider


A high-level inference provider entry for unified-mode synthesis.

Operators describe inference providers at this high level (backend-agnostic
vocabulary) instead of authoring raw Llama Stack provider blocks. The
synthesizer (`apply_high_level_inference`) expands each entry into a Llama
Stack `providers.inference` entry, mapping `type` to a `provider_type` and
emitting `${env.<VAR>}` references for secrets (never literal values).

Attributes:
    type: Canonical provider identifier. Vendor-neutral so it survives a
        future backend change; each backend-specific synthesizer maps it to
        its own provider vocabulary.
    id: Optional identifier emitted as the Llama Stack provider_id. When
        omitted, synthesized as type with underscores hyphenated. If set,
        must be non-empty after stripping whitespace and may contain only
        lowercase letters, digits, underscores, and hyphens.
    api_key_env: Name of the environment variable holding the provider API
        key. Emitted verbatim as `${env.<name>}` so the secret never lands
        on disk resolved.
    allowed_models: Optional allow-list of model identifiers passed through
        to the synthesized provider config.
    extra: Additional provider-config keys merged verbatim into the
        synthesized provider's `config` block — an escape hatch for
        provider-specific knobs not modeled here.


| Field          | Type   | Description                                                                                                                                                  |
|----------------|--------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| type           | string | Canonical, backend-agnostic provider identifier mapped to a Llama Stack provider_type by the synthesizer.                                                    |
| id             | string | Optional identifier emitted as the Llama Stack provider_id. When omitted, synthesized as type with underscores hyphenated. If set, must be non-empty after stripping whitespace and may contain only lowercase letters, digits, underscores, and hyphens. |
| api_key_env    | string | Name of the environment variable holding the provider API key. Emitted as a ${env.<name>} reference so the secret is never written to disk in resolved form. |
| allowed_models | array  | Optional allow-list of model identifiers for this provider.                                                                                                  |
| extra          | object | Additional provider-config keys merged verbatim into the synthesized provider's config block.                                                                |


## UnifiedLlamaStackConfig


Backend-specific knobs for unified-mode Llama Stack synthesis.

Per Decision S5 of the design spike, backend-agnostic high-level sections
(inference, ...) live at the configuration root, not here. This block holds
only the Llama-Stack-specific synthesis controls: which baseline to start
from, an optional profile file, and a raw native_override escape hatch.

During synthesis from the default baseline or a profile, LCORE ensures the
Llama Stack MCP tool_runtime provider (`provider_id: model-context-protocol`,
`provider_type: remote::model-context-protocol`) is present so static
`mcp_servers` and dynamic MCP registration work. That ensure is skipped when
`baseline: empty` (migration / blank-slate); supply MCP via `native_override`
in that case.

Attributes:
    baseline: Synthesis starting point. "default" begins from LCORE's
        built-in baseline (src/data/default_run.yaml); "empty" begins from
        an empty dict (used by the migration tool for an exact round-trip).
        Ignored when `profile` is set.
    profile: Optional path to a user-authored run.yaml-shaped file used as
        the synthesis baseline. Relative paths resolve against the directory
        of the loaded lightspeed-stack.yaml.
    native_override: Raw Llama Stack schema deep-merged last (maps merge
        recursively, lists and scalars replace). The escape hatch for
        anything the high-level sections do not express.


| Field           | Type   | Description                                                                                                                |
|-----------------|--------|----------------------------------------------------------------------------------------------------------------------------|
| baseline        | string | Synthesis starting point: 'default' uses LCORE's built-in baseline, 'empty' starts from {}. Ignored when 'profile' is set. |
| profile         | string | Path to a run.yaml-shaped baseline file. Relative paths resolve against the directory of the loaded lightspeed-stack.yaml. |
| native_override | object | Raw Llama Stack schema deep-merged last (maps merge recursively; lists and scalars replace).                               |


## UserDataCollection


User data collection configuration.


| Field               | Type    | Description                                                                        |
|---------------------|---------|------------------------------------------------------------------------------------|
| feedback_enabled    | boolean | When set to true the user feedback is stored and later sent for analysis.          |
| feedback_storage    | string  | Path to directory where feedback will be saved for further processing.             |
| transcripts_enabled | boolean | When set to true the conversation history is stored and later sent for analysis.   |
| transcripts_storage | string  | Path to directory where conversation history will be saved for further processing. |
