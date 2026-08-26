"""Handler for REST API call to provide info."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from ogx_client import APIConnectionError
from opentelemetry import trace

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncOgxClientHolder
from configuration import configuration
from log import get_logger
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import InfoResponse
from models.config import Action
from utils.otel_tracing import set_span_attributes
from version import __version__

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["info"])


get_info_responses: dict[int | str, dict[str, Any]] = {
    200: InfoResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
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
    service name, version and OGX version.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - InfoResponse: An object containing the service's name and version.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    with tracer.start_as_current_span("info.handle_request") as span:
        logger.info("Response to /v1/info endpoint")

        try:
            # try to get OGX client
            client = AsyncOgxClientHolder().get_client()
            # retrieve version
            llama_stack_version_object = await client.inspect.version()
            llama_stack_version = llama_stack_version_object.version
            logger.debug("Service name: %s", configuration.configuration.name)
            logger.debug("Service version: %s", __version__)
            logger.debug("OGX version: %s", llama_stack_version)
            set_span_attributes(
                span,
                {
                    "service.name": configuration.configuration.name,
                    "service.version": __version__,
                },
            )
            return InfoResponse(
                name=configuration.configuration.name,
                service_version=__version__,
                llama_stack_version=llama_stack_version,
            )
        # connection to OGX server
        except APIConnectionError as e:
            logger.error("Unable to connect to OGX: %s", e)
            response = ServiceUnavailableResponse(backend_name="OGX", cause=str(e))
            raise HTTPException(**response.model_dump()) from e
