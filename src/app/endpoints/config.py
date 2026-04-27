"""Handler for REST API call to retrieve service configuration."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.config import Action
from models.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ConfigurationResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["config"])


get_config_responses: dict[int | str, dict[str, Any]] = {
    200: ConfigurationResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
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

    Ensures the application configuration is loaded before returning it.

    ### Parameters:
    - request: The incoming HTTP request.
    - auth: Authentication tuple from the auth dependency.

    ### Returns:
    - ConfigurationResponse: The loaded service configuration response.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    # ensure that configuration is loaded
    check_configuration_loaded(configuration)

    return ConfigurationResponse(configuration=configuration.configuration)
