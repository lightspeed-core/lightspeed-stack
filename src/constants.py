"""Constants used in business logic."""

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

# Authentication constants
DEFAULT_VIRTUAL_PATH = "/ls-access"
DEFAULT_USER_NAME = "lightspeed-user"
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

# Data collector constants
DATA_COLLECTOR_COLLECTION_INTERVAL = 7200  # 2 hours in seconds
DATA_COLLECTOR_CONNECTION_TIMEOUT = 30
DATA_COLLECTOR_RETRY_INTERVAL = 300  # 5 minutes in seconds
