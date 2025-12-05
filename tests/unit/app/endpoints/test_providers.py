"""Unit tests for the /providers REST API endpoints."""

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError, BadRequestError
from llama_stack_client.types import ProviderInfo
from pytest_mock import MockerFixture

from app.endpoints.providers import (
    get_provider_endpoint_handler,
    providers_endpoint_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_providers_endpoint_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test that /providers endpoint raises HTTP 500 if configuration is not loaded."""
    mock_authorization_resolvers(mocker)
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.providers.configuration", mock_config)
    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await providers_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_providers_endpoint_connection_error(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /providers endpoint raises HTTP 503 if Llama Stack connection fails."""
    mocker.patch("app.endpoints.providers.configuration", minimal_config)

    mocker.patch(
        "app.endpoints.providers.AsyncLlamaStackClientHolder"
    ).return_value.get_client.side_effect = APIConnectionError(request=mocker.Mock())

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await providers_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_providers_endpoint_success(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /providers endpoint returns a grouped list of providers on success."""
    mocker.patch("app.endpoints.providers.configuration", minimal_config)

    provider_list = [
        ProviderInfo(
            api="inference",
            provider_id="openai",
            provider_type="remote::openai",
            config={},
            health={},
        ),
        ProviderInfo(
            api="inference",
            provider_id="st",
            provider_type="inline::sentence-transformers",
            config={},
            health={},
        ),
        ProviderInfo(
            api="datasetio",
            provider_id="huggingface",
            provider_type="remote::huggingface",
            config={},
            health={},
        ),
    ]
    mock_client = mocker.AsyncMock()
    mock_client.providers.list.return_value = provider_list
    mocker.patch(
        "app.endpoints.providers.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await providers_endpoint_handler(request=request, auth=auth)
    assert "inference" in response.providers
    assert len(response.providers["inference"]) == 2
    assert "datasetio" in response.providers


@pytest.mark.asyncio
async def test_get_provider_not_found(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /providers/{provider_id} endpoint raises HTTP 404 if the provider is not found."""
    mocker.patch("app.endpoints.providers.configuration", minimal_config)

    # Mock AsyncLlamaStackClientHolder to return a client that raises BadRequestError
    mock_client_holder = mocker.patch(
        "app.endpoints.providers.AsyncLlamaStackClientHolder"
    )
    mock_client = mocker.AsyncMock()
    mock_client.providers.retrieve = mocker.AsyncMock(
        side_effect=BadRequestError(
            message="Provider not found",
            response=mocker.Mock(request=None),
            body=None,
        )
    )  # type: ignore
    mock_client_holder.return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await get_provider_endpoint_handler(
            request=request, provider_id="openai", auth=auth
        )
    assert e.value.status_code == status.HTTP_404_NOT_FOUND
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert "not found" in detail["response"]  # type: ignore
    assert "Provider with ID openai does not exist" in detail["cause"]  # type: ignore


@pytest.mark.asyncio
async def test_get_provider_success(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /providers/{provider_id} endpoint returns provider details on success."""
    mocker.patch("app.endpoints.providers.configuration", minimal_config)

    provider = ProviderInfo(
        api="inference",
        provider_id="openai",
        provider_type="remote::openai",
        config={"api_key": "*****"},
        health={"status": "OK", "message": "Healthy"},
    )
    mock_client = mocker.AsyncMock()
    mock_client.providers.retrieve = mocker.AsyncMock(return_value=provider)
    mocker.patch(
        "app.endpoints.providers.AsyncLlamaStackClientHolder"
    ).return_value.get_client.return_value = mock_client

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await get_provider_endpoint_handler(
        request=request, provider_id="openai", auth=auth
    )
    assert response.provider_id == "openai"
    assert response.api == "inference"


@pytest.mark.asyncio
async def test_get_provider_connection_error(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test that /providers/{provider_id} raises HTTP 500 if Llama Stack connection fails."""
    mocker.patch("app.endpoints.providers.configuration", minimal_config)
    mock_authorization_resolvers(mocker)

    mocker.patch(
        "app.endpoints.providers.AsyncLlamaStackClientHolder"
    ).return_value.get_client.side_effect = APIConnectionError(request=mocker.Mock())

    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await get_provider_endpoint_handler(
            request=request, provider_id="openai", auth=auth
        )
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = e.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore
