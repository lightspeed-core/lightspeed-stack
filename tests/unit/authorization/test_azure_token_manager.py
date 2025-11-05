"""Unit test for Authentication with Azure Entra ID Credentials."""

# pylint: disable=protected-access

import time
import pytest
from pytest_mock import MockerFixture
from azure.core.credentials import AccessToken
from pydantic import SecretStr

from authorization.azure_token_manager import (
    AzureEntraIDTokenManager,
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
    )


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton instance before each test."""
    AzureEntraIDTokenManager._instances = {}


@pytest.fixture(name="token_manager")
def token_manager_fixture() -> AzureEntraIDTokenManager:
    """Return a fresh AzureEntraIDTokenManager instance."""
    return AzureEntraIDTokenManager()


class TestAzureEntraIDTokenManager:
    """Unit tests for AzureEntraIDTokenManager."""

    def test_singleton_behavior(self, token_manager):
        """Verify the singleton returns the same instance."""
        manager2 = AzureEntraIDTokenManager()
        assert token_manager is manager2

    def test_initial_state(self, token_manager):
        """Check the initial token manager state."""
        assert token_manager.access_token == ""
        assert token_manager.is_token_expired
        assert not token_manager.is_entra_id_configured

    def test_set_config(self, token_manager, dummy_config):
        """Set the Azure configuration on the token manager."""
        token_manager.set_config(dummy_config)
        assert token_manager.is_entra_id_configured

    def test_token_expiration_logic(self, token_manager):
        """Verify token expiration logic works correctly."""
        token_manager._expires_on = int(time.time()) + 100
        assert not token_manager.is_token_expired

        token_manager._expires_on = 0
        assert token_manager.is_token_expired

    @pytest.mark.asyncio
    async def test_refresh_token_raises_without_config(self, token_manager):
        """Raise ValueError when refresh_token is called without config."""
        with pytest.raises(ValueError, match="Azure configuration is not set"):
            token_manager.refresh_token()

    def test_update_access_token_sets_token_and_expiration(self, token_manager):
        """Update the token and its expiration in the token manager."""
        expires_on = int(time.time()) + 3600
        token_manager._update_access_token("test-token", expires_on)
        assert token_manager.access_token == "test-token"
        assert token_manager._expires_on == expires_on - TOKEN_EXPIRATION_LEEWAY

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self, token_manager, dummy_config, mocker: MockerFixture
    ):
        """Refresh the token successfully using the Azure credential mock."""
        token_manager.set_config(dummy_config)
        dummy_access_token = AccessToken("token_value", int(time.time()) + 3600)

        mock_credential_instance = mocker.Mock()
        mock_credential_instance.get_token.return_value = dummy_access_token

        mocker.patch(
            "authorization.azure_token_manager.ClientSecretCredential",
            return_value=mock_credential_instance,
        )

        token_manager.refresh_token()

        assert token_manager.access_token == "token_value"
        assert not token_manager.is_token_expired
        mock_credential_instance.get_token.assert_called_once_with(
            "https://cognitiveservices.azure.com/.default"
        )

    @pytest.mark.asyncio
    async def test_refresh_token_failure_raises_runtime_error(
        self, token_manager, dummy_config, mocker: MockerFixture, caplog
    ):
        """Raise RuntimeError when token retrieval fails."""
        token_manager.set_config(dummy_config)
        mock_credential_instance = mocker.Mock()
        mock_credential_instance.get_token.side_effect = Exception("fail")
        mocker.patch(
            "authorization.azure_token_manager.ClientSecretCredential",
            return_value=mock_credential_instance,
        )

        with caplog.at_level("ERROR"):
            with pytest.raises(
                RuntimeError, match="Failed to retrieve Azure access token"
            ):
                token_manager.refresh_token()
            assert "Error retrieving access token" in caplog.text

    def test_token_expired_property_dynamic(self, token_manager, mocker: MockerFixture):
        """Simulate time passage to test token expiration property."""
        now = 1000000
        token_manager._expires_on = now + 10

        mocker.patch("authorization.azure_token_manager.time.time", return_value=now)
        assert not token_manager.is_token_expired

        mocker.patch(
            "authorization.azure_token_manager.time.time", return_value=now + 20
        )
        assert token_manager.is_token_expired
