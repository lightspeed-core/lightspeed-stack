"""Model with service configuration."""

# pylint: disable=too-many-lines

from pathlib import Path
from typing import Optional, Any, Pattern
from enum import Enum
from functools import cached_property
import re

import jsonpath_ng
from jsonpath_ng.exceptions import JSONPathError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    constr,
    FilePath,
    AnyHttpUrl,
    PositiveInt,
    NonNegativeInt,
    SecretStr,
)

from pydantic.dataclasses import dataclass
from typing_extensions import Self, Literal

import constants

from utils import checks


class ConfigurationBase(BaseModel):
    """Base class for all configuration models that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class TLSConfiguration(ConfigurationBase):
    """TLS configuration.

    Transport Layer Security (TLS) is a cryptographic protocol designed to
    provide communications security over a computer network, such as the
    Internet. The protocol is widely used in applications such as email,
    instant messaging, and voice over IP, but its use in securing HTTPS remains
    the most publicly visible.

    Useful resources:

      - [FastAPI HTTPS Deployment](https://fastapi.tiangolo.com/deployment/https/)
      - [Transport Layer Security Overview](https://en.wikipedia.org/wiki/Transport_Layer_Security)
      - [What is TLS](https://www.ssltrust.eu/learning/ssl/transport-layer-security-tls)
    """

    tls_certificate_path: Optional[FilePath] = Field(
        None,
        title="TLS certificate path",
        description="SSL/TLS certificate file path for HTTPS support.",
    )

    tls_key_path: Optional[FilePath] = Field(
        None,
        title="TLS key path",
        description="SSL/TLS private key file path for HTTPS support.",
    )

    tls_key_password: Optional[FilePath] = Field(
        None,
        title="SSL/TLS key password path",
        description="Path to file containing the password to decrypt the SSL/TLS private key.",
    )

    @model_validator(mode="after")
    def check_tls_configuration(self) -> Self:
        """Check TLS configuration."""
        return self


class CORSConfiguration(ConfigurationBase):
    """CORS configuration.

    CORS or 'Cross-Origin Resource Sharing' refers to the situations when a
    frontend running in a browser has JavaScript code that communicates with a
    backend, and the backend is in a different 'origin' than the frontend.

    Useful resources:

      - [CORS in FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
      - [Wikipedia article](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing)
      - [What is CORS?](https://dev.to/akshay_chauhan/what-is-cors-explained-8f1)
    """

    # not AnyHttpUrl: we need to support "*" that is not valid URL
    allow_origins: list[str] = Field(
        ["*"],
        title="Allow origins",
        description="A list of origins allowed for cross-origin requests. An origin "
        "is the combination of protocol (http, https), domain "
        "(myapp.com, localhost, localhost.tiangolo.com), and port (80, 443, 8080). "
        "Use ['*'] to allow all origins.",
    )

    allow_credentials: bool = Field(
        False,
        title="Allow credentials",
        description="Indicate that cookies should be supported for cross-origin requests",
    )

    allow_methods: list[str] = Field(
        ["*"],
        title="Allow methods",
        description="A list of HTTP methods that should be allowed for "
        "cross-origin requests. You can use ['*'] to allow "
        "all standard methods.",
    )

    allow_headers: list[str] = Field(
        ["*"],
        title="Allow headers",
        description="A list of HTTP request headers that should be supported "
        "for cross-origin requests. You can use ['*'] to allow all headers. The "
        "Accept, Accept-Language, Content-Language and Content-Type headers are "
        "always allowed for simple CORS requests.",
    )

    @model_validator(mode="after")
    def check_cors_configuration(self) -> Self:
        """Check CORS configuration."""
        # credentials are not allowed with wildcard origins per CORS/Fetch spec.
        # see https://fastapi.tiangolo.com/tutorial/cors/
        if self.allow_credentials and "*" in self.allow_origins:
            raise ValueError(
                "Invalid CORS configuration: allow_credentials can not be set to true when "
                "allow origins contains the '*' wildcard."
                "Use explicit origins or disable credentials."
            )
        return self


class SQLiteDatabaseConfiguration(ConfigurationBase):
    """SQLite database configuration."""

    db_path: str = Field(
        ...,
        title="DB path",
        description="Path to file where SQLite database is stored",
    )


class InMemoryCacheConfig(ConfigurationBase):
    """In-memory cache configuration."""

    max_entries: PositiveInt = Field(
        ...,
        title="Max entries",
        description="Maximum number of entries stored in the in-memory cache",
    )


class PostgreSQLDatabaseConfiguration(ConfigurationBase):
    """PostgreSQL database configuration.

    PostgreSQL database is used by Lightspeed Core Stack service for storing information about
    conversation IDs. It can also be leveraged to store conversation history and information
    about quota usage.

    Useful resources:

    - [Psycopg: connection classes](https://www.psycopg.org/psycopg3/docs/api/connections.html)
    - [PostgreSQL connection strings](https://www.connectionstrings.com/postgresql/)
    - [How to Use PostgreSQL in Python](https://www.freecodecamp.org/news/postgresql-in-python/)
    """

    host: str = Field(
        "localhost",
        title="Hostname",
        description="Database server host or socket directory",
    )

    port: PositiveInt = Field(
        5432,
        title="Port",
        description="Database server port",
    )

    db: str = Field(
        ...,
        title="Database name",
        description="Database name to connect to",
    )

    user: str = Field(
        ...,
        title="User name",
        description="Database user name used to authenticate",
    )

    password: SecretStr = Field(
        ...,
        title="Password",
        description="Password used to authenticate",
    )

    namespace: Optional[str] = Field(
        "lightspeed-stack",
        title="Name space",
        description="Database namespace",
    )

    ssl_mode: str = Field(
        constants.POSTGRES_DEFAULT_SSL_MODE,
        title="SSL mode",
        description="SSL mode",
    )

    gss_encmode: str = Field(
        constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        title="GSS encmode",
        description="This option determines whether or with what priority a secure GSS "
        "TCP/IP connection will be negotiated with the server.",
    )

    ca_cert_path: Optional[FilePath] = Field(
        None,
        title="CA certificate path",
        description="Path to CA certificate",
    )

    @model_validator(mode="after")
    def check_postgres_configuration(self) -> Self:
        """Check PostgreSQL configuration."""
        if self.port > 65535:
            raise ValueError("Port value should be less than 65536")
        return self


class DatabaseConfiguration(ConfigurationBase):
    """Database configuration."""

    sqlite: Optional[SQLiteDatabaseConfiguration] = Field(
        None,
        title="SQLite configuration",
        description="SQLite database configuration",
    )

    postgres: Optional[PostgreSQLDatabaseConfiguration] = Field(
        None,
        title="PostgreSQL configuration",
        description="PostgreSQL database configuration",
    )

    @model_validator(mode="after")
    def check_database_configuration(self) -> Self:
        """Check that exactly one database type is configured."""
        total_configured_dbs = sum([self.sqlite is not None, self.postgres is not None])

        if total_configured_dbs == 0:
            # Default to SQLite in a (hopefully) tmpfs if no database configuration is provided.
            # This is good for backwards compatibility for deployments that do not mind having
            # no persistent database.
            sqlite_file_name = "/tmp/lightspeed-stack.db"
            self.sqlite = SQLiteDatabaseConfiguration(db_path=sqlite_file_name)
        elif total_configured_dbs > 1:
            raise ValueError("Only one database configuration can be provided")

        return self

    @property
    def db_type(self) -> Literal["sqlite", "postgres"]:
        """Return the configured database type."""
        if self.sqlite is not None:
            return "sqlite"
        if self.postgres is not None:
            return "postgres"
        raise ValueError("No database configuration found")

    @property
    def config(self) -> SQLiteDatabaseConfiguration | PostgreSQLDatabaseConfiguration:
        """Return the active database configuration."""
        if self.sqlite is not None:
            return self.sqlite
        if self.postgres is not None:
            return self.postgres
        raise ValueError("No database configuration found")


class ServiceConfiguration(ConfigurationBase):
    """Service configuration.

    Lightspeed Core Stack is a REST API service that accepts requests
    on a specified hostname and port. It is also possible to enable
    authentication and specify the number of Uvicorn workers. When more
    workers are specified, the service can handle requests concurrently.
    """

    host: str = Field(
        "localhost",
        title="Host",
        description="Service hostname",
    )

    port: PositiveInt = Field(
        8080,
        title="Port",
        description="Service port",
    )

    auth_enabled: bool = Field(
        False,
        title="Authentication enabled",
        description="Enables the authentication subsystem",
    )

    workers: PositiveInt = Field(
        1,
        title="Number of workers",
        description="Number of Uvicorn worker processes to start",
    )

    color_log: bool = Field(
        True,
        title="Color log",
        description="Enables colorized logging",
    )

    access_log: bool = Field(
        True,
        title="Access log",
        description="Enables logging of all access information",
    )

    tls_config: TLSConfiguration = Field(
        default_factory=lambda: TLSConfiguration(
            tls_certificate_path=None, tls_key_path=None, tls_key_password=None
        ),
        title="TLS configuration",
        description="Transport Layer Security configuration for HTTPS support",
    )

    cors: CORSConfiguration = Field(
        default_factory=lambda: CORSConfiguration(
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        title="CORS configuration",
        description="Cross-Origin Resource Sharing configuration for cross-domain requests",
    )

    @model_validator(mode="after")
    def check_service_configuration(self) -> Self:
        """Check service configuration."""
        if self.port > 65535:
            raise ValueError("Port value should be less than 65536")
        return self


class ModelContextProtocolServer(ConfigurationBase):
    """Model context protocol server configuration.

    MCP (Model Context Protocol) servers provide tools and
    capabilities to the AI agents. These are configured by this structure.
    Only MCP servers defined in the lightspeed-stack.yaml configuration are
    available to the agents. Tools configured in the llama-stack run.yaml
    are not accessible to lightspeed-core agents.

    Useful resources:

    - [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)
    - [MCP FAQs](https://modelcontextprotocol.io/faqs)
    - [Wikipedia article](https://en.wikipedia.org/wiki/Model_Context_Protocol)
    """

    name: str = Field(
        ...,
        title="MCP name",
        description="MCP server name that must be unique",
    )

    provider_id: str = Field(
        "model-context-protocol",
        title="Provider ID",
        description="MCP provider identification",
    )

    url: str = Field(
        ...,
        title="MCP server URL",
        description="URL of the MCP server",
    )


class LlamaStackConfiguration(ConfigurationBase):
    """Llama stack configuration.

    Llama Stack is a comprehensive system that provides a uniform set of tools
    for building, scaling, and deploying generative AI applications, enabling
    developers to create, integrate, and orchestrate multiple AI services and
    capabilities into an adaptable setup.

    Useful resources:

      - [Llama Stack](https://www.llama.com/products/llama-stack/)
      - [Python Llama Stack client](https://github.com/llamastack/llama-stack-client-python)
      - [Build AI Applications with Llama Stack](https://llamastack.github.io/)
    """

    url: Optional[str] = Field(
        None,
        title="Llama Stack URL",
        description="URL to Llama Stack service; used when library mode is disabled",
    )

    api_key: Optional[SecretStr] = Field(
        None,
        title="API key",
        description="API key to access Llama Stack service",
    )

    use_as_library_client: Optional[bool] = Field(
        None,
        title="Use as library",
        description="When set to true Llama Stack will be used in library mode, not in "
        "server mode (default)",
    )

    library_client_config_path: Optional[str] = Field(
        None,
        title="Llama Stack configuration path",
        description="Path to configuration file used when Llama Stack is run in library mode",
    )

    @model_validator(mode="after")
    def check_llama_stack_model(self) -> Self:
        """
        Validate the Llama stack configuration after model initialization.

        Ensures that either a URL is provided for server mode or library client
        mode is explicitly enabled. If library client mode is enabled, verifies
        that a configuration file path is specified and points to an existing,
        readable file. Raises a ValueError if any required condition is not
        met.

        Returns:
            Self: The validated LlamaStackConfiguration instance.
        """
        if self.url is None:
            # when URL is not set, it is supposed that Llama Stack should be run in library mode
            # it means that use_as_library_client attribute must be set to True
            if self.use_as_library_client is None:
                raise ValueError(
                    "Llama stack URL is not specified and library client mode is not specified"
                )
            if self.use_as_library_client is False:
                raise ValueError(
                    "Llama stack URL is not specified and library client mode is not enabled"
                )

        # None -> False conversion
        if self.use_as_library_client is None:
            self.use_as_library_client = False

        if self.use_as_library_client:
            # when use_as_library_client is set to true, Llama Stack will be run in library mode
            # it means that:
            # - Llama Stack URL should not be set, and
            # - library_client_config_path attribute must be set and must point to
            #   a regular readable YAML file
            if self.library_client_config_path is None:
                # pylint: disable=line-too-long
                raise ValueError(
                    "Llama stack library client mode is enabled but a configuration file path is not specified"  # noqa: E501
                )
            # the configuration file must exists and be regular readable file
            checks.file_check(
                Path(self.library_client_config_path), "Llama Stack configuration file"
            )
        return self


class UserDataCollection(ConfigurationBase):
    """User data collection configuration."""

    feedback_enabled: bool = False
    feedback_storage: Optional[str] = None
    transcripts_enabled: bool = False
    transcripts_storage: Optional[str] = None

    @model_validator(mode="after")
    def check_storage_location_is_set_when_needed(self) -> Self:
        """Check that storage_location is set when enabled."""
        if self.feedback_enabled:
            if self.feedback_storage is None:
                raise ValueError(
                    "feedback_storage is required when feedback is enabled"
                )
            checks.directory_check(
                Path(self.feedback_storage),
                desc="Check directory to store feedback",
                must_exists=False,
                must_be_writable=True,
            )
        if self.transcripts_enabled:
            if self.transcripts_storage is None:
                raise ValueError(
                    "transcripts_storage is required when transcripts is enabled"
                )
            checks.directory_check(
                Path(self.transcripts_storage),
                desc="Check directory to store transcripts",
                must_exists=False,
                must_be_writable=True,
            )
        return self


class JsonPathOperator(str, Enum):
    """Supported operators for JSONPath evaluation."""

    EQUALS = "equals"
    CONTAINS = "contains"
    IN = "in"
    MATCH = "match"


class JwtRoleRule(ConfigurationBase):
    """Rule for extracting roles from JWT claims."""

    jsonpath: str = Field(
        ...,
        title="JSON path",
        description="JSONPath expression to evaluate against the JWT payload",
    )

    operator: JsonPathOperator = Field(
        ...,
        title="Operator",
        description="JSON path comparison operator",
    )

    negate: bool = Field(
        False,
        title="Negate rule",
        description="If set to true, the meaning of the rule is negated",
    )

    value: Any = Field(
        ...,
        title="Value",
        description="Value to compare against",
    )

    roles: list[str] = Field(
        ...,
        title="List of roles",
        description="Roles to be assigned if the rule matches",
    )

    @model_validator(mode="after")
    def check_jsonpath(self) -> Self:
        """Verify that the JSONPath expression is valid."""
        try:
            # try to parse the JSONPath
            jsonpath_ng.parse(self.jsonpath)
            return self
        except JSONPathError as e:
            raise ValueError(
                f"Invalid JSONPath expression: {self.jsonpath}: {e}"
            ) from e

    @model_validator(mode="after")
    def check_roles(self) -> Self:
        """Ensure that at least one role is specified."""
        if not self.roles:
            raise ValueError("At least one role must be specified in the rule")

        if len(self.roles) != len(set(self.roles)):
            raise ValueError("Roles must be unique in the rule")

        if any(role == "*" for role in self.roles):
            raise ValueError(
                "The wildcard '*' role is not allowed in role rules, "
                "everyone automatically gets this role"
            )

        return self

    @model_validator(mode="after")
    def check_regex_pattern(self) -> Self:
        """Verify that regex patterns are valid for MATCH operator."""
        if self.operator == JsonPathOperator.MATCH:
            if not isinstance(self.value, str):
                raise ValueError(
                    f"MATCH operator requires a string pattern, {type(self.value).__name__}"
                )
            try:
                re.compile(self.value)
            except re.error as e:
                raise ValueError(
                    f"Invalid regex pattern for MATCH operator: {self.value}: {e}"
                ) from e
        return self

    @cached_property
    def compiled_regex(self) -> Optional[Pattern[str]]:
        """Return compiled regex pattern for MATCH operator, None otherwise."""
        if self.operator == JsonPathOperator.MATCH and isinstance(self.value, str):
            return re.compile(self.value)
        return None


class Action(str, Enum):
    """Available actions in the system."""

    # Special action to allow unrestricted access to all actions
    ADMIN = "admin"

    # List the conversations of other users
    LIST_OTHERS_CONVERSATIONS = "list_other_conversations"

    # Read the contents of conversations of other users
    READ_OTHERS_CONVERSATIONS = "read_other_conversations"

    # Continue the conversations of other users
    QUERY_OTHERS_CONVERSATIONS = "query_other_conversations"

    # Delete the conversations of other users
    DELETE_OTHERS_CONVERSATIONS = "delete_other_conversations"

    # Access the query endpoint
    QUERY = "query"

    # Access the streaming query endpoint
    STREAMING_QUERY = "streaming_query"

    # Access the conversation endpoint
    GET_CONVERSATION = "get_conversation"

    # List own conversations
    LIST_CONVERSATIONS = "list_conversations"

    # Access the conversation delete endpoint
    DELETE_CONVERSATION = "delete_conversation"

    # Access the conversation update endpoint
    UPDATE_CONVERSATION = "update_conversation"
    FEEDBACK = "feedback"
    GET_MODELS = "get_models"
    GET_TOOLS = "get_tools"
    GET_SHIELDS = "get_shields"
    LIST_PROVIDERS = "list_providers"
    GET_PROVIDER = "get_provider"
    LIST_RAGS = "list_rags"
    GET_RAG = "get_rag"
    GET_METRICS = "get_metrics"
    GET_CONFIG = "get_config"

    INFO = "info"
    # Allow overriding model/provider via request
    MODEL_OVERRIDE = "model_override"


class AccessRule(ConfigurationBase):
    """Rule defining what actions a role can perform."""

    role: str  # Role name
    actions: list[Action]  # Allowed actions for this role


class AuthorizationConfiguration(ConfigurationBase):
    """Authorization configuration."""

    access_rules: list[AccessRule] = Field(
        default_factory=list
    )  # Rules for role-based access control


class JwtConfiguration(ConfigurationBase):
    """JWT configuration."""

    user_id_claim: str = constants.DEFAULT_JWT_UID_CLAIM
    username_claim: str = constants.DEFAULT_JWT_USER_NAME_CLAIM
    role_rules: list[JwtRoleRule] = Field(
        default_factory=list
    )  # Rules for extracting roles from JWT claims


class JwkConfiguration(ConfigurationBase):
    """JWK configuration."""

    url: AnyHttpUrl
    jwt_configuration: JwtConfiguration = Field(default_factory=JwtConfiguration)


class RHIdentityConfiguration(ConfigurationBase):
    """Red Hat Identity authentication configuration."""

    required_entitlements: Optional[list[str]] = None


class APIKeyTokenConfiguration(ConfigurationBase):
    """API Key Token configuration."""

    # Use SecretStr to prevent accidental exposure in logs or error messages.
    api_key: SecretStr = Field(
        min_length=1,
        title="API key",
        json_schema_extra={
            "format": "password",
            "writeOnly": True,
            "examples": ["some-api-key"],
        },
    )


class AuthenticationConfiguration(ConfigurationBase):
    """Authentication configuration."""

    module: str = constants.DEFAULT_AUTHENTICATION_MODULE
    skip_tls_verification: bool = False
    k8s_cluster_api: Optional[AnyHttpUrl] = None
    k8s_ca_cert_path: Optional[FilePath] = None
    jwk_config: Optional[JwkConfiguration] = None
    api_key_config: Optional[APIKeyTokenConfiguration] = None
    rh_identity_config: Optional[RHIdentityConfiguration] = None

    @model_validator(mode="after")
    def check_authentication_model(self) -> Self:
        """Validate YAML containing authentication configuration section."""
        if self.module not in constants.SUPPORTED_AUTHENTICATION_MODULES:
            supported_modules = ", ".join(constants.SUPPORTED_AUTHENTICATION_MODULES)
            raise ValueError(
                f"Unsupported authentication module '{self.module}'. "
                f"Supported modules: {supported_modules}"
            )

        if self.module == constants.AUTH_MOD_JWK_TOKEN:
            if self.jwk_config is None:
                raise ValueError(
                    "JWK configuration must be specified when using JWK token authentication"
                )

        if self.module == constants.AUTH_MOD_RH_IDENTITY:
            if self.rh_identity_config is None:
                raise ValueError(
                    "RH Identity configuration must be specified "
                    "when using RH Identity authentication"
                )

        if self.module == constants.AUTH_MOD_APIKEY_TOKEN:
            if self.api_key_config is None:
                raise ValueError(
                    "API Key configuration section must be specified when using API Key token authentication"
                )
            if self.api_key_config.api_key.get_secret_value() is None:
                raise ValueError(
                    "api_key parameter must be specified when using API_KEY token authentication"
                )

        return self

    @property
    def jwk_configuration(self) -> JwkConfiguration:
        """Return JWK configuration if the module is JWK token."""
        if self.module != constants.AUTH_MOD_JWK_TOKEN:
            raise ValueError(
                "JWK configuration is only available for JWK token authentication module"
            )
        if self.jwk_config is None:
            raise ValueError("JWK configuration should not be None")
        return self.jwk_config

    @property
    def rh_identity_configuration(self) -> RHIdentityConfiguration:
        """Return RH Identity configuration if the module is RH Identity."""
        if self.module != constants.AUTH_MOD_RH_IDENTITY:
            raise ValueError(
                "RH Identity configuration is only available for RH Identity authentication module"
            )
        if self.rh_identity_config is None:
            raise ValueError("RH Identity configuration should not be None")
        return self.rh_identity_config

    @property
    def api_key_configuration(self) -> APIKeyTokenConfiguration:
        """Return API_KEY configuration if the module is API_KEY token."""
        if self.module != constants.AUTH_MOD_APIKEY_TOKEN:
            raise ValueError(
                "API Key configuration is only available for API Key token authentication module"
            )
        if self.api_key_config is None:
            raise ValueError("API Key configuration should not be None")
        return self.api_key_config


@dataclass
class CustomProfile:
    """Custom profile customization for prompts and validation."""

    path: str
    prompts: dict[str, str] = Field(default={}, init=False)

    def __post_init__(self) -> None:
        """Validate and load profile."""
        self._validate_and_process()

    def _validate_and_process(self) -> None:
        """Validate and load the profile."""
        checks.file_check(Path(self.path), "custom profile")
        profile_module = checks.import_python_module("profile", self.path)
        if profile_module is not None and checks.is_valid_profile(profile_module):
            self.prompts = profile_module.PROFILE_CONFIG.get("system_prompts", {})

    def get_prompts(self) -> dict[str, str]:
        """Retrieve prompt attribute."""
        return self.prompts


class Customization(ConfigurationBase):
    """Service customization."""

    profile_path: Optional[str] = None
    disable_query_system_prompt: bool = False
    system_prompt_path: Optional[FilePath] = None
    system_prompt: Optional[str] = None
    custom_profile: Optional[CustomProfile] = Field(default=None, init=False)

    @model_validator(mode="after")
    def check_customization_model(self) -> Self:
        """Load customizations."""
        if self.profile_path:
            self.custom_profile = CustomProfile(path=self.profile_path)
        elif self.system_prompt_path is not None:
            checks.file_check(self.system_prompt_path, "system prompt")
            self.system_prompt = checks.get_attribute_from_file(
                dict(self), "system_prompt_path"
            )
        return self


class InferenceConfiguration(ConfigurationBase):
    """Inference configuration."""

    default_model: Optional[str] = None
    default_provider: Optional[str] = None

    @model_validator(mode="after")
    def check_default_model_and_provider(self) -> Self:
        """Check default model and provider."""
        if self.default_model is None and self.default_provider is not None:
            raise ValueError(
                "Default model must be specified when default provider is set"
            )
        if self.default_model is not None and self.default_provider is None:
            raise ValueError(
                "Default provider must be specified when default model is set"
            )
        return self


class ConversationHistoryConfiguration(ConfigurationBase):
    """Conversation history configuration."""

    type: Literal["noop", "memory", "sqlite", "postgres"] | None = None
    memory: Optional[InMemoryCacheConfig] = None
    sqlite: Optional[SQLiteDatabaseConfiguration] = None
    postgres: Optional[PostgreSQLDatabaseConfiguration] = None

    @model_validator(mode="after")
    def check_cache_configuration(self) -> Self:
        """Check conversation cache configuration."""
        # if any backend config is provided, type must be explicitly selected
        if self.type is None:
            if any([self.memory, self.sqlite, self.postgres]):
                raise ValueError(
                    "Conversation cache type must be set when backend configuration is provided"
                )
            # no type selected + no configuration is expected and fully supported
            return self
        match self.type:
            case constants.CACHE_TYPE_MEMORY:
                if self.memory is None:
                    raise ValueError("Memory cache is selected, but not configured")
                # no other DBs configuration allowed
                if any([self.sqlite, self.postgres]):
                    raise ValueError("Only memory cache config must be provided")
            case constants.CACHE_TYPE_SQLITE:
                if self.sqlite is None:
                    raise ValueError("SQLite cache is selected, but not configured")
                # no other DBs configuration allowed
                if any([self.memory, self.postgres]):
                    raise ValueError("Only SQLite cache config must be provided")
            case constants.CACHE_TYPE_POSTGRES:
                if self.postgres is None:
                    raise ValueError("PostgreSQL cache is selected, but not configured")
                # no other DBs configuration allowed
                if any([self.memory, self.sqlite]):
                    raise ValueError("Only PostgreSQL cache config must be provided")
        return self


class ByokRag(ConfigurationBase):
    """BYOK RAG configuration."""

    rag_id: constr(min_length=1)  # type:ignore
    rag_type: constr(min_length=1) = constants.DEFAULT_RAG_TYPE  # type:ignore
    embedding_model: constr(min_length=1) = (  # type:ignore
        constants.DEFAULT_EMBEDDING_MODEL
    )
    embedding_dimension: PositiveInt = constants.DEFAULT_EMBEDDING_DIMENSION
    vector_db_id: constr(min_length=1)  # type:ignore
    db_path: FilePath


class QuotaLimiterConfiguration(ConfigurationBase):
    """Configuration for one quota limiter.

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
    """

    type: Literal["user_limiter", "cluster_limiter"] = Field(
        ...,
        title="Quota limiter type",
        description="Quota limiter type, either user_limiter or cluster_limiter",
    )

    name: str = Field(
        ...,
        title="Quota limiter name",
        description="Human readable quota limiter name",
    )

    initial_quota: NonNegativeInt = Field(
        ...,
        title="Initial quota",
        description="Quota set at beginning of the period",
    )

    quota_increase: NonNegativeInt = Field(
        ...,
        title="Quota increase",
        description="Delta value used to increase quota when period is reached",
    )

    period: str = Field(
        ...,
        title="Period",
        description="Period specified in human readable form",
    )


class QuotaSchedulerConfiguration(ConfigurationBase):
    """Quota scheduler configuration."""

    period: PositiveInt = Field(
        1,
        title="Period",
        description="Quota scheduler period specified in seconds",
    )


class QuotaHandlersConfiguration(ConfigurationBase):
    """Quota limiter configuration.

    It is possible to limit quota usage per user or per service or services
    (that typically run in one cluster). Each limit is configured as a separate
    _quota limiter_. It can be of type `user_limiter` or `cluster_limiter`
    (which is name that makes sense in OpenShift deployment).
    """

    sqlite: Optional[SQLiteDatabaseConfiguration] = Field(
        None,
        title="SQLite configuration",
        description="SQLite database configuration",
    )

    postgres: Optional[PostgreSQLDatabaseConfiguration] = Field(
        None,
        title="PostgreSQL configuration",
        description="PostgreSQL database configuration",
    )

    limiters: list[QuotaLimiterConfiguration] = Field(
        default_factory=list,
        title="Quota limiters",
        description="Quota limiters configuration",
    )

    scheduler: QuotaSchedulerConfiguration = Field(
        default_factory=lambda: QuotaSchedulerConfiguration(period=1),
        title="Quota scheduler",
        description="Quota scheduler configuration",
    )

    enable_token_history: bool = Field(
        False,
        title="Enable token history",
        description="Enables storing information about token usage history",
    )


class Configuration(ConfigurationBase):
    """Global service configuration."""

    name: str = Field(
        ...,
        title="Service name",
        description="Name of the service. That value will be used in REST API endpoints.",
    )

    service: ServiceConfiguration = Field(
        ...,
        title="Service configuration",
        description="This section contains Lightspeed Core Stack service configuration.",
    )

    llama_stack: LlamaStackConfiguration = Field(
        ...,
        title="Llama Stack configuration",
        description="This section contains Llama Stack configuration. "
        "Lightspeed Core Stack service can call Llama Stack in library mode or in server mode.",
    )

    user_data_collection: UserDataCollection = Field(
        ...,
        title="User data collection configuration",
        description="This section contains configuration for subsystem that collects user data"
        "(transcription history and feedbacks).",
    )

    database: DatabaseConfiguration = Field(
        default_factory=lambda: DatabaseConfiguration(sqlite=None, postgres=None),
        title="Database Configuration",
        description="Configuration for database to store conversation IDs and other runtime data",
    )

    mcp_servers: list[ModelContextProtocolServer] = Field(
        default_factory=list,
        title="Model Context Protocol Server and tools configuration",
        description="MCP (Model Context Protocol) servers provide tools and "
        "capabilities to the AI agents. These are configured in this section. "
        "Only MCP servers defined in the lightspeed-stack.yaml configuration are "
        "available to the agents. Tools configured in the llama-stack run.yaml "
        "are not accessible to lightspeed-core agents.",
    )

    authentication: AuthenticationConfiguration = Field(
        default_factory=AuthenticationConfiguration,
        title="Authentication configuration",
        description="Authentication configuration",
    )

    authorization: Optional[AuthorizationConfiguration] = Field(
        None,
        title="Authorization configuration",
        description="Lightspeed Core Stack implements a modular "
        "authentication and authorization system with multiple authentication "
        "methods. Authorization is configurable through role-based access "
        "control. Authentication is handled through selectable modules "
        "configured via the module field in the authentication configuration.",
    )

    customization: Optional[Customization] = Field(
        None,
        title="Custom profile configuration",
        description="It is possible to customize Lightspeed Core Stack via this "
        "section. System prompt can be customized and also different parts of "
        "the service can be replaced by custom Python modules.",
    )

    inference: InferenceConfiguration = Field(
        default_factory=InferenceConfiguration,
        title="Inference configuration",
        description="One LLM provider and one its model might be selected as "
        "default ones. When no provider+model pair is specified in REST API "
        "calls (query endpoints), the default provider and model are used.",
    )

    conversation_cache: ConversationHistoryConfiguration = Field(
        default_factory=ConversationHistoryConfiguration,
        title="Conversation history configuration",
        description="Conversation history configuration.",
    )

    byok_rag: list[ByokRag] = Field(
        default_factory=list,
        title="BYOK RAG configuration",
        description="BYOK RAG configuration. This configuration can be used to "
        "reconfigure Llama Stack through its run.yaml configuration file",
    )

    quota_handlers: QuotaHandlersConfiguration = Field(
        default_factory=lambda: QuotaHandlersConfiguration(
            sqlite=None, postgres=None, enable_token_history=False
        ),
        title="Quota handlers",
        description="Quota handlers configuration",
    )

    def dump(self, filename: str = "configuration.json") -> None:
        """Dump actual configuration into JSON file."""
        with open(filename, "w", encoding="utf-8") as fout:
            fout.write(self.model_dump_json(indent=4))
