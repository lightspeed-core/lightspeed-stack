"""Handler for REST API call to list loaded agent skills."""

from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
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
from models.api.responses.successful import SkillsResponse
from models.config import Action
from utils.endpoints import check_configuration_loaded
from utils.pydantic_ai_helpers import get_skills_metadata

logger = get_logger(__name__)
router = APIRouter(tags=["skills"])


skills_responses: dict[int | str, dict[str, Any]] = {
    200: SkillsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
}


@router.get("/skills", responses=skills_responses)
@authorize(Action.GET_SKILLS)
async def skills_endpoint_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> SkillsResponse:
    """Handle requests to the /skills endpoint.

    Process GET requests to the /skills endpoint, returning a list of loaded
    agent skills with their metadata (name, description).

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.

    ### Returns:
    - SkillsResponse: An object containing the list of loaded skills.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    skills_metadata = await run_in_threadpool(
        get_skills_metadata, configuration.configuration.skills
    )
    return SkillsResponse(skills=skills_metadata)
