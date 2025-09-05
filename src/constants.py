"""Constants used in business logic."""

# Minimal and maximal supported Llama Stack version
MINIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.2.17"
MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION = "0.2.18"

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


# PostgreSQL connection constants
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLMODE
POSTGRES_DEFAULT_SSL_MODE = "prefer"
# See: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-GSSENCMODE
POSTGRES_DEFAULT_GSS_ENCMODE = "prefer"
