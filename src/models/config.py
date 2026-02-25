"""Model with service configuration."""

# pylint: disable=too-many-lines

from pathlib import Path
from typing import Optional, Any, Pattern
from enum import Enum
from functools import cached_property
import re
import yaml

import jsonpath_ng
from jsonpath_ng.exceptions import JSONPathError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    FilePath,
    AnyHttpUrl,
    PositiveInt,
    NonNegativeInt,
    SecretStr,
    PrivateAttr,
)

from pydantic.dataclasses import dataclass
from typing_extensions import Self, Literal

import constants

from utils import checks
from utils.mcp_auth_headers import resolve_authorization_headers
from log import get_logger

logger = get_logger(__name__)


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
        """
        Perform post-validation checks for the TLS configuration.

        Currently a no-op that returns the model unchanged.

        Returns:
            Self: The validated model instance.
        """
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
        """
        Validate CORS settings and enforce that credentials are not allowed.

        Raises:
            ValueError: If `allow_credentials` is true while
            `allow_origins` contains the "*" wildcard.

        Returns:
            Self: The validated configuration instance.
        """
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

    PostgreSQL database is used by Lightspeed Core Stack service for storing
    information about conversation IDs. It can also be leveraged to store
    conversation history and information about quota usage.

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
        "public",
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
        """
        Validate PostgreSQL configuration constraints.

        Ensures the configured port is within the valid TCP port range.

        Returns:
            self: The validated configuration instance.

        Raises:
            ValueError: If `port` is greater than 65535.
        """
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
        """
        Ensure exactly one database backend is configured, defaulting to a temporary SQLite one.

        If neither `sqlite` nor `postgres` is set, assigns a default SQLite
        configuration using the file path "/tmp/lightspeed-stack.db". If both
        backends are configured, raises a `ValueError`.

        Returns:
            self: The configuration instance with exactly one
            database backend set.
        """
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
        """
        Determine which database backend is configured.

        Returns:
            The string "sqlite" if a SQLite configuration is
            present, "postgres" if a PostgreSQL configuration is
            present.

        Raises:
            ValueError: If neither SQLite nor PostgreSQL configuration is set.
        """
        if self.sqlite is not None:
            return "sqlite"
        if self.postgres is not None:
            return "postgres"
        raise ValueError("No database configuration found")

    @property
    def config(self) -> SQLiteDatabaseConfiguration | PostgreSQLDatabaseConfiguration:
        """
        Get the active database backend configuration.

        Returns:
            SQLiteDatabaseConfiguration or PostgreSQLDatabaseConfiguration: The
            configured SQLite configuration if `sqlite` is set, otherwise the
            configured PostgreSQL configuration if `postgres` is set.

        Raises:
            ValueError: If neither `sqlite` nor `postgres` is
            configured.
        """
        if self.sqlite is not None:
            return self.sqlite
        if self.postgres is not None:
            return self.postgres
        raise ValueError("No database configuration found")


class ServiceConfiguration(ConfigurationBase):
    """Service configuration.

    Lightspeed Core Stack is a REST API service that accepts requests on a
    specified hostname and port. It is also possible to enable authentication
    and specify the number of Uvicorn workers. When more workers are specified,
    the service can handle requests concurrently.
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

    base_url: Optional[str] = Field(
        None,
        title="Base URL",
        description="Externally reachable base URL for the service; needed for A2A support.",
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

    root_path: str = Field(
        "",
        title="Root path",
        description="ASGI root path for serving behind a reverse proxy on a subpath",
    )

    @field_validator("root_path")
    @classmethod
    def validate_root_path(cls, value: str) -> str:
        """Validate root_path format.

        Ensures the root path is either empty or starts with a leading
        slash and does not end with a trailing slash.

        Parameters:
            value: The root path value to validate.

        Returns:
            The validated root path value.

        Raises:
            ValueError: If root_path is missing a leading slash or has
                a trailing slash.
        """
        if value and not value.startswith("/"):
            raise ValueError("root_path must start with '/'")
        if value.endswith("/"):
            raise ValueError("root_path must not end with '/'")
        return value

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
        """
        Validate service configuration and enforce allowed port range.

        Raises:
            ValueError: If `port` is greater than 65535.

        Returns:
            self: The validated model instance.
        """
        if self.port > 65535:
            raise ValueError("Port value should be less than 65536")
        return self


class ModelContextProtocolServer(ConfigurationBase):
    """Model context protocol server configuration.

    MCP (Model Context Protocol) servers provide tools and capabilities to the
    AI agents. These are configured by this structure. Only MCP servers
    defined in the lightspeed-stack.yaml configuration are available to the
    agents. Tools configured in the llama-stack run.yaml are not accessible to
    lightspeed-core agents.

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

    authorization_headers: dict[str, str] = Field(
        default_factory=dict,
        title="Authorization headers",
        description=(
            "Headers to send to the MCP server. "
            "The map contains the header name and the path to a file containing "
            "the header value (secret). "
            "There are 3 special cases: "
            "1. Usage of the kubernetes token in the header. "
            "To specify this use a string 'kubernetes' instead of the file path. "
            "2. Usage of the client-provided token in the header. "
            "To specify this use a string 'client' instead of the file path. "
            "3. Usage of the oauth token in the header. "
            "To specify this use a string 'oauth' instead of the file path. "
        ),
    )

    _resolved_authorization_headers: dict[str, str] = PrivateAttr(default_factory=dict)

    @property
    def resolved_authorization_headers(self) -> dict[str, str]:
        """Resolved authorization headers (computed from authorization_headers)."""
        return self._resolved_authorization_headers

    headers: list[str] = Field(
        default_factory=list,
        title="Propagated headers",
        description=(
            "List of HTTP header names to automatically forward from the incoming "
            "request to this MCP server. Headers listed here are extracted from "
            "the original client request and included when calling the MCP server. "
            "This is useful when infrastructure components (e.g. API gateways) "
            "inject headers that MCP servers need, such as x-rh-identity in HCC. "
            "Header matching is case-insensitive. "
            "These headers are additive with authorization_headers and MCP-HEADERS."
        ),
    )

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: list[str]) -> list[str]:
        """Validate propagated headers: no empty strings, no case-insensitive duplicates."""
        seen: set[str] = set()
        for header in value:
            if not header.strip():
                msg = "Header names must not be empty"
                raise ValueError(msg)
            lower = header.lower()
            if lower in seen:
                msg = f"Duplicate header name (case-insensitive): '{header}'"
                raise ValueError(msg)
            seen.add(lower)
        return value

    timeout: Optional[PositiveInt] = Field(
        default=None,
        title="Request timeout",
        description=(
            "Timeout in seconds for requests to the MCP server. "
            "If not specified, the default timeout from Llama Stack will be used. "
            "Note: This field is reserved for future use when Llama Stack adds timeout support."
        ),
    )

    @model_validator(mode="after")
    def resolve_auth_headers(self) -> Self:
        """
        Resolve authorization headers by reading secret files.

        Automatically populates resolved_authorization_headers by reading
        secret files specified in authorization_headers. Special values
        'kubernetes' and 'client' are preserved for later substitution.

        Returns:
            Self: The model instance with resolved_authorization_headers populated.
        """
        if self.authorization_headers:
            self._resolved_authorization_headers = resolve_authorization_headers(
                self.authorization_headers
            )
        return self


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

    url: Optional[AnyHttpUrl] = Field(
        None,
        title="Llama Stack URL",
        description="URL to Llama Stack service; used when library mode is disabled. "
        "Must be a valid HTTP or HTTPS URL.",
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

    timeout: PositiveInt = Field(
        180,
        title="Request timeout",
        description="Timeout in seconds for requests to Llama Stack service. "
        "Default is 180 seconds (3 minutes) to accommodate long-running RAG queries.",
    )

    @model_validator(mode="after")
    def check_llama_stack_model(self) -> Self:
        """
        Validate the Llama Stack configuration and enforce mode-specific requirements.

        If no URL is provided, requires explicit library-client mode selection.
        When library-client mode is enabled, requires a non-empty
        `library_client_config_path` that points to a regular, readable YAML
        file (checked via checks.file_check). Also normalizes a None
        `use_as_library_client` to False.

        Returns:
            Self: The validated LlamaStackConfiguration instance.

        Raises:
            ValueError: If the configuration is invalid, e.g. no
            URL and library-client mode is unspecified or
            disabled, or library-client mode is enabled but
            `library_client_config_path` is not provided.
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


class SplunkConfiguration(ConfigurationBase):
    """Splunk HEC (HTTP Event Collector) configuration.

    Splunk HEC allows sending events directly to Splunk over HTTP/HTTPS.
    This configuration is used to send telemetry events for inference
    requests to the corporate Splunk deployment.

    Useful resources:

      - [Splunk HEC Docs](https://docs.splunk.com/Documentation/SplunkCloud)
      - [About HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data)
    """

    enabled: bool = Field(
        False,
        title="Enabled",
        description="Enable or disable Splunk HEC integration.",
    )

    url: Optional[str] = Field(
        None,
        title="HEC URL",
        description="Splunk HEC endpoint URL.",
    )

    token_path: Optional[FilePath] = Field(
        None,
        title="Token path",
        description="Path to file containing the Splunk HEC authentication token.",
    )

    index: Optional[str] = Field(
        None,
        title="Index",
        description="Target Splunk index for events.",
    )

    source: str = Field(
        "lightspeed-stack",
        title="Source",
        description="Event source identifier.",
    )

    timeout: PositiveInt = Field(
        5,
        title="Timeout",
        description="HTTP timeout in seconds for HEC requests.",
    )

    verify_ssl: bool = Field(
        True,
        title="Verify SSL",
        description="Whether to verify SSL certificates for HEC endpoint.",
    )

    @model_validator(mode="after")
    def check_splunk_configuration(self) -> Self:
        """Validate that required fields are set when Splunk is enabled.

        Returns:
            Self: The validated configuration instance.

        Raises:
            ValueError: If enabled is True but required fields are missing.
        """
        if self.enabled:
            missing_fields = []
            if not self.url:
                missing_fields.append("url")
            if not self.token_path:
                missing_fields.append("token_path")
            if not self.index:
                missing_fields.append("index")
            if missing_fields:
                raise ValueError(
                    f"Splunk is enabled but required fields are missing: "
                    f"{', '.join(missing_fields)}"
                )
        return self


class UserDataCollection(ConfigurationBase):
    """User data collection configuration."""

    feedback_enabled: bool = Field(
        False,
        title="Feedback enabled",
        description="When set to true the user feedback is stored and later sent for analysis.",
    )

    feedback_storage: Optional[str] = Field(
        None,
        title="Feedback storage directory",
        description="Path to directory where feedback will be saved for further processing.",
    )

    transcripts_enabled: bool = Field(
        False,
        title="Transcripts enabled",
        description="When set to true the conversation history is stored and later sent for "
        "analysis.",
    )

    transcripts_storage: Optional[str] = Field(
        None,
        title="Transcripts storage directory",
        description="Path to directory where conversation history will be saved for further "
        "processing.",
    )

    @model_validator(mode="after")
    def check_storage_location_is_set_when_needed(self) -> Self:
        """
        Ensure storage locations are configured and writable when feedback is enabled.

        If feedback collection is enabled, `feedback_storage` must be provided
        and refer to a directory that exists or can be created and is writable.
        If transcript collection is enabled, `transcripts_storage` must be
        provided and refer to a directory that exists or can be created and is
        writable.

        Returns:
            self: The validated UserDataCollection instance.
        """
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
    """Supported operators for JSONPath evaluation.

    Note: this is not a real model, just an enumeration of all supported JSONPath operators.
    """

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
        """
        Validate that the `jsonpath` expression parses as a JSONPath.

        Returns:
            self: The same model instance when the JSONPath
            expression is valid.

        Raises:
            ValueError: If the `jsonpath` cannot be parsed; the
            message includes the offending expression and parser
            error.
        """
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
        """
        Validate the rule's roles list and enforce required constraints.

        Performs three checks: ensures at least one role is present, enforces
        that all roles are unique, and prohibits the wildcard role `"*"`.

        Returns:
            self: The same `JwtRoleRule` instance when validation
            succeeds.
        """
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
        """
        Validate that when the operator is MATCH, the rule is a valid regular expression string.

        Raises:
            ValueError: If the operator is MATCH and `value` is
            not a string or is not a valid regular expression.

        Returns:
            Self: The same JwtRoleRule instance.
        """
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
        """
        Provide a compiled regex when the rule uses the MATCH operator and the value is a string.

        Returns:
            Optional[Pattern[str]]: Compiled `re.Pattern` of `value` if
            `operator` is `JsonPathOperator.MATCH` and `value` is a `str`,
            `None` otherwise.
        """
        if self.operator == JsonPathOperator.MATCH and isinstance(self.value, str):
            return re.compile(self.value)
        return None


class Action(str, Enum):
    """Available actions in the system.

    Note: this is not a real model, just an enumeration of all action names.
    """

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
    # RHEL Lightspeed rlsapi v1 compatibility - stateless inference (no history/RAG)
    RLSAPI_V1_INFER = "rlsapi_v1_infer"

    # A2A (Agent-to-Agent) protocol actions
    A2A_AGENT_CARD = "a2a_agent_card"
    A2A_TASK_EXECUTION = "a2a_task_execution"
    A2A_MESSAGE = "a2a_message"
    A2A_JSONRPC = "a2a_jsonrpc"


class AccessRule(ConfigurationBase):
    """Rule defining what actions a role can perform."""

    role: str = Field(
        ...,
        title="Role name",
        description="Name of the role",
    )

    actions: list[Action] = Field(
        ...,
        title="Allowed actions",
        description="Allowed actions for this role",
    )


class AuthorizationConfiguration(ConfigurationBase):
    """Authorization configuration."""

    access_rules: list[AccessRule] = Field(
        default_factory=list,
        title="Access rules",
        description="Rules for role-based access control",
    )


class JwtConfiguration(ConfigurationBase):
    """JWT (JSON Web Token) configuration.

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
    """

    user_id_claim: str = Field(
        constants.DEFAULT_JWT_UID_CLAIM,
        title="User ID claim",
        description="JWT claim name that uniquely identifies the user (subject ID).",
    )

    username_claim: str = Field(
        constants.DEFAULT_JWT_USER_NAME_CLAIM,
        title="Username claim",
        description="JWT claim name that provides the human-readable username.",
    )

    role_rules: list[JwtRoleRule] = Field(
        default_factory=list,
        title="Role rules",
        description="Rules for extracting roles from JWT claims",
    )


class JwkConfiguration(ConfigurationBase):
    """JWK (JSON Web Key) configuration.

    A JSON Web Key (JWK) is a JavaScript Object Notation (JSON) data structure
    that represents a cryptographic key.

    Useful resources:

      - [JSON Web Key](https://openid.net/specs/draft-jones-json-web-key-03.html)
      - [RFC 7517](https://www.rfc-editor.org/rfc/rfc7517)
    """

    url: AnyHttpUrl = Field(
        ...,
        title="URL",
        description="HTTPS URL of the JWK (JSON Web Key) set used to validate JWTs.",
    )

    jwt_configuration: JwtConfiguration = Field(
        default_factory=lambda: JwtConfiguration(
            user_id_claim=constants.DEFAULT_JWT_UID_CLAIM,
            username_claim=constants.DEFAULT_JWT_USER_NAME_CLAIM,
        ),
        title="JWT configuration",
        description="JWT (JSON Web Token) configuration",
    )


class RHIdentityConfiguration(ConfigurationBase):
    """Red Hat Identity authentication configuration."""

    required_entitlements: Optional[list[str]] = Field(
        None,
        title="Required entitlements",
        description="List of all required entitlements.",
    )


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

    # LCORE-694: Config option to skip authorization for readiness and liveness probe
    skip_for_health_probes: bool = Field(
        False,
        title="Skip authorization for probes",
        description="Skip authorization for readiness and liveness probes",
    )
    k8s_cluster_api: Optional[AnyHttpUrl] = None
    k8s_ca_cert_path: Optional[FilePath] = None
    jwk_config: Optional[JwkConfiguration] = None
    api_key_config: Optional[APIKeyTokenConfiguration] = None
    rh_identity_config: Optional[RHIdentityConfiguration] = None

    @model_validator(mode="after")
    def check_authentication_model(self) -> Self:
        """
        Validate authentication configuration and enforce module-specific requirements.

        Checks that the selected authentication module is supported and that any module-specific
        configuration (JWK or RH Identity) is present when required.

        Returns:
            self: The validated AuthenticationConfiguration instance.

        Raises:
            ValueError: If the module is unsupported, or if a required module-specific
                configuration (jwk_config for JWK token or rh_identity_config for RH Identity)
                is missing.
        """
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
                    "API Key configuration section must be specified "
                    "when using API Key token authentication"
                )
            if self.api_key_config.api_key.get_secret_value() is None:
                raise ValueError(
                    "api_key parameter must be specified when using API_KEY token authentication"
                )

        return self

    @property
    def jwk_configuration(self) -> JwkConfiguration:
        """
        Return the active JWK configuration for JWK-token authentication.

        Raises:
            ValueError: If the authentication module is not the JWK token
            module or if the JWK configuration is not set.

        Returns:
            JwkConfiguration: The configured JWK settings.
        """
        if self.module != constants.AUTH_MOD_JWK_TOKEN:
            raise ValueError(
                "JWK configuration is only available for JWK token authentication module"
            )
        if self.jwk_config is None:
            raise ValueError("JWK configuration should not be None")
        return self.jwk_config

    @property
    def rh_identity_configuration(self) -> RHIdentityConfiguration:
        """
        Access the RH Identity configuration for RH Identity authentication.

        Returns:
            RHIdentityConfiguration: The configured RH Identity configuration object.

        Raises:
            ValueError: If the active authentication module is not RH Identity.
            ValueError: If the RH Identity configuration is missing when the module is RH Identity.
        """
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

    path: str = Field(
        ...,
        title="Path to custom profile",
        description="Path to Python modules containing custom profile.",
    )

    prompts: dict[str, str] = Field(
        default={},
        init=False,
        title="System prompts",
        description="Dictionary containing map of system prompts",
    )

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
        """
        Get the loaded prompt mappings for the custom profile.

        Returns:
            dict[str, str]: Mapping from prompt names to prompt text.
        """
        return self.prompts


class Customization(ConfigurationBase):
    """Service customization."""

    profile_path: Optional[str] = None
    disable_query_system_prompt: bool = False
    disable_shield_ids_override: bool = False
    system_prompt_path: Optional[FilePath] = None
    system_prompt: Optional[str] = None
    agent_card_path: Optional[FilePath] = None
    agent_card_config: Optional[dict[str, Any]] = None
    custom_profile: Optional[CustomProfile] = Field(default=None, init=False)

    @model_validator(mode="after")
    def check_customization_model(self) -> Self:
        """
        Load and apply service customization sources to the model.

        If `profile_path` is set, constructs a CustomProfile from that path and
        assigns it to `custom_profile`.  Otherwise, if `system_prompt_path` is
        provided, validates the file and reads `system_prompt` from it.

        Returns:
            self: The model instance, potentially with `custom_profile` or
                  `system_prompt` populated.
        """
        if self.profile_path:
            self.custom_profile = CustomProfile(path=self.profile_path)
        elif self.system_prompt_path is not None:
            checks.file_check(self.system_prompt_path, "system prompt")
            self.system_prompt = checks.get_attribute_from_file(
                dict(self), "system_prompt_path"
            )

        # Load agent card configuration from YAML file
        if self.agent_card_path is not None:
            checks.file_check(self.agent_card_path, "agent card")

            try:
                with open(self.agent_card_path, "r", encoding="utf-8") as f:
                    self.agent_card_config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(
                    f"Invalid YAML in agent card file '{self.agent_card_path}': {e}"
                ) from e
            except OSError as e:
                raise ValueError(
                    f"Unable to read agent card file '{self.agent_card_path}': {e}"
                ) from e

        return self


class InferenceConfiguration(ConfigurationBase):
    """Inference configuration."""

    default_model: Optional[str] = Field(
        None,
        title="Default model",
        description="Identification of default model used when no other model is specified.",
    )

    default_provider: Optional[str] = Field(
        None,
        title="Default provider",
        description="Identification of default provider used when no other model is specified.",
    )

    @model_validator(mode="after")
    def check_default_model_and_provider(self) -> Self:
        """
        Validate that default_model and default_provider are configured together: both set or unset.

        Raises:
            ValueError: If one is set while the other is not.

        Returns:
            self (Self): The validated configuration instance.
        """
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

    type: Optional[Literal["noop", "memory", "sqlite", "postgres"]] = Field(
        None,
        title="Conversation history database type",
        description="Type of database where the conversation history is to be stored.",
    )

    memory: Optional[InMemoryCacheConfig] = Field(
        None,
        title="In-memory cache configuration",
        description="In-memory cache configuration",
    )

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
    def check_cache_configuration(self) -> Self:
        """
        Validate the conversation cache configuration and enforce the selected cache type backend.

        Raises:
            ValueError: If a backend is provided but `type` is None.
            ValueError: If `type` is "memory" but `memory` config is missing,
                        or if other backend configs are present.
            ValueError: If `type` is "sqlite" but `sqlite` config is missing,
                        or if other backend configs are present.
            ValueError: If `type` is "postgres" but `postgres` config is
                        missing, or if other backend configs are present.

        Returns:
            The validated model instance.
        """
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


class A2AStateConfiguration(ConfigurationBase):
    """A2A protocol persistent state configuration.

    Configures how A2A task state and context-to-conversation mappings are
    stored. For multi-worker deployments, use SQLite or PostgreSQL to ensure
    state is shared across all workers.

    If no configuration is provided, in-memory storage is used (default).
    This is suitable for single-worker deployments but state will be lost
    on restarts and not shared across workers.

    Attributes:
        sqlite: SQLite database configuration for A2A state storage.
        postgres: PostgreSQL database configuration for A2A state storage.
    """

    sqlite: Optional[SQLiteDatabaseConfiguration] = Field(
        default=None,
        title="SQLite configuration",
        description="SQLite database configuration for A2A state storage.",
    )
    postgres: Optional[PostgreSQLDatabaseConfiguration] = Field(
        default=None,
        title="PostgreSQL configuration",
        description="PostgreSQL database configuration for A2A state storage.",
    )

    @model_validator(mode="after")
    def check_a2a_state_configuration(self) -> Self:
        """Validate A2A state configuration - only one type can be configured."""
        total_configured = sum([self.sqlite is not None, self.postgres is not None])

        if total_configured > 1:
            raise ValueError("Only one A2A state storage configuration can be provided")

        return self

    @property
    def storage_type(self) -> Literal["memory", "sqlite", "postgres"]:
        """Return the configured storage type."""
        if self.sqlite is not None:
            return "sqlite"
        if self.postgres is not None:
            return "postgres"
        return "memory"

    @property
    def config(
        self,
    ) -> Optional[SQLiteDatabaseConfiguration | PostgreSQLDatabaseConfiguration]:
        """Return the active storage configuration, or None for memory storage."""
        if self.sqlite is not None:
            return self.sqlite
        if self.postgres is not None:
            return self.postgres
        return None


class ByokRag(ConfigurationBase):
    """BYOK (Bring Your Own Knowledge) RAG configuration."""

    rag_id: str = Field(
        ...,
        min_length=1,
        title="RAG ID",
        description="Unique RAG ID",
    )

    rag_type: str = Field(
        constants.DEFAULT_RAG_TYPE,
        min_length=1,
        title="RAG type",
        description="Type of RAG database.",
    )

    embedding_model: str = Field(
        constants.DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        title="Embedding model",
        description="Embedding model identification",
    )

    embedding_dimension: PositiveInt = Field(
        constants.DEFAULT_EMBEDDING_DIMENSION,
        title="Embedding dimension",
        description="Dimensionality of embedding vectors.",
    )

    vector_db_id: str = Field(
        ...,
        min_length=1,
        title="Vector DB ID",
        description="Vector database identification.",
    )

    db_path: FilePath = Field(
        ...,
        title="DB path",
        description="Path to RAG database.",
    )


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

    database_reconnection_count: PositiveInt = Field(
        10,
        title="Database reconnection count on startup",
        description="Database reconnection count on startup. When database for "
        "quota is not available on startup, the service tries to reconnect N "
        "times with specified delay.",
    )

    database_reconnection_delay: PositiveInt = Field(
        1,
        title="Database reconnection delay",
        description="Database reconnection delay specified in seconds. When database for "
        "quota is not available on startup, the service tries to reconnect N "
        "times with specified delay.",
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
        default_factory=lambda: QuotaSchedulerConfiguration(
            period=1, database_reconnection_count=10, database_reconnection_delay=1
        ),
        title="Quota scheduler",
        description="Quota scheduler configuration",
    )

    enable_token_history: bool = Field(
        False,
        title="Enable token history",
        description="Enables storing information about token usage history",
    )


class SolrConfiguration(ConfigurationBase):
    """Solr configuration for vector search queries.

    Controls whether to use offline or online mode when building document URLs
    from vector search results, and enables/disables Solr vector IO functionality.
    """

    enabled: bool = Field(
        False,
        title="Solr enabled",
        description="When True, enables Solr vector IO functionality for vector search queries. "
        "When False, disables Solr vector search processing.",
    )

    offline: bool = Field(
        True,
        title="Offline mode",
        description="When True, use parent_id for chunk source URLs. "
        "When False, use reference_url for chunk source URLs.",
    )


class AzureEntraIdConfiguration(ConfigurationBase):
    """Microsoft Entra ID authentication attributes for Azure."""

    tenant_id: SecretStr
    client_id: SecretStr
    client_secret: SecretStr
    scope: str = Field(
        "https://cognitiveservices.azure.com/.default",
        title="Token scope",
        description="Azure Cognitive Services scope for token requests. "
        "Override only if using a different Azure service.",
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
        default_factory=lambda: AuthenticationConfiguration(
            skip_for_health_probes=False
        ),
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
        default_factory=lambda: InferenceConfiguration(
            default_model=None, default_provider=None
        ),
        title="Inference configuration",
        description="One LLM provider and one its model might be selected as "
        "default ones. When no provider+model pair is specified in REST API "
        "calls (query endpoints), the default provider and model are used.",
    )

    conversation_cache: ConversationHistoryConfiguration = Field(
        default_factory=lambda: ConversationHistoryConfiguration(
            type=None, memory=None, sqlite=None, postgres=None
        ),
        title="Conversation history configuration",
        description="Conversation history configuration.",
    )

    byok_rag: list[ByokRag] = Field(
        default_factory=list,
        title="BYOK RAG configuration",
        description="BYOK RAG configuration. This configuration can be used to "
        "reconfigure Llama Stack through its run.yaml configuration file",
    )

    a2a_state: A2AStateConfiguration = Field(
        default_factory=A2AStateConfiguration,
        title="A2A state configuration",
        description="Configuration for A2A protocol persistent state storage.",
    )

    quota_handlers: QuotaHandlersConfiguration = Field(
        default_factory=lambda: QuotaHandlersConfiguration(
            sqlite=None, postgres=None, enable_token_history=False
        ),
        title="Quota handlers",
        description="Quota handlers configuration",
    )
    azure_entra_id: Optional[AzureEntraIdConfiguration] = None

    splunk: Optional[SplunkConfiguration] = Field(
        default=None,
        title="Splunk configuration",
        description="Splunk HEC configuration for sending telemetry events.",
    )

    deployment_environment: str = Field(
        "development",
        title="Deployment environment",
        description="Deployment environment name (e.g., 'development', 'staging', 'production'). "
        "Used in telemetry events.",
    )

    solr: Optional[SolrConfiguration] = Field(
        default=None,
        title="Solr configuration",
        description="Configuration for Solr vector search operations.",
    )

    @model_validator(mode="after")
    def validate_mcp_auth_headers(self) -> Self:
        """
        Validate MCP server authorization headers against authentication module.

        Removes any MCP server with authorization_headers="kubernetes" when the
        authentication module is not "k8s" or "noop-with-token". This prevents sending
        wrong credential types to MCP servers.

        Note: "noop-with-token" should only be used for testing/development purposes.
        When using "noop-with-token" with kubernetes authorization headers, a real
        Kubernetes token must still be passed in the request headers.

        Returns:
            Self: The model instance after validation.
        """
        # Get authentication module value (pyright: ignore attribute access on Field)
        auth_module = getattr(self.authentication, "module", None)

        # Filter out misconfigured MCP servers
        valid_mcp_servers = []
        for mcp_server in self.mcp_servers:
            is_valid = True
            if mcp_server.authorization_headers:
                for value in mcp_server.authorization_headers.values():
                    if (
                        value.strip() == constants.MCP_AUTH_KUBERNETES
                        and auth_module
                        not in [
                            constants.AUTH_MOD_K8S,
                            constants.AUTH_MOD_NOOP_WITH_TOKEN,
                        ]
                    ):
                        logger.warning(
                            "Removing MCP server '%s': has authorization_headers with "
                            "value '%s' but authentication module is '%s' "
                            "(not '%s' or '%s'). Either change authentication.module to "
                            "'%s' or '%s' or update the MCP server's authorization_headers "
                            "to use a file path or '%s'.",
                            mcp_server.name,
                            constants.MCP_AUTH_KUBERNETES,
                            auth_module,
                            constants.AUTH_MOD_K8S,
                            constants.AUTH_MOD_NOOP_WITH_TOKEN,
                            constants.AUTH_MOD_K8S,
                            constants.AUTH_MOD_NOOP_WITH_TOKEN,
                            constants.MCP_AUTH_CLIENT,
                        )
                        is_valid = False
                        break
            if is_valid:
                valid_mcp_servers.append(mcp_server)

        self.mcp_servers = valid_mcp_servers
        return self

    def dump(self, filename: str | Path = "configuration.json") -> None:
        """
        Write the current Configuration model to a JSON file.

        The configuration is serialized with an indentation of 4 spaces using
        the model's JSON representation and written with UTF-8 encoding. If the
        file exists it will be overwritten.

        Parameters:
            filename (str | Path): Path to the output file (defaults to "configuration.json").
        """
        with open(filename, "w", encoding="utf-8") as fout:
            fout.write(self.model_dump_json(indent=4))
