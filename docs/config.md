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




## AuthenticationConfiguration


Authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| module | string |  |
| skip_tls_verification | boolean |  |
| skip_for_health_probes | boolean | Skip authorization for readiness and liveness probes |
| k8s_cluster_api | string |  |
| k8s_ca_cert_path | string |  |
| jwk_config |  |  |
| api_key_config |  |  |
| rh_identity_config |  |  |


## AuthorizationConfiguration


Authorization configuration.


| Field | Type | Description |
|-------|------|-------------|
| access_rules | array | Rules for role-based access control |


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
| rag_type | string | Type of RAG database. |
| embedding_model | string | Embedding model identification |
| embedding_dimension | integer | Dimensionality of embedding vectors. |
| vector_db_id | string | Vector database identification. |
| db_path | string | Path to RAG database. |


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
| byok_rag | array | BYOK RAG configuration. This configuration can be used to reconfigure Llama Stack through its run.yaml configuration file |
| a2a_state |  | Configuration for A2A protocol persistent state storage. |
| quota_handlers |  | Quota handlers configuration |
| azure_entra_id |  |  |
| splunk |  | Splunk HEC configuration for sending telemetry events. |
| deployment_environment | string | Deployment environment name (e.g., 'development', 'staging', 'production'). Used in telemetry events. |


## ConversationHistoryConfiguration


Conversation history configuration.


| Field | Type | Description |
|-------|------|-------------|
| type | string | Type of database where the conversation history is to be stored. |
| memory |  | In-memory cache configuration |
| sqlite |  | SQLite database configuration |
| postgres |  | PostgreSQL database configuration |


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
| authorization_headers | object | Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 2 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client provided token in the header. To specify this use a string 'client' instead of the file path. |
| timeout | integer | Timeout in seconds for requests to the MCP server. If not specified, the default timeout from Llama Stack will be used. Note: This field is reserved for future use when Llama Stack adds timeout support. |


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


## RHIdentityConfiguration


Red Hat Identity authentication configuration.


| Field | Type | Description |
|-------|------|-------------|
| required_entitlements | array | List of all required entitlements. |


## SQLiteDatabaseConfiguration


SQLite database configuration.


| Field | Type | Description |
|-------|------|-------------|
| db_path | string | Path to file where SQLite database is stored |


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


## UserDataCollection


User data collection configuration.


| Field | Type | Description |
|-------|------|-------------|
| feedback_enabled | boolean | When set to true the user feedback is stored and later sent for analysis. |
| feedback_storage | string | Path to directory where feedback will be saved for further processing. |
| transcripts_enabled | boolean | When set to true the conversation history is stored and later sent for analysis. |
| transcripts_storage | string | Path to directory where conversation history will be saved for further processing. |
