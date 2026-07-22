# Lightspeed Core Stack



---

# 📋 Schemas for successful responses models



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


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration for A2A state storage. |
| postgres |  | PostgreSQL database configuration for A2A state storage. |


## APIKeyTokenConfiguration


API Key Token configuration.


| Field | Type | Description |
|-------|------|-------------|
| api_key | string |  |


## AccessRule


Rule defining what actions a role can perform.


| Field | Type | Description |
|-------|------|-------------|
| role | string | Name of the role |
| actions | array | Allowed actions for this role |


## Action


Available actions in the system.

Note: this is not a real model, just an enumeration of all action names.




## AllowedToolsFilter


Filter configuration for restricting which MCP tools can be used.

:param tool_names: (Optional) List of specific tool names that are allowed


| Field | Type | Description |
|-------|------|-------------|
| tool_names | array |  |


## ApprovalFilter


Granular approval control for specific MCP tools.

Attributes:
    always: Tool names that always require human approval before execution.
    never: Tool names that never require approval (pre-approved).


| Field | Type | Description |
|-------|------|-------------|
| always | array | List of tool names that always require human approval |
| never | array | List of tool names that never require approval |


## ApprovalsConfiguration


Configuration for human-in-the-loop approvals.

Attributes:
    approval_timeout_seconds: How long approval requests remain pending
        before expiring.
    approval_retention_days: How long to retain decided approvals for audit
        purposes before cleanup.


| Field | Type | Description |
|-------|------|-------------|
| approval_timeout_seconds | integer | Seconds before pending approval requests expire |
| approval_retention_days | integer | Days to retain decided approvals before cleanup |


## AuthenticationConfiguration


Authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| module | string |  |
| skip_tls_verification | boolean |  |
| skip_for_health_probes | boolean | Skip authorization for readiness and liveness probes |
| skip_for_metrics | boolean | Skip authorization for the /metrics endpoint |
| k8s_cluster_api | string |  |
| k8s_ca_cert_path | string |  |
| jwk_config |  |  |
| api_key_config |  |  |
| rh_identity_config |  |  |
| trusted_proxy_config |  |  |


## AuthorizationConfiguration


Authorization configuration.


| Field | Type | Description |
|-------|------|-------------|
| access_rules | array | Rules for role-based access control |


## AuthorizedResponse


Model representing a response to an authorization request.

Attributes:
    user_id: The ID of the logged in user.
    username: The name of the logged in user.
    skip_userid_check: Whether to skip the user ID check.


| Field | Type | Description |
|-------|------|-------------|
| user_id | string | User ID, for example UUID |
| username | string | User name |
| skip_userid_check | boolean | Whether to skip the user ID check |


## AzureEntraIdConfiguration


Microsoft Entra ID authentication attributes for Azure.


| Field | Type | Description |
|-------|------|-------------|
| tenant_id | string |  |
| client_id | string |  |
| client_secret | string |  |
| scope | string | Azure Cognitive Services scope for token requests. Override only if using a different Azure service. |


## ByokRag


BYOK (Bring Your Own Knowledge) RAG configuration.


| Field | Type | Description |
|-------|------|-------------|
| rag_id | string | Unique RAG ID |
| rag_type | string | Type of RAG database (e.g. 'inline::faiss', 'remote::pgvector'). |
| embedding_model | string | Embedding model identification |
| embedding_dimension | integer | Dimensionality of embedding vectors. |
| vector_db_id | string | Vector database identification. |
| db_path | string | Path to RAG database. Required for inline::faiss. |
| score_multiplier | number | Multiplier applied to relevance scores from this vector store. Used to weight results when querying multiple knowledge sources. Values > 1 boost this store's results; values < 1 reduce them. |
| host | string | PostgreSQL host for remote::pgvector. Defaults to ${env.POSTGRES_HOST} when rag_type is remote::pgvector. |
| port | string | PostgreSQL port for remote::pgvector. Defaults to ${env.POSTGRES_PORT} when rag_type is remote::pgvector. |
| db | string | PostgreSQL database name for remote::pgvector. Defaults to ${env.POSTGRES_DATABASE} when rag_type is remote::pgvector. |
| user | string | PostgreSQL user for remote::pgvector. Defaults to ${env.POSTGRES_USER} when rag_type is remote::pgvector. |
| password | string | PostgreSQL password for remote::pgvector. Defaults to ${env.POSTGRES_PASSWORD} when rag_type is remote::pgvector. |


## CORSConfiguration


CORS configuration.

CORS or 'Cross-Origin Resource Sharing' refers to the situations when a
frontend running in a browser has JavaScript code that communicates with a
backend, and the backend is in a different 'origin' than the frontend.

Useful resources:

  - [CORS in FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
  - [Wikipedia article](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing)
  - [What is CORS?](https://dev.to/akshay_chauhan/what-is-cors-explained-8f1)


| Field | Type | Description |
|-------|------|-------------|
| allow_origins | array | A list of origins allowed for cross-origin requests. An origin is the combination of protocol (http, https), domain (myapp.com, localhost, localhost.tiangolo.com), and port (80, 443, 8080). Use ['*'] to allow all origins. |
| allow_credentials | boolean | Indicate that cookies should be supported for cross-origin requests |
| allow_methods | array | A list of HTTP methods that should be allowed for cross-origin requests. You can use ['*'] to allow all standard methods. |
| allow_headers | array | A list of HTTP request headers that should be supported for cross-origin requests. You can use ['*'] to allow all headers. The Accept, Accept-Language, Content-Language and Content-Type headers are always allowed for simple CORS requests. |


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


| Field | Type | Description |
|-------|------|-------------|
| enabled | boolean | When true, older conversation turns are summarized when estimated tokens approach the context window limit. |
| threshold_ratio | number | Trigger compaction when estimated tokens exceed this fraction of the model's context window (0.0-1.0). |
| token_floor | integer | Minimum token count before compaction can trigger. Prevents triggering on very small context windows. |
| buffer_turns | integer | Number of recent turns to keep verbatim. |
| buffer_max_ratio | number | Maximum fraction of context window the buffer zone can occupy, regardless of buffer_turns. |


## Configuration


Global service configuration.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Name of the service. That value will be used in REST API endpoints. |
| service |  | This section contains Lightspeed Core Stack service configuration. |
| llama_stack |  | This section contains Llama Stack configuration. Lightspeed Core Stack service can call Llama Stack in library mode or in server mode. |
| user_data_collection |  | This section contains configuration for subsystem that collects user data(transcription history and feedbacks). |
| database |  | Configuration for database to store conversation IDs and other runtime data |
| mcp_servers | array | MCP (Model Context Protocol) servers provide tools and capabilities to the AI agents. These are configured in this section. Only MCP servers defined in the lightspeed-stack.yaml configuration are available to the agents. Tools configured in the llama-stack run.yaml are not accessible to lightspeed-core agents. |
| authentication |  | Authentication configuration |
| authorization |  | Lightspeed Core Stack implements a modular authentication and authorization system with multiple authentication methods. Authorization is configurable through role-based access control. Authentication is handled through selectable modules configured via the module field in the authentication configuration. |
| customization |  | It is possible to customize Lightspeed Core Stack via this section. System prompt can be customized and also different parts of the service can be replaced by custom Python modules. |
| inference |  | One LLM provider and one its model might be selected as default ones. When no provider+model pair is specified in REST API calls (query endpoints), the default provider and model are used. |
| conversation_cache |  |  |
| compaction |  | Controls when conversation history is summarized to keep the model's input below the context window limit. Disabled by default — when disabled, requests that exceed the window continue to surface as HTTP 413. |
| approvals |  | Settings for human-in-the-loop approval of MCP tool invocations |
| byok_rag | array | BYOK RAG configuration. This configuration can be used to reconfigure Llama Stack through its run.yaml configuration file |
| a2a_state |  | Configuration for A2A protocol persistent state storage. |
| quota_handlers |  | Quota handlers configuration |
| azure_entra_id |  |  |
| rlsapi_v1 |  | Configuration for the rlsapi v1 /infer endpoint used by the RHEL Lightspeed Command Line Assistant (CLA). |
| splunk |  | Splunk HEC configuration for sending telemetry events. |
| deployment_environment | string | Deployment environment name (e.g., 'development', 'staging', 'production'). Used in telemetry events. |
| rag |  | Configuration for all RAG strategies (inline and tool-based). |
| okp |  | OKP provider settings. Only used when 'okp' is listed in rag.inline or rag.tool. |
| reranker |  | Configuration for neural reranking of RAG chunks using cross-encoder. |
| skills |  | Agent skills configuration. Specifies paths to skill directories. |


## ConfigurationResponse


Success response model for the config endpoint.

Attributes:
    configuration: Parsed application configuration returned to the client.


| Field | Type | Description |
|-------|------|-------------|
| configuration |  |  |


## ConversationData


Model representing conversation data returned by cache list operations.

Attributes:
    conversation_id: The conversation ID
    topic_summary: The topic summary for the conversation (can be None)
    last_message_timestamp: The timestamp of the last message in the conversation


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string |  |
| topic_summary | string |  |
| last_message_timestamp | number |  |


## ConversationDeleteResponse


Response for deleting a conversation.


| Field | Type | Description |
|-------|------|-------------|
| deleted | boolean | Whether the deletion was successful. |
| conversation_id | string | Conversation identifier that was passed to delete. |


## ConversationDetails


Model representing the details of a user conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    created_at: When the conversation was created.
    last_message_at: When the last message was sent.
    message_count: Number of user messages in the conversation.
    last_used_model: The last model used for the conversation.
    last_used_provider: The provider of the last used model.
    topic_summary: The topic summary for the conversation.

Example:
    ```python
    conversation = ConversationDetails(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        created_at="2024-01-01T00:00:00Z",
        last_message_at="2024-01-01T00:05:00Z",
        message_count=5,
        last_used_model="gemini/gemini-2.0-flash",
        last_used_provider="gemini",
        topic_summary="Openshift Microservices Deployment Strategies",
    )
    ```


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| created_at | string | When the conversation was created |
| last_message_at | string | When the last message was sent |
| message_count | integer | Number of user messages in the conversation |
| last_used_model | string | Identification of the last model used for the conversation |
| last_used_provider | string | Identification of the last provider used for the conversation |
| topic_summary | string | Topic summary for the conversation |


## ConversationHistoryConfiguration


Conversation history configuration.


| Field | Type | Description |
|-------|------|-------------|
| type | string | Type of database where the conversation history is to be stored. |
| memory |  | In-memory cache configuration |
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |


## ConversationResponse


Model representing a response for retrieving a conversation.

Attributes:
    conversation_id: The conversation ID (UUID).
    chat_history: The chat history as a list of conversation turns.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | Conversation ID (UUID) |
| chat_history | array | The simplified chat history as a list of conversation turns |


## ConversationTurn


Model representing a single conversation turn.

Attributes:
    messages: List of messages in this turn.
    tool_calls: List of tool calls made in this turn.
    tool_results: List of tool results from this turn.
    provider: Provider identifier used for this turn.
    model: Model identifier used for this turn.
    started_at: ISO 8601 timestamp when the turn started.
    completed_at: ISO 8601 timestamp when the turn completed.


| Field | Type | Description |
|-------|------|-------------|
| messages | array | List of messages in this turn |
| tool_calls | array | List of tool calls made in this turn |
| tool_results | array | List of tool results from this turn |
| provider | string | Provider identifier used for this turn |
| model | string | Model identifier used for this turn |
| started_at | string | ISO 8601 timestamp when the turn started |
| completed_at | string | ISO 8601 timestamp when the turn completed |


## ConversationUpdateResponse


Model representing a response for updating a conversation topic summary.

Attributes:
    conversation_id: The conversation ID (UUID) that was updated.
    success: Whether the update was successful.
    message: A message about the update result.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The conversation ID (UUID) that was updated |
| success | boolean | Whether the update was successful |
| message | string | A message about the update result |


## ConversationsListResponse


Model representing a response for listing conversations of a user.

Attributes:
    conversations: List of conversation details associated with the user.


| Field | Type | Description |
|-------|------|-------------|
| conversations | array |  |


## ConversationsListResponseV2


Model representing a response for listing conversations of a user.

Attributes:
    conversations: List of conversation data associated with the user.


| Field | Type | Description |
|-------|------|-------------|
| conversations | array |  |


## CustomProfile


Custom profile customization for prompts and validation.


| Field | Type | Description |
|-------|------|-------------|
| path | string | Path to Python modules containing custom profile. |
| prompts | object | Dictionary containing map of system prompts |


## Customization


Service customization.


| Field | Type | Description |
|-------|------|-------------|
| profile_path | string |  |
| disable_query_system_prompt | boolean |  |
| disable_shield_ids_override | boolean |  |
| system_prompt_path | string |  |
| system_prompt | string |  |
| agent_card_path | string |  |
| agent_card_config | object |  |
| custom_profile |  |  |


## DatabaseConfiguration


Database configuration.


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |


## FeedbackResponse


Model representing a response to a feedback request.

Attributes:
    response: The response of the feedback request.


| Field | Type | Description |
|-------|------|-------------|
| response | string | The response of the feedback request. |


## FeedbackStatusUpdateResponse


Model representing a response to a feedback status update request.

Attributes:
    status: The previous and current status of the service and who updated it.


| Field | Type | Description |
|-------|------|-------------|
| status | object |  |


## FileResponse


Response model containing a file object.

Attributes:
    id: File ID.
    filename: File name.
    bytes: File size in bytes.
    created_at: Unix timestamp when created.
    purpose: File purpose.
    object: Object type (always "file").


| Field | Type | Description |
|-------|------|-------------|
| id | string | File ID |
| filename | string | File name |
| bytes | integer | File size in bytes |
| created_at | integer | Unix timestamp when created |
| purpose | string | File purpose |
| object | string | Object type |


## InMemoryCacheConfig


In-memory cache configuration.


| Field | Type | Description |
|-------|------|-------------|
| max_entries | integer | Maximum number of entries stored in the in-memory cache |


## InferenceConfiguration


Inference configuration.


| Field | Type | Description |
|-------|------|-------------|
| default_model | string | Identification of default model used when no other model is specified. |
| default_provider | string | Identification of default provider used when no other model is specified. |
| context_windows | object | Map of fully-qualified model identifier (e.g., "openai/gpt-4o-mini") to context window size in tokens. Used by the conversation compaction trigger to decide when older turns must be summarized before the input exceeds the window. Models absent from this map have no registered window — callers fall back to their own default or skip the token-based trigger. |


## InfoResponse


Model representing a response to an info request.

Attributes:
    name: Service name.
    service_version: Service version.
    llama_stack_version: Llama Stack version.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Service name |
| service_version | string | Service version |
| llama_stack_version | string | Llama Stack version |


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


| Field | Type | Description |
|-------|------|-------------|
| url | string | HTTPS URL of the JWK (JSON Web Key) set used to validate JWTs. |
| jwt_configuration |  | JWT (JSON Web Token) configuration |


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


| Field | Type | Description |
|-------|------|-------------|
| user_id_claim | string | JWT claim name that uniquely identifies the user (subject ID). |
| username_claim | string | JWT claim name that provides the human-readable username. |
| role_rules | array | Rules for extracting roles from JWT claims |


## JwtRoleRule


Rule for extracting roles from JWT claims.


| Field | Type | Description |
|-------|------|-------------|
| jsonpath | string | JSONPath expression to evaluate against the JWT payload |
| operator |  | JSON path comparison operator |
| negate | boolean | If set to true, the meaning of the rule is negated |
| value |  | Value to compare against |
| roles | array | Roles to be assigned if the rule matches |


## LivenessResponse


Model representing a response to a liveness request.

Attributes:
    alive: If app is alive.


| Field | Type | Description |
|-------|------|-------------|
| alive | boolean | Flag indicating that the app is alive |


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


| Field | Type | Description |
|-------|------|-------------|
| url | string | URL to Llama Stack service; used when library mode is disabled. Must be a valid HTTP or HTTPS URL. |
| api_key | string | API key to access Llama Stack service |
| use_as_library_client | boolean | When set to true Llama Stack will be used in library mode, not in server mode (default) |
| library_client_config_path | string | Path to configuration file used when Llama Stack is run in library mode |
| timeout | integer | Timeout in seconds for requests to Llama Stack service. Default is 180 seconds (3 minutes) to accommodate long-running RAG queries. |
| max_retries | integer | Maximum number of connection attempts before giving up. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod). |
| retry_delay | integer | Delay in seconds between retry attempts. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod). |
| allow_degraded_mode | boolean | If enabled, Lightspeed Core can be started even when Llama Stack is not accessible (valid for server mode only) |


## MCPClientAuthOptionsResponse


Response containing MCP servers that accept client-provided authorization.

Attributes:
    servers: MCP servers that declare client authentication headers.


| Field | Type | Description |
|-------|------|-------------|
| servers | array | List of MCP servers that accept client-provided authorization |


## MCPListToolsTool


Tool definition returned by MCP list tools operation.

:param input_schema: JSON schema defining the tool's input parameters
:param name: Name of the tool
:param description: (Optional) Description of what the tool does


| Field | Type | Description |
|-------|------|-------------|
| input_schema | object |  |
| name | string |  |
| description | string |  |


## MCPServerAuthInfo


Information about MCP server client authentication options.


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| client_auth_headers | array | List of authentication header names for client-provided tokens |


## MCPServerDeleteResponse


Response indicating the outcome of an MCP server delete operation.

Attributes:
    name: Name of the MCP server targeted for deletion.
    deleted: Whether the server was successfully deleted (True) or not found (False).
    response: Description of the result, e.g. "MCP server deleted successfully".


| Field | Type | Description |
|-------|------|-------------|
| deleted | boolean | Whether the deletion was successful. |
| name | string | MCP server name that was passed to delete. |


## MCPServerInfo


Information about a registered MCP server.

Attributes:
    name: Unique name of the MCP server.
    url: URL of the MCP server endpoint.
    provider_id: MCP provider identification.
    source: Whether the server was registered statically (config) or dynamically (api).


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name |
| url | string | MCP server URL |
| provider_id | string | MCP provider identification |
| source | string | How the server was registered: 'config' (static) or 'api' (dynamic) |


## MCPServerListResponse


Response listing all registered MCP servers.

Attributes:
    servers: All registered MCP servers (static and dynamic).


| Field | Type | Description |
|-------|------|-------------|
| servers | array | List of all registered MCP servers (static and dynamic) |


## MCPServerRegistrationResponse


Response for a successful MCP server registration.

Attributes:
    name: Registered MCP server name.
    url: Registered MCP server URL.
    provider_id: MCP provider identification.
    message: Status message.


| Field | Type | Description |
|-------|------|-------------|
| name | string | Registered MCP server name |
| url | string | Registered MCP server URL |
| provider_id | string | MCP provider identification |
| message | string | Status message |


## Message


Model representing a message in a conversation turn.

Attributes:
    content: The message content.
    type: The type of message.
    referenced_documents: Optional list of documents referenced in an assistant response.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The message content |
| type | string | The type of message |
| referenced_documents | array | List of documents referenced in the response (assistant messages only) |


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


| Field | Type | Description |
|-------|------|-------------|
| name | string | MCP server name that must be unique |
| provider_id | string | MCP provider identification |
| url | string | URL of the MCP server |
| authorization_headers | object | Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 3 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client-provided token in the header. To specify this use a string 'client' instead of the file path. 3. Usage of the oauth token in the header. To specify this use a string 'oauth' instead of the file path.  |
| headers | array | List of HTTP header names to automatically forward from the incoming request to this MCP server. Headers listed here are extracted from the original client request and included when calling the MCP server. This is useful when infrastructure components (e.g. API gateways) inject headers that MCP servers need, such as x-rh-identity in HCC. Header matching is case-insensitive. These headers are additive with authorization_headers and MCP-HEADERS. |
| require_approval |  | When to require human approval for tool invocations. 'always' requires approval for all tools, 'never' auto-approves, or use ApprovalFilter for granular control. |
| timeout | integer | Timeout in seconds for requests to the MCP server. If not specified, the default timeout from Llama Stack will be used. Note: This field is reserved for future use when Llama Stack adds timeout support. |


## ModelsResponse


Model representing a response to models request.


| Field | Type | Description |
|-------|------|-------------|
| models | array | List of models available |


## OkpConfiguration


OKP (Offline Knowledge Portal) provider configuration.

Controls provider-specific behaviour for the OKP vector store.
Only relevant when ``"okp"`` is listed in ``rag.inline`` or ``rag.tool``.


| Field | Type | Description |
|-------|------|-------------|
| rhokp_url | string | Base URL for the OKP server (http or https). Set to `${env.RH_SERVER_OKP}` in YAML to use the environment variable. When unset, the default from constants is used. |
| offline | boolean | When True, use parent_id for OKP chunk source URLs. When False, use reference_url for chunk source URLs. |
| chunk_filter_query | string | Additional OKP filter query applied to every OKP search request. Use Solr boolean syntax, e.g. 'product:ansible AND product:*openshift*'. |


## OpenAIResponseAnnotationCitation


URL citation annotation for referencing external web resources.

:param type: Annotation type identifier, always "url_citation"
:param end_index: End position of the citation span in the content
:param start_index: Start position of the citation span in the content
:param title: Title of the referenced web resource
:param url: URL of the referenced web resource


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| end_index | integer |  |
| start_index | integer |  |
| title | string |  |
| url | string |  |


## OpenAIResponseAnnotationContainerFileCitation



| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| container_id | string |  |
| end_index | integer |  |
| file_id | string |  |
| filename | string |  |
| start_index | integer |  |


## OpenAIResponseAnnotationFileCitation


File citation annotation for referencing specific files in response content.

:param type: Annotation type identifier, always "file_citation"
:param file_id: Unique identifier of the referenced file
:param filename: Name of the referenced file
:param index: Position index of the citation within the content


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_id | string |  |
| filename | string |  |
| index | integer |  |


## OpenAIResponseAnnotationFilePath



| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_id | string |  |
| index | integer |  |


## OpenAIResponseContentPartRefusal


Refusal content within a streamed response part.

:param type: Content part type identifier, always "refusal"
:param refusal: Refusal text supplied by the model


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| refusal | string |  |


## OpenAIResponseError


Error details for failed OpenAI response requests.

:param code: Error code identifying the type of failure
:param message: Human-readable error message describing the failure


| Field | Type | Description |
|-------|------|-------------|
| code | string |  |
| message | string |  |


## OpenAIResponseInputMessageContentFile


File content for input messages in OpenAI response format.

:param type: The type of the input item. Always `input_file`.
:param file_data: The data of the file to be sent to the model.
:param file_id: (Optional) The ID of the file to be sent to the model.
:param file_url: The URL of the file to be sent to the model.
:param filename: The name of the file to be sent to the model.


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| file_data | string |  |
| file_id | string |  |
| file_url | string |  |
| filename | string |  |


## OpenAIResponseInputMessageContentImage


Image content for input messages in OpenAI response format.

:param detail: Level of detail for image processing, can be "low", "high", or "auto"
:param type: Content type identifier, always "input_image"
:param file_id: (Optional) The ID of the file to be sent to the model.
:param image_url: (Optional) URL of the image content


| Field | Type | Description |
|-------|------|-------------|
| detail |  |  |
| type | string |  |
| file_id | string |  |
| image_url | string |  |


## OpenAIResponseInputMessageContentText


Text content for input messages in OpenAI response format.

:param text: The text content of the input message
:param type: Content type identifier, always "input_text"


| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |


## OpenAIResponseInputToolChoiceAllowedTools


Constrains the tools available to the model to a pre-defined set.

:param mode: Constrains the tools available to the model to a pre-defined set
:param tools: A list of tool definitions that the model should be allowed to call
:param type: Tool choice type identifier, always "allowed_tools"


| Field | Type | Description |
|-------|------|-------------|
| mode | string |  |
| tools | array |  |
| type | string |  |


## OpenAIResponseInputToolChoiceCustomTool


Forces the model to call a custom tool.

:param type: Tool choice type identifier, always "custom"
:param name: The name of the custom tool to call.


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| name | string |  |


## OpenAIResponseInputToolChoiceFileSearch


Indicates that the model should use file search to generate a response.

:param type: Tool choice type identifier, always "file_search"


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |


## OpenAIResponseInputToolChoiceFunctionTool


Forces the model to call a specific function.

:param name: The name of the function to call
:param type: Tool choice type identifier, always "function"


| Field | Type | Description |
|-------|------|-------------|
| name | string |  |
| type | string |  |


## OpenAIResponseInputToolChoiceMCPTool


Forces the model to call a specific tool on a remote MCP server

:param server_label: The label of the MCP server to use.
:param type: Tool choice type identifier, always "mcp"
:param name: (Optional) The name of the tool to call on the server.


| Field | Type | Description |
|-------|------|-------------|
| server_label | string |  |
| type | string |  |
| name | string |  |


## OpenAIResponseInputToolChoiceMode





## OpenAIResponseInputToolChoiceWebSearch


Indicates that the model should use web search to generate a response

:param type: Web search tool type variant to use


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |


## OpenAIResponseInputToolFileSearch


File search tool configuration for OpenAI response inputs.

:param type: Tool type identifier, always "file_search"
:param vector_store_ids: List of vector store identifiers to search within
:param filters: (Optional) Additional filters to apply to the search
:param max_num_results: (Optional) Maximum number of search results to return (1-50)
:param ranking_options: (Optional) Options for ranking and scoring search results


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| vector_store_ids | array |  |
| filters | object |  |
| max_num_results | integer |  |
| ranking_options |  |  |


## OpenAIResponseInputToolFunction


Function tool configuration for OpenAI response inputs.

:param type: Tool type identifier, always "function"
:param name: Name of the function that can be called
:param description: (Optional) Description of what the function does
:param parameters: (Optional) JSON schema defining the function's parameters
:param strict: (Optional) Whether to enforce strict parameter validation


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| name | string |  |
| description | string |  |
| parameters | object |  |
| strict | boolean |  |


## OpenAIResponseInputToolWebSearch


Web search tool configuration for OpenAI response inputs.

:param type: Web search tool type variant to use
:param search_context_size: (Optional) Size of search context, must be "low", "medium", or "high"


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| search_context_size | string |  |


## OpenAIResponseMCPApprovalRequest


A request for human approval of a tool invocation.


| Field | Type | Description |
|-------|------|-------------|
| arguments | string |  |
| id | string |  |
| name | string |  |
| server_label | string |  |
| type | string |  |


## OpenAIResponseMessage


Corresponds to the various Message types in the Responses API.
They are all under one type because the Responses API gives them all
the same "type" value, and there is no way to tell them apart in certain
scenarios.


| Field | Type | Description |
|-------|------|-------------|
| content |  |  |
| role |  |  |
| type | string |  |
| id | string |  |
| status | string |  |


## OpenAIResponseOutputMessageContentOutputText



| Field | Type | Description |
|-------|------|-------------|
| text | string |  |
| type | string |  |
| annotations | array |  |
| logprobs | array |  |


## OpenAIResponseOutputMessageFileSearchToolCall


File search tool call output message for OpenAI responses.

:param id: Unique identifier for this tool call
:param queries: List of search queries executed
:param status: Current status of the file search operation
:param type: Tool call type identifier, always "file_search_call"
:param results: (Optional) Search results returned by the file search operation


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| queries | array |  |
| status | string |  |
| type | string |  |
| results | array |  |


## OpenAIResponseOutputMessageFileSearchToolCallResults


Search results returned by the file search operation.

:param attributes: (Optional) Key-value attributes associated with the file
:param file_id: Unique identifier of the file containing the result
:param filename: Name of the file containing the result
:param score: Relevance score for this search result (between 0 and 1)
:param text: Text content of the search result


| Field | Type | Description |
|-------|------|-------------|
| attributes | object |  |
| file_id | string |  |
| filename | string |  |
| score | number |  |
| text | string |  |


## OpenAIResponseOutputMessageFunctionToolCall


Function tool call output message for OpenAI responses.

:param call_id: Unique identifier for the function call
:param name: Name of the function being called
:param arguments: JSON string containing the function arguments
:param type: Tool call type identifier, always "function_call"
:param id: (Optional) Additional identifier for the tool call
:param status: (Optional) Current status of the function call execution


| Field | Type | Description |
|-------|------|-------------|
| call_id | string |  |
| name | string |  |
| arguments | string |  |
| type | string |  |
| id | string |  |
| status | string |  |


## OpenAIResponseOutputMessageMCPCall


Model Context Protocol (MCP) call output message for OpenAI responses.

:param id: Unique identifier for this MCP call
:param type: Tool call type identifier, always "mcp_call"
:param arguments: JSON string containing the MCP call arguments
:param name: Name of the MCP method being called
:param server_label: Label identifying the MCP server handling the call
:param error: (Optional) Error message if the MCP call failed
:param output: (Optional) Output result from the successful MCP call


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| type | string |  |
| arguments | string |  |
| name | string |  |
| server_label | string |  |
| error | string |  |
| output | string |  |


## OpenAIResponseOutputMessageMCPListTools


MCP list tools output message containing available tools from an MCP server.

:param id: Unique identifier for this MCP list tools operation
:param type: Tool call type identifier, always "mcp_list_tools"
:param server_label: Label identifying the MCP server providing the tools
:param tools: List of available tools provided by the MCP server


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| type | string |  |
| server_label | string |  |
| tools | array |  |


## OpenAIResponseOutputMessageWebSearchToolCall


Web search tool call output message for OpenAI responses.

:param id: Unique identifier for this tool call
:param status: Current status of the web search operation
:param type: Tool call type identifier, always "web_search_call"


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| status | string |  |
| type | string |  |


## OpenAIResponsePrompt


OpenAI compatible Prompt object that is used in OpenAI responses.

:param id: Unique identifier of the prompt template
:param variables: Dictionary of variable names to OpenAIResponseInputMessageContent structure for template substitution. The substitution values can either be strings, or other Response input types
like images or files.
:param version: Version number of the prompt to use (defaults to latest if not specified)


| Field | Type | Description |
|-------|------|-------------|
| id | string |  |
| variables | object |  |
| version | string |  |


## OpenAIResponseReasoning


Configuration for reasoning effort in OpenAI responses.

Controls how much reasoning the model performs before generating a response.

:param effort: The effort level for reasoning. "low" favors speed and economical token usage,
               "high" favors more complete reasoning, "medium" is a balance between the two.


| Field | Type | Description |
|-------|------|-------------|
| effort | string |  |


## OpenAIResponseText


Text response configuration for OpenAI responses.

:param format: (Optional) Text format configuration specifying output format requirements


| Field | Type | Description |
|-------|------|-------------|
| format |  |  |


## OpenAIResponseTextFormat


Configuration for Responses API text format.

:param type: Must be "text", "json_schema", or "json_object" to identify the format type
:param name: The name of the response format. Only used for json_schema.
:param schema: The JSON schema the response should conform to. In a Python SDK, this is often a `pydantic` model. Only used for json_schema.
:param description: (Optional) A description of the response format. Only used for json_schema.
:param strict: (Optional) Whether to strictly enforce the JSON schema. If true, the response must match the schema exactly. Only used for json_schema.


| Field | Type | Description |
|-------|------|-------------|
| type |  |  |
| name | string |  |
| schema | object |  |
| description | string |  |
| strict | boolean |  |


## OpenAIResponseToolMCP


Model Context Protocol (MCP) tool configuration for OpenAI response object.

:param type: Tool type identifier, always "mcp"
:param server_label: Label to identify this MCP server
:param allowed_tools: (Optional) Restriction on which tools can be used from this server


| Field | Type | Description |
|-------|------|-------------|
| type | string |  |
| server_label | string |  |
| allowed_tools |  |  |


## OpenAIResponseUsage


Usage information for OpenAI response.

:param input_tokens: Number of tokens in the input
:param output_tokens: Number of tokens in the output
:param total_tokens: Total tokens used (input + output)
:param input_tokens_details: Detailed breakdown of input token usage
:param output_tokens_details: Detailed breakdown of output token usage


| Field | Type | Description |
|-------|------|-------------|
| input_tokens | integer |  |
| output_tokens | integer |  |
| total_tokens | integer |  |
| input_tokens_details |  |  |
| output_tokens_details |  |  |


## OpenAIResponseUsageInputTokensDetails


Token details for input tokens in OpenAI response usage.

:param cached_tokens: Number of tokens retrieved from cache


| Field | Type | Description |
|-------|------|-------------|
| cached_tokens | integer |  |


## OpenAIResponseUsageOutputTokensDetails


Token details for output tokens in OpenAI response usage.

:param reasoning_tokens: Number of tokens used for reasoning (o1/o3 models)


| Field | Type | Description |
|-------|------|-------------|
| reasoning_tokens | integer |  |


## OpenAITokenLogProb


The log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes | array | The bytes for the token. |
| logprob | number | The log probability of the token. |
| top_logprobs | array | The top log probabilities for the token. |


## OpenAITopLogProb


The top log probability for a token from an OpenAI-compatible chat completion response.


| Field | Type | Description |
|-------|------|-------------|
| token | string | The token. |
| bytes | array | The bytes for the token. |
| logprob | number | The log probability of the token. |


## PostgreSQLDatabaseConfiguration


PostgreSQL database configuration.

PostgreSQL database is used by Lightspeed Core Stack service for storing
information about conversation IDs. It can also be leveraged to store
conversation history and information about quota usage.

Useful resources:

- [Psycopg: connection classes](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [PostgreSQL connection strings](https://www.connectionstrings.com/postgresql/)
- [How to Use PostgreSQL in Python](https://www.freecodecamp.org/news/postgresql-in-python/)


| Field | Type | Description |
|-------|------|-------------|
| host | string | Database server host or socket directory |
| port | integer | Database server port |
| db | string | Database name to connect to |
| user | string | Database user name used to authenticate |
| password | string | Password used to authenticate |
| namespace | string | Database namespace |
| ssl_mode | string | SSL mode |
| gss_encmode | string | This option determines whether or with what priority a secure GSS TCP/IP connection will be negotiated with the server. |
| ca_cert_path | string | Path to CA certificate |


## PromptDeleteResponse


Result of deleting a stored prompt (always HTTP 200, like conversations v2).

Attributes:
    prompt_id: Prompt identifier that was passed to delete.
    deleted: Whether the prompt was deleted successfully
    response: Human readable response


| Field | Type | Description |
|-------|------|-------------|
| deleted | boolean | Whether the deletion was successful. |
| prompt_id | string | Prompt identifier that was passed to delete. |


## PromptResourceResponse


A stored prompt template as returned by Llama Stack.

Attributes:
    prompt_id: Prompt identifier from Llama Stack.
    version: Version number for this prompt.
    is_default: Whether this version is the default.
    prompt: Prompt text with placeholders.
    variables: Variable names used in the template.


| Field | Type | Description |
|-------|------|-------------|
| prompt_id | string | Prompt identifier from Llama Stack |
| version | integer | Version number for this prompt |
| is_default | boolean | Whether this version is the default |
| prompt | string | Prompt text with placeholders |
| variables | array | Variable names used in the template |


## PromptsListResponse


List of stored prompt templates returned by Llama Stack.

Attributes:
    data: Prompt entries as returned by the Llama Stack list API.


| Field | Type | Description |
|-------|------|-------------|
| data | array | Prompt entries (as returned by Llama Stack list) |


## ProviderHealthStatus


Model representing the health status of a provider.

Attributes:
    provider_id: The ID of the provider.
    status: The health status ('ok', 'unhealthy', 'not_implemented').
    message: Optional message about the health status.


| Field | Type | Description |
|-------|------|-------------|
| provider_id | string | The ID of the provider |
| status | string | The health status |
| message | string | Optional message about the health status |


## ProviderResponse


Model representing a response to get specific provider request.


| Field | Type | Description |
|-------|------|-------------|
| api | string | The API this provider implements |
| config | object | Provider configuration parameters |
| health | object | Current health status of the provider |
| provider_id | string | Unique provider identifier |
| provider_type | string | Provider implementation type |


## ProvidersListResponse


Model representing a response to providers request.


| Field | Type | Description |
|-------|------|-------------|
| providers | object | List of available API types and their corresponding providers |


## QueryResponse


Model representing LLM response to a query.

Attributes:
    conversation_id: The optional conversation ID (UUID).
    response: The response.
    rag_chunks: Deprecated. List of RAG chunks used to generate the response.
        This information is now available in tool_results under file_search_call type.
    referenced_documents: The URLs and titles for the documents used to generate the response.
    tool_calls: List of tool calls made during response generation.
    tool_results: List of tool results.
    truncated: Whether conversation history was truncated.
    input_tokens: Number of tokens sent to LLM.
    output_tokens: Number of tokens received from LLM.
    available_quotas: Quota available as measured by all configured quota limiters.


| Field | Type | Description |
|-------|------|-------------|
| conversation_id | string | The optional conversation ID (UUID) |
| response | string | Response from LLM |
| rag_chunks | array | Deprecated: List of RAG chunks used to generate the response. |
| referenced_documents | array | List of documents referenced in generating the response |
| truncated | boolean | Deprecated: whether conversation history was truncated |
| input_tokens | integer | Number of tokens sent to LLM |
| output_tokens | integer | Number of tokens received from LLM |
| available_quotas | object | Quota available as measured by all configured quota limiters |
| tool_calls | array | List of tool calls made during response generation |
| tool_results | array | List of tool results |


## QuotaHandlersConfiguration


Quota limiter configuration.

It is possible to limit quota usage per user or per service or services
(that typically run in one cluster). Each limit is configured as a separate
_quota limiter_. It can be of type `user_limiter` or `cluster_limiter`
(which is name that makes sense in OpenShift deployment).


| Field | Type | Description |
|-------|------|-------------|
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |
| limiters | array | Quota limiters configuration |
| scheduler |  | Quota scheduler configuration |
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


| Field | Type | Description |
|-------|------|-------------|
| type | string | Quota limiter type, either user_limiter or cluster_limiter |
| name | string | Human readable quota limiter name |
| initial_quota | integer | Quota set at beginning of the period |
| quota_increase | integer | Delta value used to increase quota when period is reached |
| period | string | Period specified in human readable form |


## QuotaSchedulerConfiguration


Quota scheduler configuration.


| Field | Type | Description |
|-------|------|-------------|
| period | integer | Quota scheduler period specified in seconds |
| database_reconnection_count | integer | Database reconnection count on startup. When database for quota is not available on startup, the service tries to reconnect N times with specified delay. |
| database_reconnection_delay | integer | Database reconnection delay specified in seconds. When database for quota is not available on startup, the service tries to reconnect N times with specified delay. |


## RAGChunk


Model representing a RAG chunk used in the response.


| Field | Type | Description |
|-------|------|-------------|
| content | string | The content of the chunk |
| source | string | Index name identifying the knowledge source from configuration |
| score | number | Relevance score |
| attributes | object | Document metadata from the RAG provider (e.g., url, title, author) |


## RAGInfoResponse


Model representing a response with information about RAG DB.


| Field | Type | Description |
|-------|------|-------------|
| id | string | Vector DB unique ID |
| name | string | Human readable vector DB name |
| created_at | integer | When the vector store was created, represented as Unix time |
| last_active_at | integer | When the vector store was last active, represented as Unix time |
| usage_bytes | integer | Storage byte(s) used by this vector DB |
| expires_at | integer | When the vector store expires, represented as Unix time |
| object | string | Object type |
| status | string | Vector DB status |


## RAGListResponse


Model representing a response to list RAGs request.


| Field | Type | Description |
|-------|------|-------------|
| rags | array | List of RAG identifiers |


## RHIdentityConfiguration


Red Hat Identity authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| required_entitlements | array | List of all required entitlements. |
| max_header_size | integer | Maximum allowed size in bytes for the base64-encoded x-rh-identity header. Headers exceeding this size are rejected before decoding. |


## RagConfiguration


RAG strategy configuration.

Controls which RAG sources are used for inline and tool-based retrieval.

Each strategy lists RAG IDs to include. The special ID ``"okp"`` defined in constants,
activates the OKP provider; all other IDs refer to entries in ``byok_rag``.

Both ``inline`` and ``tool`` default to ``[]`` (disabled).
Each must be explicitly configured to activate its respective RAG strategy.


| Field | Type | Description |
|-------|------|-------------|
| inline | array | RAG IDs whose sources are injected as context before the LLM call. Use 'okp' to enable OKP inline RAG. Empty by default (no inline RAG). |
| tool | array | RAG IDs made available to the LLM as a file_search tool. Use 'okp' to include the OKP vector store. When omitted, tool RAG is disabled. |


## ReadinessResponse


Model representing response to a readiness request.

Attributes:
    ready: If service is ready.
    reason: The reason for the readiness.
    providers: List of unhealthy providers in case of readiness failure.


| Field | Type | Description |
|-------|------|-------------|
| ready | boolean | Flag indicating if service is ready |
| reason | string | The reason for the readiness |
| providers | array | List of unhealthy providers in case of readiness failure. |


## ReferencedDocument


Model representing a document referenced in generating a response.

Attributes:
    doc_url: Url to the referenced doc.
    doc_title: Title of the referenced doc.
    document_id: Document ID for preserving identity during deduplication.


| Field | Type | Description |
|-------|------|-------------|
| doc_url | string | URL of the referenced document |
| doc_title | string | Title of the referenced document |
| source | string | Index name identifying the knowledge source from configuration |
| document_id | string | Document ID for preserving identity during deduplication |


## RerankerConfiguration


Reranker configuration for RAG chunk reranking.


| Field | Type | Description |
|-------|------|-------------|
| enabled | boolean | When True, reranking applied to RAG chunks. When False, reranking is disabled and original scoring used. |
| model | string | Cross-encoder model name for reranking RAG chunks. Defaults to 'cross-encoder/ms-marco-MiniLM-L6-v2' from sentence-transformers. |


## ResponsesResponse


Model representing a response from the Responses API following LCORE specification.

Attributes:
    created_at: Unix timestamp when the response was created.
    completed_at: Unix timestamp when the response was completed, if applicable.
    error: Error details if the response failed or was blocked.
    id: Unique identifier for this response.
    model: Model identifier in "provider/model" format used for generation.
    object: Object type identifier, always "response".
    output: List of structured output items containing messages, tool calls, and
        other content. This is the primary response content.
    parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
    previous_response_id: Identifier of the previous response in a multi-turn
        conversation.
    prompt: The input prompt object that was sent to the model.
    status: Current status of the response (e.g., "completed", "blocked",
        "in_progress").
    temperature: Temperature parameter used for generation (controls randomness).
    text: Text response configuration object used for OpenAI responses.
    top_p: Top-p sampling parameter used for generation.
    tools: List of tools available to the model during generation.
    tool_choice: Tool selection strategy used (e.g., "auto", "required", "none").
    truncation: Strategy used for handling content that exceeds context limits.
    usage: Token usage statistics including input_tokens, output_tokens, and
        total_tokens.
    instructions: System instructions or guidelines provided to the model.
    max_tool_calls: Maximum number of tool calls allowed in a single response.
    reasoning: Reasoning configuration (effort level) used for the response.
    max_output_tokens: Upper bound for tokens generated in the response.
    safety_identifier: Safety/guardrail identifier applied to the request.
    metadata: Additional metadata dictionary with custom key-value pairs.
    store: Whether the response was stored.
    conversation: Conversation ID linking this response to a conversation thread
        (LCORE-specific).
    available_quotas: Remaining token quotas for the user (LCORE-specific).
    output_text: Aggregated text output from all output_text items in the
        output array.


| Field | Type | Description |
|-------|------|-------------|
| created_at | integer |  |
| completed_at | integer |  |
| error |  |  |
| id | string |  |
| model | string |  |
| object | string |  |
| output | array |  |
| parallel_tool_calls | boolean |  |
| previous_response_id | string |  |
| prompt |  |  |
| status | string |  |
| temperature | number |  |
| text |  |  |
| top_p | number |  |
| tools | array |  |
| tool_choice |  |  |
| truncation | string |  |
| usage |  |  |
| instructions | string |  |
| max_tool_calls | integer |  |
| reasoning |  |  |
| max_output_tokens | integer |  |
| safety_identifier | string |  |
| metadata | object |  |
| store | boolean |  |
| conversation | string |  |
| available_quotas | object |  |
| output_text | string |  |


## RlsapiV1Configuration


Configuration for the rlsapi v1 /infer endpoint.

Settings specific to the RHEL Lightspeed Command Line Assistant (CLA)
stateless inference endpoint. Kept separate from shared configuration
sections so that CLA-specific options do not affect other endpoints.


| Field | Type | Description |
|-------|------|-------------|
| allow_verbose_infer | boolean | Allow /v1/infer to return extended metadata (tool_calls, rag_chunks, token_usage) when the client sends "include_metadata": true. Should NOT be enabled in production. If production use is needed, consider RBAC-based access control via an Action.RLSAPI_V1_INFER authorization rule. |
| quota_subject | string | Identity field used as the quota subject for /v1/infer. When set, token quota enforcement is enabled for this endpoint. Requires quota_handlers to be configured. "org_id" and "system_id" require rh-identity authentication; falls back to user_id when rh-identity data is unavailable. |


## RlsapiV1InferData


Response data for rlsapi v1 /infer endpoint.

Attributes:
    text: The generated response text.
    request_id: Unique identifier for the request.
    tool_calls: MCP tool calls made during inference (verbose mode only).
    tool_results: Results from MCP tool calls (verbose mode only).
    rag_chunks: RAG chunks retrieved from documentation (verbose mode only).
    referenced_documents: Source documents referenced (verbose mode only).
    input_tokens: Number of input tokens consumed (verbose mode only).
    output_tokens: Number of output tokens generated (verbose mode only).


| Field | Type | Description |
|-------|------|-------------|
| text | string | Generated response text |
| request_id | string | Unique request identifier |
| tool_calls | array | Tool calls made during inference (requires include_metadata=true) |
| tool_results | array | Results from tool calls (requires include_metadata=true) |
| rag_chunks | array | Retrieved RAG documentation chunks (requires include_metadata=true) |
| referenced_documents | array | Source documents referenced in answer (requires include_metadata=true) |
| input_tokens | integer | Number of input tokens consumed (requires include_metadata=true) |
| output_tokens | integer | Number of output tokens generated (requires include_metadata=true) |


## RlsapiV1InferResponse


RHEL Lightspeed rlsapi v1 /infer response.

Attributes:
    data: Response data containing text and request_id.


| Field | Type | Description |
|-------|------|-------------|
| data |  | Response data containing text and request_id |


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field | Type | Description |
|-------|------|-------------|
| db_path | string | Path to file where SQLite database is stored |


## SearchRankingOptions


Options for ranking and filtering search results.

This class configures how search results are ranked and filtered. You can use algorithm-based
rerankers (weighted, RRF) or neural rerankers. Defaults from VectorStoresConfig are
used when parameters are not provided.

Examples:
    # Weighted ranker with custom alpha
    SearchRankingOptions(ranker="weighted", alpha=0.7)

    # RRF ranker with custom impact factor
    SearchRankingOptions(ranker="rrf", impact_factor=50.0)

    # Use config defaults (just specify ranker type)
    SearchRankingOptions(ranker="weighted")  # Uses alpha from VectorStoresConfig

    # Score threshold filtering
    SearchRankingOptions(ranker="weighted", score_threshold=0.5)

:param ranker: (Optional) Name of the ranking algorithm to use. Supported values:
    - "weighted": Weighted combination of vector and keyword scores
    - "rrf": Reciprocal Rank Fusion algorithm
    - "neural": Neural reranking model (requires model parameter, Part II)
    Note: For OpenAI API compatibility, any string value is accepted, but only the above values are supported.
:param score_threshold: (Optional) Minimum relevance score threshold for results. Default: 0.0
:param alpha: (Optional) Weight factor for weighted ranker (0-1).
    - 0.0 = keyword only
    - 0.5 = equal weight (default)
    - 1.0 = vector only
    Only used when ranker="weighted" and weights is not provided.
    Falls back to VectorStoresConfig.chunk_retrieval_params.weighted_search_alpha if not provided.
:param impact_factor: (Optional) Impact factor (k) for RRF algorithm.
    Lower values emphasize higher-ranked results. Default: 60.0 (optimal from research).
    Only used when ranker="rrf".
    Falls back to VectorStoresConfig.chunk_retrieval_params.rrf_impact_factor if not provided.
:param weights: (Optional) Dictionary of weights for combining different signal types.
    Keys can be "vector", "keyword", "neural". Values should sum to 1.0.
    Used when combining algorithm-based reranking with neural reranking (Part II).
    Example: {"vector": 0.3, "keyword": 0.3, "neural": 0.4}
:param model: (Optional) Model identifier for neural reranker (e.g., "vllm/Qwen3-Reranker-0.6B").
    Required when ranker="neural" or when weights contains "neural" (Part II).


| Field | Type | Description |
|-------|------|-------------|
| ranker | string |  |
| score_threshold | number |  |
| alpha | number | Weight factor for weighted ranker |
| impact_factor | number | Impact factor for RRF algorithm |
| weights | object | Weights for combining vector, keyword, and neural scores. Keys: 'vector', 'keyword', 'neural' |
| model | string | Model identifier for neural reranker |


## ServiceConfiguration


Service configuration.

Lightspeed Core Stack is a REST API service that accepts requests on a
specified hostname and port. It is also possible to enable authentication
and specify the number of Uvicorn workers. When more workers are specified,
the service can handle requests concurrently.


| Field | Type | Description |
|-------|------|-------------|
| host | string | Service hostname |
| port | integer | Service port |
| base_url | string | Externally reachable base URL for the service; needed for A2A support. |
| auth_enabled | boolean | Enables the authentication subsystem |
| workers | integer | Number of Uvicorn worker processes to start |
| color_log | boolean | Enables colorized logging |
| access_log | boolean | Enables logging of all access information |
| tls_config |  | Transport Layer Security configuration for HTTPS support |
| root_path | string | ASGI root path for serving behind a reverse proxy on a subpath |
| cors |  | Cross-Origin Resource Sharing configuration for cross-domain requests |


## ShieldsResponse


Model representing a response to shields request.


| Field | Type | Description |
|-------|------|-------------|
| shields | array | List of shields available |


## SkillsConfiguration


Agent skills configuration.

Specifies paths to skill directories. Skill metadata (name, description)
is read from SKILL.md frontmatter at startup.

Each path can point to either:
- A directory containing a SKILL.md file (single skill)
- A directory containing subdirectories with SKILL.md files (multiple skills)

Paths are validated at startup to ensure they exist and contain valid SKILL.md files.


| Field | Type | Description |
|-------|------|-------------|
| paths | array | Paths to skill directories or directories containing skill subdirectories. |


## SplunkConfiguration


Splunk HEC (HTTP Event Collector) configuration.

Splunk HEC allows sending events directly to Splunk over HTTP/HTTPS.
This configuration is used to send telemetry events for inference
requests to the corporate Splunk deployment.

Useful resources:

  - [Splunk HEC Docs](https://docs.splunk.com/Documentation/SplunkCloud)
  - [About HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data)


| Field | Type | Description |
|-------|------|-------------|
| enabled | boolean | Enable or disable Splunk HEC integration. |
| url | string | Splunk HEC endpoint URL. |
| token_path | string | Path to file containing the Splunk HEC authentication token. |
| index | string | Target Splunk index for events. |
| source | string | Event source identifier. |
| timeout | integer | HTTP timeout in seconds for HEC requests. |
| verify_ssl | boolean | Whether to verify SSL certificates for HEC endpoint. |


## StatusResponse


Model representing a response to a status request.

Attributes:
    functionality: The functionality of the service.
    status: The status of the service.


| Field | Type | Description |
|-------|------|-------------|
| functionality | string | The functionality of the service |
| status | object | The status of the service |


## StreamingInterruptResponse


Model representing a response to a streaming interrupt request.

Attributes:
    request_id: The streaming request ID targeted by the interrupt call.
    interrupted: Whether an in-progress stream was interrupted.
    message: Human-readable interruption status message.


| Field | Type | Description |
|-------|------|-------------|
| request_id | string | The streaming request ID targeted by the interrupt call |
| interrupted | boolean | Whether an in-progress stream was interrupted |
| message | string | Human-readable interruption status message |


## StreamingQueryResponse


Documentation-only model for streaming query responses using Server-Sent Events (SSE).




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


| Field | Type | Description |
|-------|------|-------------|
| tls_certificate_path | string | SSL/TLS certificate file path for HTTPS support. |
| tls_key_path | string | SSL/TLS private key file path for HTTPS support. |
| tls_key_password | string | Path to file containing the password to decrypt the SSL/TLS private key. |


## ToolCallSummary


Model representing a tool call made during response generation (for tool_calls list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call |
| name | string | Name of the tool called |
| args | object | Arguments passed to the tool |
| type | string | Type indicator for tool call |


## ToolResultSummary


Model representing a result from a tool call (for tool_results list).


| Field | Type | Description |
|-------|------|-------------|
| id | string | ID of the tool call/result, matches the corresponding tool call 'id' |
| status | string | Status of the tool execution (e.g., 'success') |
| content | string | Content/result returned from the tool |
| type | string | Type indicator for tool result |
| round | integer | Round number or step of tool execution |


## ToolsResponse


Model representing a response to tools request.


| Field | Type | Description |
|-------|------|-------------|
| tools | array | List of tools available from all configured MCP servers and built-in toolgroups |


## TrustedProxyConfiguration


Configuration for trusted-proxy auth module.


| Field | Type | Description |
|-------|------|-------------|
| user_header | string | HTTP header containing the forwarded user identity. |
| allowed_service_accounts | array | Optional allowlist of Kubernetes ServiceAccount identities permitted to act as trusted proxies. When set to null/omitted, any ServiceAccount with a valid token is accepted. When set to a non-empty list, only the listed ServiceAccounts are allowed. An empty list behaves the same as null (no restriction). |


## TrustedProxyServiceAccount


A Kubernetes ServiceAccount identity for trusted-proxy allowlist.


| Field | Type | Description |
|-------|------|-------------|
| namespace | string | Kubernetes namespace of the ServiceAccount. |
| name | string | Name of the Kubernetes ServiceAccount. |


## UserDataCollection


User data collection configuration.


| Field | Type | Description |
|-------|------|-------------|
| feedback_enabled | boolean | When set to true the user feedback is stored and later sent for analysis. |
| feedback_storage | string | Path to directory where feedback will be saved for further processing. |
| transcripts_enabled | boolean | When set to true the conversation history is stored and later sent for analysis. |
| transcripts_storage | string | Path to directory where conversation history will be saved for further processing. |


## VectorStoreDeleteResponse


Result of deleting a vector store (always HTTP 200).


| Field | Type | Description |
|-------|------|-------------|
| deleted | boolean | Whether the deletion was successful. |
| vector_store_id | string | Vector store identifier that was passed to delete. |


## VectorStoreFileDeleteResponse


Result of deleting a file from a vector store (always HTTP 200).


| Field | Type | Description |
|-------|------|-------------|
| deleted | boolean | Whether the deletion was successful. |
| file_id | string | File identifier that was passed to delete. |


## VectorStoreFileResponse


Response model containing a vector store file object.

Attributes:
    id: Vector store file ID.
    vector_store_id: ID of the vector store.
    status: File processing status.
    attributes: Optional metadata key-value pairs.
    last_error: Optional error message if processing failed.
    object: Object type (always "vector_store.file").


| Field | Type | Description |
|-------|------|-------------|
| id | string | Vector store file ID |
| vector_store_id | string | ID of the vector store |
| status | string | File processing status |
| attributes | object | Set of up to 16 key-value pairs for storing additional information. Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers. |
| last_error | string | Error message if processing failed |
| object | string | Object type |


## VectorStoreFilesListResponse


Response model containing a list of vector store files.

Attributes:
    data: List of vector store file objects.
    object: Object type (always "list").


| Field | Type | Description |
|-------|------|-------------|
| data | array | List of vector store files |
| object | string | Object type |


## VectorStoreResponse


Response model containing a single vector store.

Attributes:
    id: Vector store ID.
    name: Vector store name.
    created_at: Unix timestamp when created.
    last_active_at: Unix timestamp of last activity.
    expires_at: Optional Unix timestamp when it expires.
    status: Vector store status.
    usage_bytes: Storage usage in bytes.
    metadata: Optional metadata dictionary for storing session information.


| Field | Type | Description |
|-------|------|-------------|
| id | string | Vector store ID |
| name | string | Vector store name |
| created_at | integer | Unix timestamp when created |
| last_active_at | integer | Unix timestamp of last activity |
| expires_at | integer | Unix timestamp when it expires |
| status | string | Vector store status |
| usage_bytes | integer | Storage usage in bytes |
| metadata | object | Metadata dictionary for storing session information |


## VectorStoresListResponse


Response model containing a list of vector stores.

Attributes:
    data: List of vector store objects.
    object: Object type (always "list").


| Field | Type | Description |
|-------|------|-------------|
| data | array | List of vector stores |
| object | string | Object type |
