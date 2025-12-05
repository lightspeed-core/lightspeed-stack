"""Handler for REST API call to provide info."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_client import APIConnectionError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InfoResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from version import __version__

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["info"])


get_info_responses: dict[int | str, dict[str, Any]] = {
    200: InfoResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


@router.get("/info", responses=get_info_responses)
@authorize(Action.INFO)
async def info_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
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
        logger.debug("Llama Stack version: %s", llama_stack_version)
        return InfoResponse(
            name=configuration.configuration.name,
            service_version=__version__,
            llama_stack_version=llama_stack_version,
        )
    # connection to Llama Stack server
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
