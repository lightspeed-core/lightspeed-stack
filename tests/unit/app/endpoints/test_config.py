import pytest

from app.endpoints.config import config_endpoint_handler
from configuration import AppConfig


def test_config_endpoint_handler_configuration_not_loaded(mocker):
    """Test the config endpoint handler."""
    mocker.patch("app.endpoints.config.configuration", None)

    request = None
    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        config_endpoint_handler(request)  # type: ignore


def test_config_endpoint_handler_configuration_loaded(mocker):
    """Test the config endpoint handler."""
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
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    request = None
    response = config_endpoint_handler(request)  # type: ignore
    assert response is not None
    assert response == cfg.configuration
