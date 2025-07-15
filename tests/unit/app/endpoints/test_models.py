import pytest

from unittest.mock import Mock
from fastapi import HTTPException, status

from app.endpoints.models import models_endpoint_handler
from configuration import AppConfig


def test_models_endpoint_handler_configuration_not_loaded(mocker):
    """Test the models endpoint handler if configuration is not loaded."""
    # simulate state when no configuration is loaded
    mocker.patch(
        "app.endpoints.models.configuration",
        return_value=mocker.Mock(),
    )
    mocker.patch("app.endpoints.models.configuration", None)

    request = None
    with pytest.raises(HTTPException) as e:
        models_endpoint_handler(request)
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Configuration is not loaded"


def test_models_endpoint_handler_improper_llama_stack_configuration(mocker):
    """Test the models endpoint handler if Llama Stack configuration is not proper."""
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
            "transcripts_disabled": True,
        },
        "mcp_servers": [],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    mocker.patch(
        "app.endpoints.models.configuration",
        return_value=None,
    )

    request = None
    with pytest.raises(HTTPException) as e:
        models_endpoint_handler(request)
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "LLama stack is not configured"


def test_models_endpoint_handler_configuration_loaded(mocker):
    """Test the models endpoint handler if configuration is loaded."""
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
            "feedback_disabled": True,
        },
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    with pytest.raises(HTTPException) as e:
        request = None
        models_endpoint_handler(request)
        assert e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert e.detail["response"] == "Unable to connect to Llama Stack"


def test_models_endpoint_handler_unable_to_retrieve_models_list(mocker):
    """Test the models endpoint handler if configuration is loaded."""
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
            "feedback_disabled": True,
        },
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock the LlamaStack client
    mock_client = Mock()
    mock_client.models.list.return_value = []
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    request = None
    response = models_endpoint_handler(request)
    assert response is not None
