"""Handler for REST API call to provide info."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Depends
from llama_stack_client import APIConnectionError

from authentication.interface import AuthTuple
from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from client import AsyncLlamaStackClientHolder
from models.config import Action
from models.responses import InfoResponse
from version import __version__

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["info"])
auth_dependency = get_auth_dependency()


get_info_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "name": "Service name",
        "service_version": "Service version",
        "llama_stack_version": "Llama Stack version",
    },
    500: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
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
    service name, version and Llama-stack version.

    Returns:
        InfoResponse: An object containing the service's name and version.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    logger.info("Response to /v1/info endpoint")

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        # retrieve version
        llama_stack_version_object = await client.inspect.version()
        llama_stack_version = llama_stack_version_object.version
        logger.debug("Service name: %s", configuration.configuration.name)
        logger.debug("Service version: %s", __version__)
        logger.debug("LLama Stack version: %s", llama_stack_version)
        return InfoResponse(
            name=configuration.configuration.name,
            service_version=__version__,
            llama_stack_version=llama_stack_version,
        )
    # connection to Llama Stack server
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e
