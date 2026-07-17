"""Handler for REST API call to list available shields."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.params import Depends
from llama_stack_client import APIConnectionError

from lightspeed_stack.authentication import get_auth_dependency
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.authorization.middleware import authorize
from lightspeed_stack.client import AsyncLlamaStackClientHolder
from lightspeed_stack.configuration import configuration
from lightspeed_stack.log import get_logger
from lightspeed_stack.models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from lightspeed_stack.models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from lightspeed_stack.models.api.responses.successful import ShieldsResponse
from lightspeed_stack.models.config import Action
from lightspeed_stack.utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["shields"])


shields_responses: dict[int | str, dict[str, Any]] = {
    200: ShieldsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
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
    shields from the Llama Stack service.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

    ### Returns:
    - ShieldsResponse: An object containing the list of available shields.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    llama_stack_configuration = configuration.llama_stack_configuration
    logger.info("Llama stack config: %s", llama_stack_configuration)

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        # retrieve shields
        shields = await client.shields.list()
        s = [dict(s) for s in shields]
        return ShieldsResponse(shields=s)

    # connection to Llama Stack server
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
