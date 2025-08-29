"""Handler for REST API call to provide info."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi import Depends

from auth.interface import AuthTuple
from auth import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.config import Action
from models.responses import InfoResponse
from version import __version__

logger = logging.getLogger(__name__)
router = APIRouter(tags=["info"])

auth_dependency = get_auth_dependency()


get_info_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "name": "Service name",
        "version": "Service version",
    },
}


@router.get("/info", responses=get_info_responses)
@authorize(Action.INFO)
async def info_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    request: Request,
) -> InfoResponse:
    """
    Handle request to the /info endpoint.

    Process GET requests to the /info endpoint, returning the
    service name and version.

    Returns:
        InfoResponse: An object containing the service's name and version.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    return InfoResponse(name=configuration.configuration.name, version=__version__)
