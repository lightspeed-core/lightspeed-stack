"""Unit tests for the /health REST API endpoint."""

from typing import Any

import pytest
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.health import (
    HealthStatus,
    check_default_model_available,
    get_providers_health_statuses,
    liveness_probe_get_method,
    readiness_probe_get_method,
)
from authentication.interface import AuthTuple
from models.responses import ProviderHealthStatus, ReadinessResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_readiness_probe_fails_due_to_unhealthy_providers(
    mocker: MockerFixture,
) -> None:
    """Test the readiness endpoint handler fails when providers are unhealthy."""
    mock_authorization_resolvers(mocker)

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

    # Mock the Response object and auth
    mock_response = mocker.Mock()

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await readiness_probe_get_method(auth=auth, response=mock_response)

    assert response.ready is False
    assert "test_provider" in response.reason
    assert "Providers not healthy" in response.reason
    assert mock_response.status_code == 503


@pytest.mark.asyncio
async def test_readiness_probe_success_when_all_providers_healthy(
    mocker: MockerFixture,
) -> None:
    """Test the readiness endpoint handler succeeds when all providers are healthy."""
    mock_authorization_resolvers(mocker)

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

    # Mock check_default_model_available so it doesn't hit uninitialized client
    mock_check_model = mocker.patch(
        "app.endpoints.health.check_default_model_available"
    )
    mock_check_model.return_value = (True, "Default model is available")

    # Mock the Response object and auth
    mock_response = mocker.Mock()

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await readiness_probe_get_method(auth=auth, response=mock_response)
    assert response is not None
    assert isinstance(response, ReadinessResponse)
    assert response.ready is True
    assert response.reason == "All providers are healthy"
    # Should return empty list since no providers are unhealthy
    assert len(response.providers) == 0


@pytest.mark.asyncio
async def test_readiness_probe_fails_when_model_not_available(
    mocker: MockerFixture,
) -> None:
    """Test readiness returns 503 when providers are healthy but default model is missing."""
    mock_authorization_resolvers(mocker)

    mock_get_providers = mocker.patch(
        "app.endpoints.health.get_providers_health_statuses"
    )
    mock_get_providers.return_value = [
        ProviderHealthStatus(
            provider_id="provider1",
            status=HealthStatus.OK.value,
            message="Provider is healthy",
        )
    ]

    mock_check_model = mocker.patch(
        "app.endpoints.health.check_default_model_available"
    )
    mock_check_model.return_value = (
        False,
        "Default model google-vertex/publishers/google/models/gemini-2.5-flash "
        "not found in model registry",
    )

    mock_response = mocker.Mock()
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await readiness_probe_get_method(auth=auth, response=mock_response)

    assert response.ready is False
    assert "not found in model registry" in response.reason
    assert mock_response.status_code == 503


@pytest.mark.asyncio
async def test_liveness_probe(mocker: MockerFixture) -> None:
    """Test the liveness endpoint handler."""
    mock_authorization_resolvers(mocker)

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await liveness_probe_get_method(auth=auth)
    assert response is not None
    assert response.alive is True


class TestProviderHealthStatus:
    """Test cases for the ProviderHealthStatus model."""

    def test_provider_health_status_creation(self) -> None:
        """Test creating a ProviderHealthStatus instance."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message="All good"
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message == "All good"

    def test_provider_health_status_optional_fields(self) -> None:
        """Test creating a ProviderHealthStatus with minimal fields."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message=None
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message is None


class TestGetProvidersHealthStatuses:
    """Test cases for the get_providers_health_statuses function."""

    @pytest.mark.asyncio
    async def test_get_providers_health_statuses(self, mocker: MockerFixture) -> None:
        """Test get_providers_health_statuses with healthy providers.

        Verify get_providers_health_statuses returns a ProviderHealthStatus
        entry for each provider reported by the client.

        Mocks an AsyncLlamaStack client whose providers.list() returns three
        providers with distinct health dicts, then asserts the function
        produces three results with:
        - provider1: status OK, message "All good"
        - provider2: status NOT_IMPLEMENTED, message "Provider does not implement health check"
        - unhealthy_provider: status ERROR, message "Connection failed"
        """
        # Mock the imports
        mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")

        # Mock the client and its methods
        mock_client = mocker.AsyncMock()
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
        result = await get_providers_health_statuses()

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

    @pytest.mark.asyncio
    async def test_get_providers_health_statuses_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_providers_health_statuses when connection fails."""
        # Mock the imports
        mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")

        # Mock get_llama_stack_client to raise an exception
        mock_lsc.side_effect = APIConnectionError(request=mocker.Mock())

        result = await get_providers_health_statuses()

        assert len(result) == 1
        assert result[0].provider_id == "unknown"
        assert result[0].status == HealthStatus.ERROR.value
        assert (
            result[0].message == "Failed to initialize health check: Connection error."
        )


class TestCheckDefaultModelAvailable:
    """Test cases for the check_default_model_available function.

    The model availability logic (registry lookup, reload, error handling)
    is tested in tests/unit/test_client.py (TestCheckModelAvailable). These
    tests verify only the config lookup and delegation in health.py.
    """

    EXPECTED_MODEL_ID = "google-vertex/publishers/google/models/gemini-2.5-flash"

    @pytest.fixture
    def inference_config(self, mocker: MockerFixture) -> Any:
        """Patch configuration with default model and provider."""
        mock_config = mocker.patch("app.endpoints.health.configuration")
        mock_config.inference.default_model = (
            "publishers/google/models/gemini-2.5-flash"
        )
        mock_config.inference.default_provider = "google-vertex"
        return mock_config

    @pytest.mark.asyncio
    async def test_no_inference_config(self, mocker: MockerFixture) -> None:
        """Test returns True when no inference configuration exists."""
        mock_config = mocker.patch("app.endpoints.health.configuration")
        mock_config.inference = None

        available, reason = await check_default_model_available()

        assert available is True
        assert reason == "No default model configured"

    @pytest.mark.asyncio
    async def test_no_default_model_configured(self, mocker: MockerFixture) -> None:
        """Test returns True when no default model is configured."""
        mock_config = mocker.patch("app.endpoints.health.configuration")
        mock_config.inference.default_model = None
        mock_config.inference.default_provider = None

        available, reason = await check_default_model_available()

        assert available is True
        assert reason == "No default model configured"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("inference_config")
    async def test_delegates_to_client_holder(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test delegates to client holder with correct model ID."""
        mock_holder = mocker.patch("app.endpoints.health.AsyncLlamaStackClientHolder")
        mock_holder.return_value.check_model_available = mocker.AsyncMock(
            return_value=(True, f"Model {self.EXPECTED_MODEL_ID} is available")
        )

        available, reason = await check_default_model_available()

        assert available is True
        assert "is available" in reason
        mock_holder.return_value.check_model_available.assert_awaited_once_with(
            self.EXPECTED_MODEL_ID
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("inference_config")
    async def test_returns_holder_failure(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test passes through failure result from client holder."""
        mock_holder = mocker.patch("app.endpoints.health.AsyncLlamaStackClientHolder")
        mock_holder.return_value.check_model_available = mocker.AsyncMock(
            return_value=(
                False,
                f"Model {self.EXPECTED_MODEL_ID} not found in model registry",
            )
        )

        available, reason = await check_default_model_available()

        assert available is False
        assert "not found in model registry" in reason
