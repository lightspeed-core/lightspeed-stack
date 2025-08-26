"""Unit tests for the /info REST API endpoint."""

import pytest
from fastapi import Request

from app.endpoints.info import info_endpoint_handler
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_info_endpoint(mocker):
    """Test the info endpoint handler."""
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

    # Mock configuration
    mocker.patch("configuration.configuration", cfg)

    mock_authorization_resolvers(mocker)

    request = Request(
        scope={
            "type": "http",
        }
    )
    auth = ("test_user", "token", {})
    response = await info_endpoint_handler(auth=auth, request=request)
    assert response is not None
    assert response.name is not None
    assert response.version is not None
