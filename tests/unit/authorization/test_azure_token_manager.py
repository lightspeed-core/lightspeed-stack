"""Unit test for Authentication with Azure Entra ID Credentials."""

# pylint: disable=protected-access

import logging
import time
from typing import Any, Generator

import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from pydantic import SecretStr
from pytest_mock import MockerFixture

from authorization import azure_token_manager
from authorization.azure_token_manager import (
    AzureEntraIDManager,
    TOKEN_EXPIRATION_LEEWAY,
)
from configuration import AzureEntraIdConfiguration


@pytest.fixture(name="dummy_config")
def dummy_config_fixture() -> AzureEntraIdConfiguration:
    """Return a dummy AzureEntraIdConfiguration for testing."""
    return AzureEntraIdConfiguration(
        tenant_id=SecretStr("tenant"),
        client_id=SecretStr("client"),
        client_secret=SecretStr("secret"),
        scope="https://cognitiveservices.azure.com/.default",
    )


@pytest.fixture(autouse=True)
def reset_singleton() -> Generator[None, None, None]:
    """Reset the singleton instance before each test."""
    AzureEntraIDManager._instances = {}  # type: ignore[attr-defined]
    yield


@pytest.fixture(name="token_manager")
def token_manager_fixture() -> AzureEntraIDManager:
    """Return a fresh AzureEntraIDTokenManager instance."""
    return AzureEntraIDManager()


class TestAzureEntraIDTokenManager:
    """Unit tests for AzureEntraIDTokenManager."""

    def test_singleton_behavior(self, token_manager: AzureEntraIDManager) -> None:
        """Verify the singleton returns the same instance."""
        manager2 = AzureEntraIDManager()
        assert token_manager is manager2

    def test_initial_state(
        self, token_manager: AzureEntraIDManager, mocker: MockerFixture
    ) -> None:
        """Check the initial token manager state."""
        mocker.patch.dict("os.environ", {"AZURE_API_KEY": ""}, clear=False)
        assert token_manager.access_token.get_secret_value() == ""
        assert token_manager.is_token_expired
        assert not token_manager.is_entra_id_configured

    def test_set_config(
        self,
        token_manager: AzureEntraIDManager,
        dummy_config: AzureEntraIdConfiguration,
    ) -> None:
        """Set the Azure configuration on the token manager."""
        token_manager.set_config(dummy_config)
        assert token_manager.is_entra_id_configured

    def test_token_expiration_logic(self, token_manager: AzureEntraIDManager) -> None:
        """Verify token expiration logic works correctly."""
        token_manager._expires_on = int(time.time()) + 100
        assert not token_manager.is_token_expired

        token_manager._expires_on = 0
        assert token_manager.is_token_expired

    def test_refresh_token_raises_without_config(
        self, token_manager: AzureEntraIDManager
    ) -> None:
        """Raise ValueError when refresh_token is called without config."""
        with pytest.raises(ValueError, match="Azure Entra ID configuration not set"):
            token_manager.refresh_token()

    def test_update_access_token_sets_token_and_expiration(
        self, token_manager: AzureEntraIDManager
    ) -> None:
        """Update the token and its expiration in the token manager."""
        expires_on = int(time.time()) + 3600
        token_manager._update_access_token("test-token", expires_on)
        assert token_manager.access_token.get_secret_value() == "test-token"
        assert token_manager._expires_on == expires_on - TOKEN_EXPIRATION_LEEWAY

    def test_refresh_token_success(
        self,
        token_manager: AzureEntraIDManager,
        dummy_config: AzureEntraIdConfiguration,
        mocker: MockerFixture,
    ) -> None:
        """Refresh the token successfully using the Azure credential mock."""
        token_manager.set_config(dummy_config)
        dummy_access_token = AccessToken("token_value", int(time.time()) + 3600)

        mock_credential_instance = mocker.Mock()
        mock_credential_instance.get_token.return_value = dummy_access_token

        mocker.patch(
            "authorization.azure_token_manager.ClientSecretCredential",
            return_value=mock_credential_instance,
        )

        result = token_manager.refresh_token()

        assert result is True
        assert token_manager.access_token.get_secret_value() == "token_value"
        assert not token_manager.is_token_expired
        mock_credential_instance.get_token.assert_called_once_with(dummy_config.scope)

    def test_refresh_token_failure_logs_error(
        self,
        token_manager: AzureEntraIDManager,
        dummy_config: AzureEntraIdConfiguration,
        mocker: MockerFixture,
        caplog: Any,
    ) -> None:
        """Log error when token retrieval fails due to ClientAuthenticationError."""
        token_manager.set_config(dummy_config)
        mock_credential_instance = mocker.Mock()
        mock_credential_instance.get_token.side_effect = ClientAuthenticationError(
            "fail"
        )
        mocker.patch(
            "authorization.azure_token_manager.ClientSecretCredential",
            return_value=mock_credential_instance,
        )

        azure_logger = logging.getLogger(azure_token_manager.__name__)
        azure_logger.propagate = True
        try:
            with caplog.at_level("WARNING"):
                result = token_manager.refresh_token()
                assert result is False
                assert "Failed to retrieve Azure access token" in caplog.text
        finally:
            azure_logger.propagate = False

    def test_token_expired_property_dynamic(
        self, token_manager: AzureEntraIDManager, mocker: MockerFixture
    ) -> None:
        """Simulate time passage to test token expiration property."""
        now = 1000000
        token_manager._expires_on = now + 10

        mocker.patch("authorization.azure_token_manager.time.time", return_value=now)
        assert not token_manager.is_token_expired

        mocker.patch(
            "authorization.azure_token_manager.time.time", return_value=now + 20
        )
        assert token_manager.is_token_expired
