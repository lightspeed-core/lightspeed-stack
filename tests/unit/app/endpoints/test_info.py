"""Unit tests for the /info REST API endpoint."""

from app.endpoints.info import info_endpoint_handler
from configuration import AppConfig


def test_info_endpoint():
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
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    request = None
    response = info_endpoint_handler(request)
    assert response is not None
    assert response.name is not None
    assert response.version is not None
