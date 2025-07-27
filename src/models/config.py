"""Model with service configuration."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, model_validator, FilePath, AnyHttpUrl, PositiveInt
from typing_extensions import Self

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


class DatabaseConfiguration(BaseModel):
    """Database configuration for persistent storage."""

    host: str = "localhost"
    port: int = 5432
    name: str = "lightspeed_stack"
    username: str = "postgres"
    password: Optional[str] = None
    ssl_mode: str = "prefer"
    pool_size: int = 20
    max_overflow: int = 30
    pool_timeout: int = 30
    pool_recycle: int = 3600

    @model_validator(mode="after")
    def check_database_configuration(self) -> Self:
        """Check database configuration."""
        if self.port <= 0 or self.port > 65535:
            raise ValueError("Port value should be between 1 and 65535")
        if self.pool_size < 1:
            raise ValueError("Pool size must be at least 1")
        if self.max_overflow < 0:
            raise ValueError("Max overflow must be non-negative")
        return self


class PersistenceConfiguration(BaseModel):
    """Persistence configuration for conversation and agent state."""

    type: str = "postgresql"  # postgresql, mongodb, firestore
    database: Optional[DatabaseConfiguration] = None
    agent_cache_max_size: int = 1000
    agent_cache_ttl_seconds: int = 3600
    enable_rehydration: bool = True
    conversation_retention_days: int = 90
    enable_archival: bool = False
    archival_storage: Optional[str] = None

    @model_validator(mode="after")
    def check_persistence_configuration(self) -> Self:
        """Check persistence configuration."""
        if self.type not in ["postgresql", "mongodb", "firestore"]:
            raise ValueError(
                f"Unsupported persistence type '{self.type}'. "
                "Supported types: postgresql, mongodb, firestore"
            )
        
        if self.type == "postgresql" and self.database is None:
            raise ValueError("Database configuration is required for PostgreSQL persistence")
        
        if self.agent_cache_max_size < 1:
            raise ValueError("Agent cache max size must be at least 1")
        
        if self.agent_cache_ttl_seconds < 1:
            raise ValueError("Agent cache TTL must be at least 1 second")
        
        if self.conversation_retention_days < 1:
            raise ValueError("Conversation retention days must be at least 1")
        
        return self


class ServiceConfiguration(BaseModel):
    """Service configuration."""

    host: str = "localhost"
    port: int = 8080
    auth_enabled: bool = False
    workers: int = 1
    color_log: bool = True
    access_log: bool = True
    tls_config: TLSConfiguration = TLSConfiguration()

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
                    "LLama stack library client mode is enabled but a configuration file path is not specified"  # noqa: C0301
                )
            # the configuration file must exists and be regular readable file
            checks.file_check(
                Path(self.library_client_config_path), "Llama Stack configuration file"
            )
        return self


class DataCollectorConfiguration(BaseModel):
    """Data collector configuration for sending data to ingress server."""

    enabled: bool = False
    ingress_server_url: Optional[str] = None
    ingress_server_auth_token: Optional[str] = None
    ingress_content_service_name: Optional[str] = None
    collection_interval: PositiveInt = constants.DATA_COLLECTOR_COLLECTION_INTERVAL
    cleanup_after_send: bool = True  # Remove local files after successful send
    connection_timeout: PositiveInt = constants.DATA_COLLECTOR_CONNECTION_TIMEOUT

    @model_validator(mode="after")
    def check_data_collector_configuration(self) -> Self:
        """Check data collector configuration."""
        if self.enabled:
            if self.ingress_server_url is None:
                raise ValueError(
                    "Ingress server URL must be specified when data collector is enabled"
                )
            if self.ingress_content_service_name is None:
                raise ValueError(
                    "Ingress content service name must be specified when data collector is enabled"
                )
        return self


class UserDataCollection(BaseModel):
    """User data collection configuration."""

    feedback_enabled: bool = False
    feedback_storage: Optional[str] = None
    transcripts_enabled: bool = False
    transcripts_storage: Optional[str] = None
    data_collector: DataCollectorConfiguration = DataCollectorConfiguration()

    @model_validator(mode="after")
    def check_storage_location_is_set_when_needed(self) -> Self:
        """Check storage location is set when needed."""
        if self.feedback_enabled and self.feedback_storage is None:
            raise ValueError(
                "Feedback storage location must be specified when feedback is enabled"
            )
        if self.transcripts_enabled and self.transcripts_storage is None:
            raise ValueError(
                "Transcripts storage location must be specified when transcripts are enabled"
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
    mcp_servers: list[ModelContextProtocolServer] = []
    authentication: Optional[AuthenticationConfiguration] = (
        AuthenticationConfiguration()
    )
    customization: Optional[Customization] = None
    inference: Optional[InferenceConfiguration] = InferenceConfiguration()
    persistence: Optional[PersistenceConfiguration] = None

    def dump(self, filename: str = "configuration.json") -> None:
        """Dump actual configuration into JSON file."""
        with open(filename, "w", encoding="utf-8") as fout:
            fout.write(self.model_dump_json(indent=4))
