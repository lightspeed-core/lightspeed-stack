"""Unit tests for the /info REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from llama_stack_client.types import VersionInfo
from pytest_mock import MockerFixture

from app.endpoints.info import info_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_info_endpoint(mocker: MockerFixture) -> None:
    """Test the info endpoint handler."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[Any, Any] = {
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
    mock_client.inspect.version.return_value = VersionInfo(version="0.1.2")
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    # Mock configuration
    mocker.patch("configuration.configuration", cfg)

    mock_authorization_resolvers(mocker)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await info_endpoint_handler(auth=auth, request=request)
    assert response is not None
    assert response.name is not None
    assert response.service_version is not None
    assert response.llama_stack_version == "0.1.2"


@pytest.mark.asyncio
async def test_info_endpoint_connection_error(mocker: MockerFixture) -> None:
    """Test the info endpoint handler.

    Verify that info_endpoint_handler raises an HTTPException with
    status 503 when the LlamaStack client cannot connect.

    Sets up application configuration and patches the LlamaStack
    client so that calling its version inspection raises an
    APIConnectionError, then asserts the raised HTTPException has
    status code 503 and a detail payload containing a "response" of
    "Service unavailable" and a "cause" that includes "Unable to
    connect to Llama Stack".
    """
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[Any, Any] = {
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
    mock_client.inspect.version.side_effect = APIConnectionError(request=None)  # type: ignore
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    # Mock configuration
    mocker.patch("configuration.configuration", cfg)

    mock_authorization_resolvers(mocker)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await info_endpoint_handler(auth=auth, request=request)
        assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert e.value.detail["response"] == "Service unavailable"  # type: ignore
        assert "Unable to connect to Llama Stack" in e.value.detail["cause"]  # type: ignore
