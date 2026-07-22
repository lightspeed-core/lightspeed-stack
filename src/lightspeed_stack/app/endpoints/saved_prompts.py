"""Handler for REST API calls to manage saved prompts."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

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
from lightspeed_stack.models.api.responses.successful import SavedPromptsConfigResponse
from lightspeed_stack.models.config import Action
from lightspeed_stack.utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["saved-prompts"])


get_saved_prompts_config_responses: dict[int | str, dict[str, Any]] = {
    200: SavedPromptsConfigResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


@router.get("/saved-prompts/config", responses=get_saved_prompts_config_responses)
@authorize(Action.GET_CONFIG)
async def get_saved_prompts_config_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    request: Request,
) -> SavedPromptsConfigResponse:
    """
    Handle requests to the GET /saved-prompts/config endpoint.

    Process GET requests that return saved prompts configuration limits so
    consuming services can provide limits consistent with what the server
    will enforce. For example:

        curl http://localhost:8080/v1/saved-prompts/config

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to backend services.

    ### Returns:
    - SavedPromptsConfigResponse: Saved prompts configuration limits.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    saved_prompts_config = configuration.configuration.saved_prompts
    max_prompts_per_user = saved_prompts_config.max_prompts_per_user
    max_display_name_length = saved_prompts_config.max_display_name_length
    max_content_length = saved_prompts_config.max_content_length
    if (
        max_prompts_per_user is None
        or max_display_name_length is None
        or max_content_length is None
    ):
        logger.error("Saved prompts configuration limits are not set")
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump())

    return SavedPromptsConfigResponse(
        max_prompts_per_user=max_prompts_per_user,
        max_display_name_length=max_display_name_length,
        max_content_length=max_content_length,
    )
