"""Constants used in business logic."""

from typing import Final

# Use Final[type] as type hint for all constants to ensure that type checkers (Mypy etc.)
# will be able to detect assignements to such constants.

# Minimal and maximal supported Llama Stack version
MINIMAL_SUPPORTED_LLAMA_STACK_VERSION: Final[str] = "0.2.17"
MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION: Final[str] = "0.6.0"

UNABLE_TO_PROCESS_RESPONSE: Final[str] = "Unable to process this request"

# Response stored in the conversation when the user interrupts a streaming request
INTERRUPTED_RESPONSE_MESSAGE: Final[str] = "You interrupted this request."

# Max seconds to wait for topic summary in background task after interrupt persist.
TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS: Final[float] = 30.0

# Supported attachment types
ATTACHMENT_TYPES: Final[frozenset] = frozenset(
    {
        "alert",
        "api object",
        "configuration",
        "error message",
        "event",
        "log",
        "stack trace",
    }
)

# Supported attachment content types
ATTACHMENT_CONTENT_TYPES: Final[frozenset] = frozenset(
    {"text/plain", "application/json", "application/yaml", "application/xml"}
)

# Default system prompt used only when no other system prompt is specified in
# configuration file nor in the query request
DEFAULT_SYSTEM_PROMPT: Final[str] = "You are a helpful assistant"

# Default topic summary system prompt used only when no other topic summary system
# prompt is specified in configuration file
DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT: Final[str] = """
Instructions:
- You are a topic summarizer
- Your job is to extract precise topic summary from user input
- Return only the final topic summary, no other text or explanation.

For Input Analysis:
- Scan entire user message
- Identify core subject matter
- Distill essence into concise descriptor
- Prioritize key concepts
- Eliminate extraneous details

For Output Constraints:
- Maximum 5 words
- Capitalize only significant words (e.g., nouns, verbs, adjectives, adverbs).
- Do **NOT** use all uppercase - capitalize only the first letter of significant words
- Exclude articles and prepositions (e.g., "a," "the," "of," "on," "in")
- Exclude all punctuation and interpunction marks (e.g., . , : ; ! ? | "")
- Retain original abbreviations. Do not expand an abbreviation if its specific meaning in the
  context is unknown or ambiguous.
- Neutral objective language
- Do **NOT** provide explanations, reasoning, or "processing steps".
- Do **NOT** provide multiple options (e.g., do not use "or").
- Do **NOT** use introductory text like "The topic is...".


Examples:
- "AI Capabilities Summary" (Correct)
- "Machine Learning Applications" (Correct)
- "AI CAPABILITIES SUMMARY" (Incorrect—should not be fully uppercase)

Processing Steps
1. Analyze semantic structure
2. Identify primary topic
3. Remove contextual noise
4. Condense to essential meaning
5. Generate topic label


Example Input:
How to implement horizontal pod autoscaling in Kubernetes clusters
Example Output:
Kubernetes Horizontal Pod Autoscaling

Example Input:
Comparing OpenShift deployment strategies for microservices architecture
Example Output:
OpenShift Microservices Deployment Strategies

Example Input:
Troubleshooting persistent volume claims in Kubernetes environments
Example Output:
Kubernetes Persistent Volume Troubleshooting

Example Input:
I need a summary about the purpose of RHDH.
Example Output:
RHDH Purpose Summary

Input:
{query}
Output:
"""

# Authentication constants
DEFAULT_VIRTUAL_PATH: Final[str] = "/ls-access"
DEFAULT_USER_NAME: Final[str] = "lightspeed-user"
DEFAULT_SKIP_USER_ID_CHECK: Final[bool] = True
DEFAULT_USER_UID: Final[str] = "00000000-0000-0000-0000-000"
# default value for token when no token is provided
NO_USER_TOKEN: Final[str] = ""
AUTH_MOD_K8S: Final[str] = "k8s"
AUTH_MOD_NOOP: Final[str] = "noop"
AUTH_MOD_NOOP_WITH_TOKEN: Final[str] = "noop-with-token"
AUTH_MOD_APIKEY_TOKEN: Final[str] = "api-key-token"
AUTH_MOD_JWK_TOKEN: Final[str] = "jwk-token"
AUTH_MOD_RH_IDENTITY: Final[str] = "rh-identity"
# Supported authentication modules
SUPPORTED_AUTHENTICATION_MODULES: Final[frozenset] = frozenset(
    {
        AUTH_MOD_K8S,
        AUTH_MOD_NOOP,
        AUTH_MOD_NOOP_WITH_TOKEN,
        AUTH_MOD_JWK_TOKEN,
        AUTH_MOD_APIKEY_TOKEN,
        AUTH_MOD_RH_IDENTITY,
    }
)
DEFAULT_AUTHENTICATION_MODULE: Final[str] = AUTH_MOD_NOOP
# Maximum allowed size for base64-encoded x-rh-identity header (bytes)
DEFAULT_RH_IDENTITY_MAX_HEADER_SIZE: Final[int] = 8192

# Maximum allowed file upload size (bytes) - 100MB default
# Protects against DoS attacks via large file uploads
DEFAULT_MAX_FILE_UPLOAD_SIZE: Final[int] = 100 * 1024 * 1024  # 100 MB
DEFAULT_JWT_UID_CLAIM: Final[str] = "user_id"
DEFAULT_JWT_USER_NAME_CLAIM: Final[str] = "username"

# MCP authorization header special values
MCP_AUTH_KUBERNETES: Final[str] = "kubernetes"
MCP_AUTH_CLIENT: Final[str] = "client"
MCP_AUTH_OAUTH: Final[str] = "oauth"

# Media type constants for streaming responses
MEDIA_TYPE_JSON: Final[str] = "application/json"
MEDIA_TYPE_TEXT: Final[str] = "text/plain"
MEDIA_TYPE_EVENT_STREAM: Final[str] = "text/event-stream"

# Streaming event type constants
LLM_TOKEN_EVENT: Final[str] = "token"
LLM_TOOL_CALL_EVENT: Final[str] = "tool_call"
LLM_TOOL_RESULT_EVENT: Final[str] = "tool_result"
LLM_TURN_COMPLETE_EVENT: Final[str] = "turn_complete"

# PostgreSQL connection constants
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLMODE
POSTGRES_DEFAULT_SSL_MODE: Final[str] = "prefer"
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-GSSENCMODE
POSTGRES_DEFAULT_GSS_ENCMODE: Final[str] = "prefer"

# cache constants
CACHE_TYPE_MEMORY: Final[str] = "memory"
CACHE_TYPE_SQLITE: Final[str] = "sqlite"
CACHE_TYPE_POSTGRES: Final[str] = "postgres"
CACHE_TYPE_NOOP: Final[str] = "noop"

# BYOK RAG
# Default RAG type for bring-your-own-knowledge RAG configurations, that type
# needs to be supported by Llama Stack
DEFAULT_RAG_TYPE: Final[str] = "inline::faiss"

# Default sentence transformer model for embedding generation, that type needs
# to be supported by Llama Stack and configured properly in providers and
# models sections
DEFAULT_EMBEDDING_MODEL: Final[str] = "sentence-transformers/all-mpnet-base-v2"

# Default embedding vector dimension for the sentence transformer model
DEFAULT_EMBEDDING_DIMENSION: Final[int] = 768

# quota limiters constants
USER_QUOTA_LIMITER: Final[str] = "user_limiter"
CLUSTER_QUOTA_LIMITER: Final[str] = "cluster_limiter"

# RAG as a tool constants
DEFAULT_RAG_TOOL: Final[str] = "file_search"
TOOL_RAG_MAX_CHUNKS: Final[int] = 10  # retrieved from RAG as a tool

# Inline RAG constants
BYOK_RAG_MAX_CHUNKS: Final[int] = 10  # retrieved from BYOK RAG
OKP_RAG_MAX_CHUNKS: Final[int] = 5  # retrieved from OKP RAG

# Solr OKP constants
SOLR_VECTOR_SEARCH_DEFAULT_K: Final[int] = 5
SOLR_VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD: Final[float] = 0.3
SOLR_VECTOR_SEARCH_DEFAULT_MODE: Final[str] = "hybrid"

# Internal Solr filter always applied to restrict results to chunk documents
SOLR_CHUNK_FILTER_QUERY: Final[str] = "is_chunk:true"

# SOLR OKP RAG - default base URL when okp.rhokp_url is unset in configuration
RH_SERVER_OKP_DEFAULT_URL: Final[str] = "http://localhost:8081"

SOLR_PROVIDER_ID: Final[str] = "okp_solr"

# Solr default configuration values (can be overridden via environment variables)
SOLR_DEFAULT_VECTOR_STORE_ID: Final[str] = "portal-rag"
SOLR_DEFAULT_VECTOR_FIELD: Final[str] = "chunk_vector"
SOLR_DEFAULT_CONTENT_FIELD: Final[str] = "chunk"
SOLR_DEFAULT_EMBEDDING_MODEL: Final[str] = (
    "sentence-transformers/ibm-granite/granite-embedding-30m-english"
)
SOLR_DEFAULT_EMBEDDING_DIMENSION: Final[int] = 384

# Default score multiplier for BYOK RAG vector stores
DEFAULT_SCORE_MULTIPLIER: Final[float] = 1.0

# Special RAG ID that activates the OKP provider when listed in rag.inline or rag.tool
OKP_RAG_ID: Final[str] = "okp"

# Logging configuration constants
# Environment variable name for configurable log level
LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR: Final[str] = "LIGHTSPEED_STACK_LOG_LEVEL"
# Default log level when environment variable is not set
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
# Default log format for plain-text logging in non-TTY environments
DEFAULT_LOG_FORMAT: Final[str] = (
    "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
)
# Environment variable to force StreamHandler instead of RichHandler
# Set to any non-empty value to disable RichHandler
LIGHTSPEED_STACK_DISABLE_RICH_HANDLER_ENV_VAR: Final[str] = (
    "LIGHTSPEED_STACK_DISABLE_RICH_HANDLER"
)

DEFAULT_VIOLATION_MESSAGE: Final[str] = (
    "I cannot process this request due to policy restrictions."
)

# Placeholder slug used in responses when the server substituted its own
# system prompt for the client's instructions.  Avoids leaking the actual
# server prompt back to the client.
SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER: Final[str] = "<server prompt applied>"
# Input size limits for API request validation
# Maximum character length for the question field in /v1/infer requests (32 KiB)
RLSAPI_V1_QUESTION_MAX_LENGTH: Final[int] = 32_768
# Maximum character length for the serialized /v1/responses request body (64 KiB)
RESPONSES_REQUEST_MAX_SIZE: Final[int] = 65_536

# Sentry configuration constants
# Environment variable name for the Sentry DSN (Data Source Name)
SENTRY_DSN_ENV_VAR: Final[str] = "SENTRY_DSN"
# Environment variable name for the Sentry environment tag
SENTRY_ENVIRONMENT_ENV_VAR: Final[str] = "SENTRY_ENVIRONMENT"
# Default Sentry environment when SENTRY_ENVIRONMENT is not set
SENTRY_DEFAULT_ENVIRONMENT: Final[str] = "development"
# Default trace sample rate (fraction of transactions to capture)
SENTRY_DEFAULT_TRACES_SAMPLE_RATE: Final[float] = 0.25
# Routes excluded from Sentry trace sampling (health checks, metrics, root).
# Note: health and metrics routers are mounted WITHOUT a /v1 prefix
# (see the setup_routers function in src/app/routers.py), so ASGI paths are
# /readiness, /liveness, /metrics.
SENTRY_EXCLUDED_ROUTES: Final[tuple[str, ...]] = (
    "/readiness",
    "/liveness",
    "/metrics",
    "/",
)
# Environment variable name for the Sentry CA certificate bundle path.
# Set this to a file path (e.g. /etc/pki/tls/certs/ca-bundle.crt) when
# connecting to a Sentry instance that uses a private or internal CA.
SENTRY_CA_CERTS_ENV_VAR: Final[str] = "SENTRY_CA_CERTS"
