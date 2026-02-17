"""Azure Entra ID token manager for Azure OpenAI authentication."""

import os
import time
from typing import Optional

from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, CredentialUnavailableError
from pydantic import SecretStr

from configuration import AzureEntraIdConfiguration
from utils.types import Singleton
from log import get_logger

logger = get_logger(__name__)

# Refresh token before actual expiration to avoid edge cases
TOKEN_EXPIRATION_LEEWAY = 30  # seconds


class AzureEntraIDManager(metaclass=Singleton):
    """Manages Azure Entra ID access tokens for Azure OpenAI provider.

    This singleton class handles:
    - Token caching and expiration tracking
    - Token refresh using client credentials flow
    - Configuration management for Entra ID authentication

    The access token is passed via request headers to authenticate
    with Azure OpenAI services.
    """

    def __init__(self) -> None:
        """Initialize the token manager with empty state."""
        self._expires_on: int = 0
        self._entra_id_config: Optional[AzureEntraIdConfiguration] = None

    def set_config(self, azure_config: AzureEntraIdConfiguration) -> None:
        """Set the Azure Entra ID configuration."""
        self._entra_id_config = azure_config
        logger.debug("Azure Entra ID configuration set")

    @property
    def is_entra_id_configured(self) -> bool:
        """Check if Entra ID configuration has been set."""
        return self._entra_id_config is not None

    @property
    def is_token_expired(self) -> bool:
        """Check if the cached token has expired or is not available."""
        return self._expires_on == 0 or time.time() > self._expires_on

    @property
    def access_token(self) -> SecretStr:
        """Return the access token from environment variable as SecretStr."""
        return SecretStr(os.environ.get("AZURE_API_KEY", ""))

    def refresh_token(self) -> bool:
        """Refresh the cached Azure access token.

        Returns:
            bool: True if token was successfully refreshed, False otherwise.

        Raises:
            ValueError: If Entra ID configuration has not been set.
        """
        if self._entra_id_config is None:
            raise ValueError("Azure Entra ID configuration not set")

        logger.info("Refreshing Azure access token")
        token_obj = self._retrieve_access_token()
        if token_obj:
            self._update_access_token(token_obj.token, token_obj.expires_on)
            return True
        return False

    def _update_access_token(self, token: str, expires_on: int) -> None:
        """Update the token in env var and track expiration time."""
        self._expires_on = expires_on - TOKEN_EXPIRATION_LEEWAY
        os.environ["AZURE_API_KEY"] = token
        expiry_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self._expires_on)
        )
        logger.info("Azure access token refreshed, expires at %s", expiry_time)

    def _retrieve_access_token(self) -> Optional[AccessToken]:
        """Retrieve a new access token from Azure."""
        if not self._entra_id_config:
            return None

        try:
            credential = ClientSecretCredential(
                tenant_id=self._entra_id_config.tenant_id.get_secret_value(),
                client_id=self._entra_id_config.client_id.get_secret_value(),
                client_secret=self._entra_id_config.client_secret.get_secret_value(),
            )
            return credential.get_token(self._entra_id_config.scope)

        except (ClientAuthenticationError, CredentialUnavailableError):
            logger.warning("Failed to retrieve Azure access token")
            return None
