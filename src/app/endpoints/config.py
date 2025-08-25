"""Handler for REST API call to retrieve service configuration."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Request, Depends

from auth.interface import AuthTuple
from auth import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.config import Action, Configuration
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])

auth_dependency = get_auth_dependency()


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
            "feedback_enabled": True,
            "feedback_storage": "/tmp/data/feedback",
            "transcripts_enabled": False,
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
            "response": "Configuration is not loaded",
        }
    },
}


@router.get("/config", responses=get_config_responses)
@authorize(Action.GET_CONFIG)
async def config_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    request: Request,
) -> Configuration:
    """
    Handle requests to the /config endpoint.

    Process GET requests to the /config endpoint and returns the
    current service configuration.

    Returns:
        Configuration: The loaded service configuration object.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    # ensure that configuration is loaded
    check_configuration_loaded(configuration)

    return configuration.configuration
