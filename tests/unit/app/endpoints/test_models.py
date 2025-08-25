"""Unit tests for the /models REST API endpoint."""

import pytest

from fastapi import HTTPException, Request, status

from llama_stack_client import APIConnectionError

from app.endpoints.models import models_endpoint_handler
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_models_endpoint_handler_configuration_not_loaded(mocker):
    """Test the models endpoint handler if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.models.configuration",
        return_value=mocker.Mock(),
    )
    mocker.patch("app.endpoints.models.configuration", None)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth = ("user_id", "user_name", "token")

    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Configuration is not loaded"


@pytest.mark.asyncio
async def test_models_endpoint_handler_improper_llama_stack_configuration(mocker):
    """Test the models endpoint handler if Llama Stack configuration is not proper."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict = {
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

    mocker.patch(
        "app.endpoints.models.configuration",
        return_value=None,
    )

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth = ("test_user", "token", {})
    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "LLama stack is not configured"


@pytest.mark.asyncio
async def test_models_endpoint_handler_configuration_loaded(mocker):
    """Test the models endpoint handler if configuration is loaded."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict = {
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

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth = ("test_user", "token", {})

    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Unable to connect to Llama Stack"


@pytest.mark.asyncio
async def test_models_endpoint_handler_unable_to_retrieve_models_list(mocker):
    """Test the models endpoint handler if configuration is loaded."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict = {
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
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth = ("test_user", "token", {})
    response = await models_endpoint_handler(request=request, auth=auth)
    assert response is not None


@pytest.mark.asyncio
async def test_models_endpoint_llama_stack_connection_error(mocker):
    """Test the model endpoint when LlamaStack connection fails."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict = {
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
    mock_client.models.list.side_effect = APIConnectionError(request=None)
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
    auth = ("test_user", "token", {})

    with pytest.raises(HTTPException) as e:
        await models_endpoint_handler(request=request, auth=auth)
        assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Unable to connect to Llama Stack"
