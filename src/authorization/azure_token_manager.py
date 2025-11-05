"""Authentication module for Azure Entra ID Credentials."""

import logging
import time
from typing import Optional

from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential
from utils.types import Singleton
from configuration import AzureEntraIdConfiguration

logger = logging.getLogger(__name__)

TOKEN_EXPIRATION_LEEWAY = 30  # seconds


class AzureEntraIDTokenManager(metaclass=Singleton):
    """Microsoft Token cache for Azure OpenAI provider.

    Manages and caches Microsoft Entra ID access tokens for the Azure OpenAI provider.
    Handles token storage, expiration checks, and refreshing tokens when an Entra ID
    configuration is provided. Designed for temporary tokens passed via request headers.
    """

    def __init__(self) -> None:
        """Construct Azure token manager."""
        self._access_token: Optional[str] = None
        self._expires_on: int = 0
        self._entra_id_config = None

    def set_config(self, azure_config: AzureEntraIdConfiguration) -> None:
        """Set the Azure Entra ID configuration."""
        self._entra_id_config = azure_config

    @property
    def is_entra_id_configured(self) -> bool:
        """Check whether an Entra ID configuration has been set."""
        return self._entra_id_config is not None

    @property
    def is_token_expired(self) -> bool:
        """Check if the current token has expired (observer only)."""
        return self._expires_on == 0 or time.time() > self._expires_on

    @property
    def access_token(self) -> str:
        """Return the currently cached access token (no refresh logic)."""
        if not self._access_token:
            logger.debug("Access token requested but not yet available.")
        return self._access_token or ""

    def refresh_token(self) -> None:
        """Refresh and cache a new Azure access token if configuration is set."""
        if self._entra_id_config is None:
            raise ValueError("Azure configuration is not set for token retrieval")

        logger.info("Refreshing Azure access token...")
        token_obj = self._retrieve_access_token()
        if token_obj:
            self._update_access_token(token_obj.token, token_obj.expires_on)
            logger.info("Azure access token successfully refreshed.")
        else:
            raise RuntimeError("Failed to retrieve Azure access token")

    def _update_access_token(self, token: str, expires_on: int) -> None:
        """Update token and expiration time (private helper)."""
        self._access_token = token
        self._expires_on = expires_on - TOKEN_EXPIRATION_LEEWAY
        logger.info(
            "Access token updated; expires at %s",
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._expires_on)),
        )

    def _retrieve_access_token(self) -> Optional[AccessToken]:
        """Retrieve access token to call Azure OpenAI."""
        if not self._entra_id_config:
            return None
        tenant_id = self._entra_id_config.tenant_id.get_secret_value()
        client_id = self._entra_id_config.client_id.get_secret_value()
        client_secret = self._entra_id_config.client_secret.get_secret_value()

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            return token
        except ClientAuthenticationError as e:
            logger.error("Error retrieving access token: %s", e, exc_info=True)
            return None
