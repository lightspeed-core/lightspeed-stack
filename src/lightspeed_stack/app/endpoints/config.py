"""Handler for REST API call to retrieve service configuration."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from lightspeed_stack.authentication import get_auth_dependency
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.authorization.middleware import authorize
from lightspeed_stack.configuration import configuration
from lightspeed_stack.log import get_logger
from lightspeed_stack.models.api.responses.constants import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
)
from lightspeed_stack.models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from lightspeed_stack.models.api.responses.successful import ConfigurationResponse
from lightspeed_stack.models.config import Action
from lightspeed_stack.utils.endpoints import check_configuration_loaded

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

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

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
