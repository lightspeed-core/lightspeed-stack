"""Handler for REST API call to authorized endpoint."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request

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
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
}


@router.post("/authorized", responses=authorized_responses)
def authorized_endpoint_handler(_request: Request) -> AuthorizedResponse:
    """Handle request to the /authorized endpoint."""
    # Ignore the user token, we should not return it in the response
    user_id, user_name, _ = asyncio.run(auth_dependency(_request))
    return AuthorizedResponse(user_id=user_id, username=user_name)
