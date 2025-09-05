"""Handler for REST API call to authorized endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from auth.interface import AuthTuple
from auth import get_auth_dependency
from models.responses import AuthorizedResponse, UnauthorizedResponse, ForbiddenResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authorized"])
auth_dependency = get_auth_dependency()


authorized_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The user is logged-in and authorized to access OLS",
        "model": AuthorizedResponse,
    },
    400: {
        "description": "Missing or invalid credentials provided by client for the noop and"
        "noop-with-token authentication modules",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Missing or invalid credentials provided by client for the"
        "k8s authentication module",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
}


@router.post("/authorized", responses=authorized_responses)
async def authorized_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
) -> AuthorizedResponse:
    """
    Handle request to the /authorized endpoint.

    Process POST requests to the /authorized endpoint, returning
    the authenticated user's ID and username.

    Returns:
        AuthorizedResponse: Contains the user ID and username of the authenticated user.
    """
    # Ignore the user token, we should not return it in the response
    user_id, user_name, skip_userid_check, _ = auth
    return AuthorizedResponse(
        user_id=user_id, username=user_name, skip_userid_check=skip_userid_check
    )
