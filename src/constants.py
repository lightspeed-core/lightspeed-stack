"""Constants used in business logic."""

# Minimal and maximal supported Llama Stack version
MINIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.2.17"
MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.4.3"

UNABLE_TO_PROCESS_RESPONSE = "Unable to process this request"

# Supported attachment types
ATTACHMENT_TYPES = frozenset(
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
ATTACHMENT_CONTENT_TYPES = frozenset(
    {"text/plain", "application/json", "application/yaml", "application/xml"}
)

# Default system prompt used only when no other system prompt is specified in
# configuration file nor in the query request
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant"

# Default topic summary system prompt used only when no other topic summary system
# prompt is specified in configuration file
DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT = """
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
- Retain original abbreviations. Do not expand an abbreviation if its specific meaning in the context is unknown or ambiguous.
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
DEFAULT_VIRTUAL_PATH = "/ls-access"
DEFAULT_USER_NAME = "lightspeed-user"
DEFAULT_SKIP_USER_ID_CHECK = True
DEFAULT_USER_UID = "00000000-0000-0000-0000-000"
# default value for token when no token is provided
NO_USER_TOKEN = ""
AUTH_MOD_K8S = "k8s"
AUTH_MOD_NOOP = "noop"
AUTH_MOD_NOOP_WITH_TOKEN = "noop-with-token"
AUTH_MOD_APIKEY_TOKEN = "api-key-token"
AUTH_MOD_JWK_TOKEN = "jwk-token"
AUTH_MOD_RH_IDENTITY = "rh-identity"
# Supported authentication modules
SUPPORTED_AUTHENTICATION_MODULES = frozenset(
    {
        AUTH_MOD_K8S,
        AUTH_MOD_NOOP,
        AUTH_MOD_NOOP_WITH_TOKEN,
        AUTH_MOD_JWK_TOKEN,
        AUTH_MOD_APIKEY_TOKEN,
        AUTH_MOD_RH_IDENTITY,
    }
)
DEFAULT_AUTHENTICATION_MODULE = AUTH_MOD_NOOP
DEFAULT_JWT_UID_CLAIM = "user_id"
DEFAULT_JWT_USER_NAME_CLAIM = "username"

# MCP authorization header special values
MCP_AUTH_KUBERNETES = "kubernetes"
MCP_AUTH_CLIENT = "client"
MCP_AUTH_OAUTH = "oauth"

# default RAG tool value
DEFAULT_RAG_TOOL = "file_search"

# Media type constants for streaming responses
MEDIA_TYPE_JSON = "application/json"
MEDIA_TYPE_TEXT = "text/plain"
MEDIA_TYPE_EVENT_STREAM = "text/event-stream"

# Streaming event type constants
LLM_TOKEN_EVENT = "token"
LLM_TOOL_CALL_EVENT = "tool_call"
LLM_TOOL_RESULT_EVENT = "tool_result"
LLM_TURN_COMPLETE_EVENT = "turn_complete"

# PostgreSQL connection constants
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLMODE
POSTGRES_DEFAULT_SSL_MODE = "prefer"
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-GSSENCMODE
POSTGRES_DEFAULT_GSS_ENCMODE = "prefer"

# cache constants
CACHE_TYPE_MEMORY = "memory"
CACHE_TYPE_SQLITE = "sqlite"
CACHE_TYPE_POSTGRES = "postgres"
CACHE_TYPE_NOOP = "noop"

# BYOK RAG
# Default RAG type for bring-your-own-knowledge RAG configurations, that type
# needs to be supported by Llama Stack
DEFAULT_RAG_TYPE = "inline::faiss"

# Default sentence transformer model for embedding generation, that type needs
# to be supported by Llama Stack and configured properly in providers and
# models sections
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"

# Default embedding vector dimension for the sentence transformer model
DEFAULT_EMBEDDING_DIMENSION = 768

# quota limiters constants
USER_QUOTA_LIMITER = "user_limiter"
CLUSTER_QUOTA_LIMITER = "cluster_limiter"

# Vector search constants
VECTOR_SEARCH_DEFAULT_K = 5
VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD = 0.0
VECTOR_SEARCH_DEFAULT_MODE = "hybrid"

# SOLR OKP RAG
MIMIR_DOC_URL = "https://mimir.corp.redhat.com"

# Logging configuration constants
# Environment variable name for configurable log level
LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR = "LIGHTSPEED_STACK_LOG_LEVEL"
# Default log level when environment variable is not set
DEFAULT_LOG_LEVEL = "INFO"
# Default log format for plain-text logging in non-TTY environments
DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
