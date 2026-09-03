"""Handler for REST API call to list available shields."""

from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.params import Depends

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import ShieldsResponse
from models.common.shields import CatalogShield
from models.config import Action
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["shields"])


shields_responses: dict[int | str, dict[str, Any]] = {
    200: ShieldsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
}


@router.get("/shields", responses=shields_responses)
@authorize(Action.GET_SHIELDS)
async def shields_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> ShieldsResponse:
    """
    Handle requests to the /shields endpoint.

    Process GET requests to the /shields endpoint, returning a list of available
    shields from Lightspeed Core Stack configuration.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.

    ### Returns:
    - ShieldsResponse: An object containing the list of available shields.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    shields = [
        CatalogShield.model_validate(shield.model_dump())
        for shield in configuration.shields
    ]
    logger.info("Returning %d configured shield(s)", len(shields))
    return ShieldsResponse(shields=shields)
