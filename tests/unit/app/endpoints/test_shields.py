"""Unit tests for the /shields REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.shields import shields_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.responses import ShieldsResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_shields_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    # simulate state when no configuration is loaded
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.shields.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await shields_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_shields_endpoint_handler_improper_llama_stack_configuration(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if Llama Stack configuration is not proper."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mocker.patch("app.endpoints.shields.configuration", cfg)
    # Mock client to avoid initialization
    mock_client_holder = mocker.patch(
        "app.endpoints.shields.AsyncLlamaStackClientHolder"
    )
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    # Mock shields.list to return empty list
    mock_client.shields.list.return_value = []

    response = await shields_endpoint_handler(request=request, auth=auth)
    assert isinstance(response, ShieldsResponse)
    assert response.shields == []


@pytest.mark.asyncio
async def test_shields_endpoint_handler_configuration_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if configuration is loaded."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mocker.patch("app.endpoints.shields.configuration", cfg)
    # Mock client to raise APIConnectionError
    mock_client_holder = mocker.patch(
        "app.endpoints.shields.AsyncLlamaStackClientHolder"
    )
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_client_holder.return_value.get_client.return_value = mock_client

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await shields_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert e.value.detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_shields_endpoint_handler_unable_to_retrieve_shields_list(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if configuration is loaded."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.shields.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await shields_endpoint_handler(request=request, auth=auth)
    assert response is not None


@pytest.mark.asyncio
async def test_shields_endpoint_llama_stack_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint when LlamaStack connection fails."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }

    # mock AsyncLlamaStackClientHolder to raise APIConnectionError
    # when shields.list() method is called
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_client_holder = mocker.patch(
        "app.endpoints.shields.AsyncLlamaStackClientHolder"
    )
    mock_client_holder.return_value.get_client.return_value = mock_client

    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await shields_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert e.value.detail["response"] == "Service unavailable"  # type: ignore
        assert "Unable to connect to Llama Stack" in e.value.detail["cause"]  # type: ignore


@pytest.mark.asyncio
async def test_shields_endpoint_handler_success_with_shields_data(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler with successful response and shields data."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock the LlamaStack client with sample shields data
    mock_shields_data = [
        {
            "identifier": "lightspeed_question_validity-shield",
            "provider_resource_id": "lightspeed_question_validity-shield",
            "provider_id": "lightspeed_question_validity",
            "type": "shield",
            "params": {},
        },
        {
            "identifier": "content_filter-shield",
            "provider_resource_id": "content_filter-shield",
            "provider_id": "content_filter",
            "type": "shield",
            "params": {"threshold": 0.8},
        },
    ]

    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = mock_shields_data
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.shields.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await shields_endpoint_handler(request=request, auth=auth)

    assert response is not None
    assert hasattr(response, "shields")
    assert len(response.shields) == 2
    assert response.shields[0]["identifier"] == "lightspeed_question_validity-shield"
    assert response.shields[1]["identifier"] == "content_filter-shield"
