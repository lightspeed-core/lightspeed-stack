"""Handler for REST API call to retrieve service configuration."""

import logging
from typing import Any

from fastapi import APIRouter, Request

from models.config import Configuration
from configuration import configuration
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


get_config_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "name": "foo bar baz",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": "config/certificate.crt",
                "tls_key_path": "config/private.key",
                "tls_key_password": None,
            },
        },
        "llama_stack": {
            "url": "http://localhost:8321",
            "api_key": "xyzzy",
            "use_as_library_client": False,
            "library_client_config_path": None,
        },
        "user_data_collection": {
            "feedback_disabled": False,
            "feedback_storage": "/tmp/data/feedback",
            "transcripts_disabled": True,
            "transcripts_storage": None,
        },
        "mcp_servers": [
            {"name": "server1", "provider_id": "provider1", "url": "http://url.com:1"},
            {"name": "server2", "provider_id": "provider2", "url": "http://url.com:2"},
            {"name": "server3", "provider_id": "provider3", "url": "http://url.com:3"},
        ],
    },
    503: {
        "detail": {
            "response": "Configuration is no loaded",
        }
    },
}


@router.get("/config", responses=get_config_responses)
def config_endpoint_handler(_request: Request) -> Configuration:
    """Handle requests to the /config endpoint."""
    # ensure that configuration is loaded
    check_configuration_loaded(configuration)

    return configuration.configuration
