"""Unit tests for the /models REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.models import models_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_models_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the models endpoint handler if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    # simulate state when no configuration is loaded
    mock_config = AppConfig()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_models_endpoint_handler_configuration_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the models endpoint handler if configuration is loaded.

    Verify the models endpoint raises HTTP 503 when configuration is loaded but
    the Llama Stack client cannot connect.

    Loads an AppConfig from a test dictionary, patches the endpoint's
    configuration and AsyncLlamaStackClientHolder so that get_client raises
    APIConnectionError, issues a request with an authorization header, and
    asserts that calling the handler raises an HTTPException with status 503
    and a detail response of "Unable to connect to Llama Stack".
    """
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

    mocker.patch("app.endpoints.models.configuration", cfg)
    mock_client_holder = mocker.patch(
        "app.endpoints.models.AsyncLlamaStackClientHolder"
    )
    mock_client_holder.return_value.get_client.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert e.value.detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_models_endpoint_handler_unable_to_retrieve_models_list(
    mocker: MockerFixture,
) -> None:
    """Test the models endpoint handler if configuration is loaded."""
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
    mock_client.models.list.return_value = []
    mock_lsc = mocker.patch(
        "app.endpoints.models.AsyncLlamaStackClientHolder.get_client"
    )
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await models_endpoint_handler(request=request, auth=auth)
    assert response is not None


@pytest.mark.asyncio
async def test_models_endpoint_llama_stack_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test the model endpoint when LlamaStack connection fails."""
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
    # when models.list() method is called
    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_client_holder = mocker.patch(
        "app.endpoints.models.AsyncLlamaStackClientHolder"
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
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert e.value.detail["response"] == "Unable to connect to Llama Stack"  # type: ignore
        assert "Unable to connect to Llama Stack" in e.value.detail["cause"]  # type: ignore
