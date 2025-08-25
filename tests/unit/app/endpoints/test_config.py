"""Unit tests for the /config REST API endpoint."""

import pytest

from fastapi import HTTPException, Request, status
from app.endpoints.config import config_endpoint_handler
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_config_endpoint_handler_configuration_not_loaded(mocker):
    """Test the config endpoint handler."""
    mock_authorization_resolvers(mocker)

    mocker.patch(
        "app.endpoints.config.configuration._configuration",
        new=None,
    )
    mocker.patch("app.endpoints.config.configuration", None)

    request = Request(
        scope={
            "type": "http",
        }
    )
    auth = ("test_user", "token", {})
    with pytest.raises(HTTPException) as exc_info:
        await config_endpoint_handler(auth=auth, request=request)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["response"] == "Configuration is not loaded"


@pytest.mark.asyncio
async def test_config_endpoint_handler_configuration_loaded(mocker):
    """Test the config endpoint handler."""
    mock_authorization_resolvers(mocker)

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
        "authentication": {
            "module": "noop",
        },
        "authorization": {"access_rules": []},
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock configuration
    mocker.patch("app.endpoints.config.configuration", cfg)

    request = Request(
        scope={
            "type": "http",
        }
    )
    auth = ("test_user", "token", {})
    response = await config_endpoint_handler(auth=auth, request=request)
    assert response is not None
    assert response == cfg.configuration
