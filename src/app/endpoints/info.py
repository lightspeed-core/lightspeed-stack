"""Handler for REST API call to provide info."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from opentelemetry import trace

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
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
from utils.otel_tracing import SpanAttributes, set_span_attributes
from utils.types import Responses
from version import __version__

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["info"])


get_info_responses: Responses = {
    200: InfoResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
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
    service name and version. The answer does not depend on OGX.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when the Kubernetes authentication backend is unreachable.

    ### Returns:
    - InfoResponse: An object containing the service's name and version.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    with tracer.start_as_current_span("info.handle_request") as span:
        logger.info("Response to /v1/info endpoint")

        logger.debug("Service name: %s", configuration.configuration.name)
        logger.debug("Service version: %s", __version__)
        set_span_attributes(
            span,
            {
                SpanAttributes.SERVICE_NAME: configuration.configuration.name,
                SpanAttributes.SERVICE_VERSION: __version__,
            },
        )
        return InfoResponse(
            name=configuration.configuration.name,
            service_version=__version__,
        )
