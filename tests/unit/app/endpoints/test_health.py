"""Unit tests for the /health REST API endpoint."""

from unittest.mock import Mock

from llama_stack.providers.datatypes import HealthStatus

from app.endpoints.health import (
    readiness_probe_get_method,
    liveness_probe_get_method,
    get_providers_health_statuses,
)
from models.responses import ProviderHealthStatus, ReadinessResponse


def test_readiness_probe_fails_due_to_unhealthy_providers(mocker):
    """Test the readiness endpoint handler fails when providers are unhealthy."""
    # Mock get_providers_health_statuses to return an unhealthy provider
    mock_get_providers_health_statuses = mocker.patch(
        "app.endpoints.health.get_providers_health_statuses"
    )
    mock_get_providers_health_statuses.return_value = [
        ProviderHealthStatus(
            provider_id="test_provider",
            status=HealthStatus.ERROR.value,
            message="Provider is down",
        )
    ]

    # Mock the Response object
    mock_response = Mock()

    response = readiness_probe_get_method(mock_response)

    assert response.ready is False
    assert "test_provider" in response.reason
    assert "Providers not healthy" in response.reason
    assert mock_response.status_code == 503


def test_readiness_probe_success_when_all_providers_healthy(mocker):
    """Test the readiness endpoint handler succeeds when all providers are healthy."""
    # Mock get_providers_health_statuses to return healthy providers
    mock_get_providers_health_statuses = mocker.patch(
        "app.endpoints.health.get_providers_health_statuses"
    )
    mock_get_providers_health_statuses.return_value = [
        ProviderHealthStatus(
            provider_id="provider1",
            status=HealthStatus.OK.value,
            message="Provider is healthy",
        ),
        ProviderHealthStatus(
            provider_id="provider2",
            status=HealthStatus.NOT_IMPLEMENTED.value,
            message="Provider does not implement health check",
        ),
    ]

    # Mock the Response object
    mock_response = Mock()

    response = readiness_probe_get_method(mock_response)
    assert response is not None
    assert isinstance(response, ReadinessResponse)
    assert response.ready is True
    assert response.reason == "All providers are healthy"
    # Should return empty list since no providers are unhealthy
    assert len(response.providers) == 0


def test_liveness_probe():
    """Test the liveness endpoint handler."""
    response = liveness_probe_get_method()
    assert response is not None
    assert response.alive is True


class TestProviderHealthStatus:
    """Test cases for the ProviderHealthStatus model."""

    def test_provider_health_status_creation(self):
        """Test creating a ProviderHealthStatus instance."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message="All good"
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message == "All good"

    def test_provider_health_status_optional_fields(self):
        """Test creating a ProviderHealthStatus with minimal fields."""
        status = ProviderHealthStatus(provider_id="test_provider", status="ok")
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message is None


class TestGetProvidersHealthStatuses:
    """Test cases for the get_providers_health_statuses function."""

    def test_get_providers_health_statuses(self, mocker):
        """Test get_providers_health_statuses with healthy providers."""
        # Mock the imports
        mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")

        # Mock the client and its methods
        mock_client = mocker.Mock()
        mock_lsc.return_value = mock_client

        # Mock providers.list() to return providers with health
        mock_provider_1 = mocker.Mock()
        mock_provider_1.provider_id = "provider1"
        mock_provider_1.health = {
            "status": HealthStatus.OK.value,
            "message": "All good",
        }

        mock_provider_2 = mocker.Mock()
        mock_provider_2.provider_id = "provider2"
        mock_provider_2.health = {
            "status": HealthStatus.NOT_IMPLEMENTED.value,
            "message": "Provider does not implement health check",
        }

        mock_provider_3 = mocker.Mock()
        mock_provider_3.provider_id = "unhealthy_provider"
        mock_provider_3.health = {
            "status": HealthStatus.ERROR.value,
            "message": "Connection failed",
        }

        mock_client.providers.list.return_value = [
            mock_provider_1,
            mock_provider_2,
            mock_provider_3,
        ]

        # Mock configuration
        result = get_providers_health_statuses()

        assert len(result) == 3
        assert result[0].provider_id == "provider1"
        assert result[0].status == HealthStatus.OK.value
        assert result[0].message == "All good"
        assert result[1].provider_id == "provider2"
        assert result[1].status == HealthStatus.NOT_IMPLEMENTED.value
        assert result[1].message == "Provider does not implement health check"
        assert result[2].provider_id == "unhealthy_provider"
        assert result[2].status == HealthStatus.ERROR.value
        assert result[2].message == "Connection failed"

    def test_get_providers_health_statuses_connection_error(self, mocker):
        """Test get_providers_health_statuses when connection fails."""
        # Mock the imports
        mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")

        # Mock get_llama_stack_client to raise an exception
        mock_lsc.side_effect = Exception("Connection error")

        result = get_providers_health_statuses()

        assert len(result) == 1
        assert result[0].provider_id == "unknown"
        assert result[0].status == HealthStatus.ERROR.value
        assert (
            result[0].message == "Failed to initialize health check: Connection error"
        )
