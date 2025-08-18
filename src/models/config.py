"""Model with service configuration."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, model_validator, FilePath, AnyHttpUrl
from typing_extensions import Self, Literal

import constants

from utils import checks


class TLSConfiguration(BaseModel):
    """TLS configuration."""

    tls_certificate_path: Optional[FilePath] = None
    tls_key_path: Optional[FilePath] = None
    tls_key_password: Optional[FilePath] = None

    @model_validator(mode="after")
    def check_tls_configuration(self) -> Self:
        """Check TLS configuration."""
        return self


class CORSConfiguration(BaseModel):
    """CORS configuration."""

    allow_origins: list[str] = [
        "*"
    ]  # not AnyHttpUrl: we need to support "*" that is not valid URL
    allow_credentials: bool = False
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]

    @model_validator(mode="after")
    def check_cors_configuration(self) -> Self:
        """Check CORS configuration."""
        # credentials are not allowed with wildcard origins per CORS/Fetch spec.
        # see https://fastapi.tiangolo.com/tutorial/cors/
        if self.allow_credentials and "*" in self.allow_origins:
            raise ValueError(
                "Invalid CORS configuration: allow_credentials can not be set to true when "
                "allow origins contains '*' wildcard."
                "Use explicit origins or disable credential."
            )
        return self


class SQLiteDatabaseConfiguration(BaseModel):
    """SQLite database configuration."""

    db_path: str


class PostgreSQLDatabaseConfiguration(BaseModel):
    """PostgreSQL database configuration."""

    host: str = "localhost"
    port: int = 5432
    db: str
    user: str
    password: str
    namespace: Optional[str] = "lightspeed-stack"
    ssl_mode: str = constants.POSTGRES_DEFAULT_SSL_MODE
    gss_encmode: str = constants.POSTGRES_DEFAULT_GSS_ENCMODE
    ca_cert_path: Optional[FilePath] = None

    @model_validator(mode="after")
    def check_postgres_configuration(self) -> Self:
        """Check PostgreSQL configuration."""
        if self.port <= 0:
            raise ValueError("Port value should not be negative")
        if self.port > 65535:
            raise ValueError("Port value should be less than 65536")
        if self.ca_cert_path is not None and not self.ca_cert_path.exists():
            raise ValueError(f"CA certificate file does not exist: {self.ca_cert_path}")
        return self


class DatabaseConfiguration(BaseModel):
    """Database configuration."""

    sqlite: Optional[SQLiteDatabaseConfiguration] = None
    postgres: Optional[PostgreSQLDatabaseConfiguration] = None

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


class ServiceConfiguration(BaseModel):
    """Service configuration."""

    host: str = "localhost"
    port: int = 8080
    auth_enabled: bool = False
    workers: int = 1
    color_log: bool = True
    access_log: bool = True
    tls_config: TLSConfiguration = TLSConfiguration()
    cors: CORSConfiguration = CORSConfiguration()

    @model_validator(mode="after")
    def check_service_configuration(self) -> Self:
        """Check service configuration."""
        if self.port <= 0:
            raise ValueError("Port value should not be negative")
        if self.port > 65535:
            raise ValueError("Port value should be less than 65536")
        if self.workers < 1:
            raise ValueError("Workers must be set to at least 1")
        return self


class ModelContextProtocolServer(BaseModel):
    """model context protocol server configuration."""

    name: str
    provider_id: str = "model-context-protocol"
    url: str


class LlamaStackConfiguration(BaseModel):
    """Llama stack configuration."""

    url: Optional[str] = None
    api_key: Optional[str] = None
    use_as_library_client: Optional[bool] = None
    library_client_config_path: Optional[str] = None

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
            if self.use_as_library_client is None:
                raise ValueError(
                    "LLama stack URL is not specified and library client mode is not specified"
                )
            if self.use_as_library_client is False:
                raise ValueError(
                    "LLama stack URL is not specified and library client mode is not enabled"
                )
        if self.use_as_library_client is None:
            self.use_as_library_client = False
        if self.use_as_library_client:
            if self.library_client_config_path is None:
                # pylint: disable=line-too-long
                raise ValueError(
                    "LLama stack library client mode is enabled but a configuration file path is not specified"  # noqa: E501
                )
            # the configuration file must exists and be regular readable file
            checks.file_check(
                Path(self.library_client_config_path), "Llama Stack configuration file"
            )
        return self


class UserDataCollection(BaseModel):
    """User data collection configuration."""

    feedback_enabled: bool = False
    feedback_storage: Optional[str] = None
    transcripts_enabled: bool = False
    transcripts_storage: Optional[str] = None

    @model_validator(mode="after")
    def check_storage_location_is_set_when_needed(self) -> Self:
        """Check that storage_location is set when enabled."""
        if self.feedback_enabled and self.feedback_storage is None:
            raise ValueError("feedback_storage is required when feedback is enabled")
        if self.transcripts_enabled and self.transcripts_storage is None:
            raise ValueError(
                "transcripts_storage is required when transcripts is enabled"
            )
        return self


class JwtConfiguration(BaseModel):
    """JWT configuration."""

    user_id_claim: str = constants.DEFAULT_JWT_UID_CLAIM
    username_claim: str = constants.DEFAULT_JWT_USER_NAME_CLAIM


class JwkConfiguration(BaseModel):
    """JWK configuration."""

    url: AnyHttpUrl
    jwt_configuration: JwtConfiguration = JwtConfiguration()


class AuthenticationConfiguration(BaseModel):
    """Authentication configuration."""

    module: str = constants.DEFAULT_AUTHENTICATION_MODULE
    skip_tls_verification: bool = False
    k8s_cluster_api: Optional[AnyHttpUrl] = None
    k8s_ca_cert_path: Optional[FilePath] = None
    jwk_config: Optional[JwkConfiguration] = None

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

        return self

    @property
    def jwk_configuration(self) -> JwkConfiguration:
        """Return JWK configuration if the module is JWK token."""
        if self.module != constants.AUTH_MOD_JWK_TOKEN:
            raise ValueError(
                "JWK configuration is only available for JWK token authentication module"
            )
        assert self.jwk_config is not None, "JWK configuration should not be None"
        return self.jwk_config


class Customization(BaseModel):
    """Service customization."""

    disable_query_system_prompt: bool = False
    system_prompt_path: Optional[FilePath] = None
    system_prompt: Optional[str] = None

    @model_validator(mode="after")
    def check_customization_model(self) -> Self:
        """Load system prompt from file."""
        if self.system_prompt_path is not None:
            checks.file_check(self.system_prompt_path, "system prompt")
            self.system_prompt = checks.get_attribute_from_file(
                dict(self), "system_prompt_path"
            )
        return self


class InferenceConfiguration(BaseModel):
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


class Configuration(BaseModel):
    """Global service configuration."""

    name: str
    service: ServiceConfiguration
    llama_stack: LlamaStackConfiguration
    user_data_collection: UserDataCollection
    database: DatabaseConfiguration = DatabaseConfiguration()
    mcp_servers: list[ModelContextProtocolServer] = []
    authentication: AuthenticationConfiguration = AuthenticationConfiguration()
    customization: Optional[Customization] = None
    inference: InferenceConfiguration = InferenceConfiguration()

    def dump(self, filename: str = "configuration.json") -> None:
        """Dump actual configuration into JSON file."""
        with open(filename, "w", encoding="utf-8") as fout:
            fout.write(self.model_dump_json(indent=4))
