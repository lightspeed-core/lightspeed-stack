"""Configuration loader."""

import logging
from typing import Any, Optional

# We want to support environment variable replacement in the configuration
# similarly to how it is done in llama-stack, so we use their function directly
from llama_stack.core.stack import replace_env_vars

import yaml
from models.config import (
    AuthorizationConfiguration,
    Configuration,
    Customization,
    LlamaStackConfiguration,
    UserDataCollection,
    ServiceConfiguration,
    ModelContextProtocolServer,
    AuthenticationConfiguration,
    InferenceConfiguration,
    DatabaseConfiguration,
    ConversationCacheConfiguration,
)


logger = logging.getLogger(__name__)


class LogicError(Exception):
    """Error in application logic."""


class AppConfig:
    """Singleton class to load and store the configuration."""

    _instance = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "AppConfig":
        """Create a new instance of the class."""
        if not isinstance(cls._instance, cls):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the class instance."""
        self._configuration: Optional[Configuration] = None

    def load_configuration(self, filename: str) -> None:
        """Load configuration from YAML file."""
        with open(filename, encoding="utf-8") as fin:
            config_dict = yaml.safe_load(fin)
            config_dict = replace_env_vars(config_dict)
            logger.info("Loaded configuration: %s", config_dict)
            self.init_from_dict(config_dict)

    def init_from_dict(self, config_dict: dict[Any, Any]) -> None:
        """Initialize configuration from a dictionary."""
        self._configuration = Configuration(**config_dict)

    @property
    def configuration(self) -> Configuration:
        """Return the whole configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration

    @property
    def service_configuration(self) -> ServiceConfiguration:
        """Return service configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.service

    @property
    def llama_stack_configuration(self) -> LlamaStackConfiguration:
        """Return Llama stack configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.llama_stack

    @property
    def user_data_collection_configuration(self) -> UserDataCollection:
        """Return user data collection configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.user_data_collection

    @property
    def mcp_servers(self) -> list[ModelContextProtocolServer]:
        """Return model context protocol servers configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.mcp_servers

    @property
    def authentication_configuration(self) -> AuthenticationConfiguration:
        """Return authentication configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")

        return self._configuration.authentication

    @property
    def authorization_configuration(self) -> AuthorizationConfiguration:
        """Return authorization configuration or default no-op configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")

        if self._configuration.authorization is None:
            return AuthorizationConfiguration()

        return self._configuration.authorization

    @property
    def customization(self) -> Optional[Customization]:
        """Return customization configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.customization

    @property
    def inference(self) -> InferenceConfiguration:
        """Return inference configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.inference

    @property
    def conversation_cache_configuration(self) -> ConversationCacheConfiguration:
        """Return conversation cache configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.conversation_cache

    @property
    def database_configuration(self) -> DatabaseConfiguration:
        """Return database configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.database


configuration: AppConfig = AppConfig()
