"""Model with service configuration."""

from typing import Optional

from pydantic import BaseModel, model_validator, FilePath

from typing_extensions import Self


class TLSConfiguration(BaseModel):
    """TLS configuration."""

    tls_certificate_path: Optional[FilePath] = None
    tls_key_path: Optional[FilePath] = None
    tls_key_password: Optional[FilePath] = None

    @model_validator(mode="after")
    def check_tls_configuration(self) -> Self:
        """Check TLS configuration."""
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


class LLamaStackConfiguration(BaseModel):
    """Llama stack configuration."""

    url: Optional[str] = None
    api_key: Optional[str] = None
    use_as_library_client: Optional[bool] = None
    library_client_config_path: Optional[str] = None

    @model_validator(mode="after")
    def check_llama_stack_model(self) -> Self:
        """Check Llama stack configuration."""
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
        return self


class DataCollectorConfiguration(BaseModel):
    """Data collector configuration for sending data to ingress server."""
    
    enabled: bool = False
    ingress_server_url: Optional[str] = None
    ingress_server_auth_token: Optional[str] = None
    collection_interval: int = 2 * 60 * 60  # 2 hours
    cleanup_after_send: bool = True  # Remove local files after successful send
    connection_timeout_seconds: int = 30
    
    @model_validator(mode="after")
    def check_archival_configuration(self) -> Self:
        """Check data archival configuration."""
        if self.enabled and self.ingress_server_url is None:
            raise ValueError("ingress_server_url is required when data archival is enabled")
        if self.collection_interval <= 0:
            raise ValueError("collection_interval must be positive")
        return self


class UserDataCollection(BaseModel):
    """User data collection configuration."""

    feedback_disabled: bool = True
    feedback_storage: Optional[str] = None
    transcripts_disabled: bool = True
    transcripts_storage: Optional[str] = None
    data_collector: DataCollectorConfiguration = DataCollectorConfiguration()

    @model_validator(mode="after")
    def check_storage_location_is_set_when_needed(self) -> Self:
        """Check that storage_location is set when enabled."""
        if not self.feedback_disabled and self.feedback_storage is None:
            raise ValueError("feedback_storage is required when feedback is enabled")
        if not self.transcripts_disabled and self.transcripts_storage is None:
            raise ValueError(
                "transcripts_storage is required when transcripts is enabled"
            )
        return self


class Configuration(BaseModel):
    """Global service configuration."""

    name: str
    service: ServiceConfiguration
    llama_stack: LLamaStackConfiguration
    user_data_collection: UserDataCollection
    mcp_servers: list[ModelContextProtocolServer] = []

    def dump(self, filename: str = "configuration.json") -> None:
        """Dump actual configuration into JSON file."""
        with open(filename, "w", encoding="utf-8") as fout:
            fout.write(self.model_dump_json(indent=4))
