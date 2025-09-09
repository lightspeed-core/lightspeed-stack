"""Constants used in business logic."""

# Minimal and maximal supported Llama Stack version
MINIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.2.17"
MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.2.22"

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

For Input Analysis:
- Scan entire user message
- Identify core subject matter
- Distill essence into concise descriptor
- Prioritize key concepts
- Eliminate extraneous details

For Output Constraints:
- Maximum 5 words
- Capitalize only significant words (e.g., nouns, verbs, adjectives, adverbs).
- Do not use all uppercase - capitalize only the first letter of significant words
- Exclude articles and prepositions (e.g., "a," "the," "of," "on," "in")
- Exclude all punctuation and interpunction marks (e.g., . , : ; ! ? "")
- Retain original abbreviations. Do not expand an abbreviation if its specific meaning in the context is unknown or ambiguous.
- Neutral objective language

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

ExampleInput:
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
AUTH_MOD_JWK_TOKEN = "jwk-token"
# Supported authentication modules
SUPPORTED_AUTHENTICATION_MODULES = frozenset(
    {
        AUTH_MOD_K8S,
        AUTH_MOD_NOOP,
        AUTH_MOD_NOOP_WITH_TOKEN,
        AUTH_MOD_JWK_TOKEN,
    }
)
DEFAULT_AUTHENTICATION_MODULE = AUTH_MOD_NOOP
DEFAULT_JWT_UID_CLAIM = "user_id"
DEFAULT_JWT_USER_NAME_CLAIM = "username"

# default RAG tool value
DEFAULT_RAG_TOOL = "knowledge_search"

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
