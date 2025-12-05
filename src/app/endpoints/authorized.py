"""Handler for REST API call to authorized endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from models.responses import AuthorizedResponse, ForbiddenResponse, UnauthorizedResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authorized"])

authorized_responses: dict[int | str, dict[str, Any]] = {
    200: AuthorizedResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
}


@router.post("/authorized", responses=authorized_responses)
async def authorized_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
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
