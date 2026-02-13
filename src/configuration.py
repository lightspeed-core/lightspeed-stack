"""Configuration loader."""

import logging
from typing import Any, Optional

# We want to support environment variable replacement in the configuration
# similarly to how it is done in llama-stack, so we use their function directly
from llama_stack.core.stack import replace_env_vars

import yaml
from models.config import (
    A2AStateConfiguration,
    AuthorizationConfiguration,
    AzureEntraIdConfiguration,
    Configuration,
    Customization,
    LlamaStackConfiguration,
    UserDataCollection,
    ServiceConfiguration,
    ModelContextProtocolServer,
    AuthenticationConfiguration,
    InferenceConfiguration,
    DatabaseConfiguration,
    ConversationHistoryConfiguration,
    QuotaHandlersConfiguration,
    SolrConfiguration,
    SplunkConfiguration,
)

from cache.cache import Cache
from cache.cache_factory import CacheFactory

from quota.quota_limiter import QuotaLimiter
from quota.token_usage_history import TokenUsageHistory
from quota.quota_limiter_factory import QuotaLimiterFactory

logger = logging.getLogger(__name__)


class LogicError(Exception):
    """Error in application logic."""


class AppConfig:  # pylint: disable=too-many-public-methods
    """Singleton class to load and store the configuration."""

    _instance = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "AppConfig":
        """Create a new instance of the class."""
        if not isinstance(cls._instance, cls):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the class instance.

        Sets placeholders for the loaded configuration and lazily-created
        runtime resources (conversation cache, quota limiters, and token usage
        history).
        """
        self._configuration: Optional[Configuration] = None
        self._conversation_cache: Optional[Cache] = None
        self._quota_limiters: list[QuotaLimiter] = []
        self._token_usage_history: Optional[TokenUsageHistory] = None

    def load_configuration(self, filename: str) -> None:
        """Load configuration from YAML file.

        Parameters:
            filename (str): Path to the YAML configuration file to load.
        """
        with open(filename, encoding="utf-8") as fin:
            config_dict = yaml.safe_load(fin)
            config_dict = replace_env_vars(config_dict)
            self.init_from_dict(config_dict)

    def init_from_dict(self, config_dict: dict[Any, Any]) -> None:
        """Initialize configuration from a dictionary.

        Parameters:
            config_dict (dict[Any, Any]): Mapping of configuration values
            (typically parsed from YAML) to construct a new Configuration
            instance. The method sets the internal configuration to
            Configuration(**config_dict) and clears any cached conversation
            cache, quota limiters, and token usage history so they will be
            reinitialized on next access.
        """
        # clear cached values when configuration changes
        self._conversation_cache = None
        self._quota_limiters = []
        self._token_usage_history = None
        # now it is possible to re-read configuration
        self._configuration = Configuration(**config_dict)

    @property
    def configuration(self) -> Configuration:
        """Return the whole configuration.

        Returns:
            Configuration: The loaded configuration object.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration

    @property
    def service_configuration(self) -> ServiceConfiguration:
        """Return service configuration.

        Returns:
            ServiceConfiguration: The service configuration stored in the current configuration.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.service

    @property
    def llama_stack_configuration(self) -> LlamaStackConfiguration:
        """Return Llama stack configuration.

        Returns:
            LlamaStackConfiguration: The configured Llama stack settings.

        Raises:
            LogicError: If the application configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.llama_stack

    @property
    def user_data_collection_configuration(self) -> UserDataCollection:
        """Return user data collection configuration.

        Returns:
            UserDataCollection: The configured UserDataCollection object from
            the loaded configuration.

        Raises:
            LogicError: If the application configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.user_data_collection

    @property
    def mcp_servers(self) -> list[ModelContextProtocolServer]:
        """Return model context protocol servers configuration.

        Returns:
            list[ModelContextProtocolServer]: The list of configured MCP servers.

        Raises:
            LogicError: If the configuration is not loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.mcp_servers

    @property
    def authentication_configuration(self) -> AuthenticationConfiguration:
        """Return authentication configuration.

        Returns:
            AuthenticationConfiguration: The authentication configuration from
            the loaded application configuration.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")

        return self._configuration.authentication

    @property
    def authorization_configuration(self) -> AuthorizationConfiguration:
        """Return authorization configuration or default no-op configuration.

        Returns:
            AuthorizationConfiguration: The configured authorization settings,
            or a default no-op AuthorizationConfiguration when none is
            configured.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")

        if self._configuration.authorization is None:
            return AuthorizationConfiguration()

        return self._configuration.authorization

    @property
    def customization(self) -> Optional[Customization]:
        """Return customization configuration.

        Returns:
            customization (Optional[Customization]): The customization
            configuration if present, otherwise None.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.customization

    @property
    def inference(self) -> InferenceConfiguration:
        """Return inference configuration.

        Returns:
            InferenceConfiguration: The inference configuration from the loaded
            application configuration.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.inference

    @property
    def conversation_cache_configuration(self) -> ConversationHistoryConfiguration:
        """Return conversation cache configuration.

        Returns:
            ConversationHistoryConfiguration: The conversation cache
            configuration from the loaded application configuration.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.conversation_cache

    @property
    def database_configuration(self) -> DatabaseConfiguration:
        """Return database configuration.

        Returns:
            DatabaseConfiguration: The configured database settings.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.database

    @property
    def quota_handlers_configuration(self) -> QuotaHandlersConfiguration:
        """Return quota handlers configuration.

        Returns:
            quota_handlers (QuotaHandlersConfiguration): The configured quota handlers.

        Raises:
            LogicError: If configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.quota_handlers

    @property
    def a2a_state(self) -> "A2AStateConfiguration":
        """Return A2A state configuration."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.a2a_state

    @property
    def conversation_cache(self) -> Cache:
        """Return the conversation cache.

        Returns:
            Cache: The conversation cache instance configured by the loaded configuration.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        if self._conversation_cache is None:
            self._conversation_cache = CacheFactory.conversation_cache(
                self._configuration.conversation_cache
            )
        return self._conversation_cache

    @property
    def quota_limiters(self) -> list[QuotaLimiter]:
        """Return list of all setup quota limiters.

        Returns:
            list[QuotaLimiter]: The quota limiter instances configured for the application.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        if not self._quota_limiters:
            self._quota_limiters = QuotaLimiterFactory.quota_limiters(
                self._configuration.quota_handlers
            )
        return self._quota_limiters

    @property
    def token_usage_history(self) -> Optional[TokenUsageHistory]:
        """
        Provide the token usage history object for the application.

        If token history is enabled in the loaded quota handlers configuration,
        creates and caches a TokenUsageHistory instance and returns it. If
        token history is disabled, returns None.

        Returns:
            Optional[TokenUsageHistory]: The cached TokenUsageHistory instance
            when enabled, otherwise `None`.

        Raises:
            LogicError: If the configuration has not been loaded.
        """
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        if (
            self._token_usage_history is None
            and self._configuration.quota_handlers.enable_token_history  # pylint: disable=no-member
        ):
            self._token_usage_history = TokenUsageHistory(
                self._configuration.quota_handlers
            )
        return self._token_usage_history

    @property
    def azure_entra_id(self) -> Optional[AzureEntraIdConfiguration]:
        """Return Azure Entra ID configuration, or None if not provided."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.azure_entra_id

    @property
    def splunk(self) -> Optional[SplunkConfiguration]:
        """Return Splunk configuration, or None if not provided."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.splunk

    @property
    def deployment_environment(self) -> str:
        """Return deployment environment name."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.deployment_environment

    @property
    def solr(self) -> Optional[SolrConfiguration]:
        """Return Solr configuration, or None if not provided."""
        if self._configuration is None:
            raise LogicError("logic error: configuration is not loaded")
        return self._configuration.solr


configuration: AppConfig = AppConfig()
