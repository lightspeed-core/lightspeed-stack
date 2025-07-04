"""Configuration loader."""

import logging
from typing import Any, Optional

import yaml
from models.config import (
    Configuration,
    LLamaStackConfiguration,
    UserDataCollection,
    ServiceConfiguration,
    ModelContextProtocolServer,
    AuthenticationConfiguration,
)

logger = logging.getLogger(__name__)


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
            logger.info("Loaded configuration: %s", config_dict)
            self.init_from_dict(config_dict)

    def init_from_dict(self, config_dict: dict[Any, Any]) -> None:
        """Initialize configuration from a dictionary."""
        self._configuration = Configuration(**config_dict)

    @property
    def configuration(self) -> Configuration:
        """Return the whole configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration

    @property
    def service_configuration(self) -> ServiceConfiguration:
        """Return service configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration.service

    @property
    def llama_stack_configuration(self) -> LLamaStackConfiguration:
        """Return Llama stack configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration.llama_stack

    @property
    def user_data_collection_configuration(self) -> UserDataCollection:
        """Return user data collection configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration.user_data_collection

    @property
    def mcp_servers(self) -> list[ModelContextProtocolServer]:
        """Return model context protocol servers configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration.mcp_servers

    @property
    def authentication_configuration(self) -> Optional[AuthenticationConfiguration]:
        """Return authentication configuration."""
        assert (
            self._configuration is not None
        ), "logic error: configuration is not loaded"
        return self._configuration.authentication


configuration: AppConfig = AppConfig()
