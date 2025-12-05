"""Handler for REST API call to retrieve service configuration."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from models.config import Action
from models.responses import (
    ConfigurationResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


get_config_responses: dict[int | str, dict[str, Any]] = {
    200: ConfigurationResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
}


@router.get("/config", responses=get_config_responses)
@authorize(Action.GET_CONFIG)
async def config_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    request: Request,
) -> ConfigurationResponse:
    """
    Handle requests to the /config endpoint.

    Process GET requests to the /config endpoint and returns the
    current service configuration.

    Returns:
        ConfigurationResponse: The loaded service configuration response.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    # ensure that configuration is loaded
    check_configuration_loaded(configuration)

    return ConfigurationResponse(configuration=configuration.configuration)
