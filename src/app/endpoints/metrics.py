"""Handler for REST API call to provide metrics."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.config import Action

router = APIRouter(tags=["metrics"])


metrics_get_responses: dict[int | str, dict[str, Any]] = {
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["ogx", "kubernetes api"]
    ),
}


@router.get(
    "/metrics", response_class=PlainTextResponse, responses=metrics_get_responses
)
@authorize(Action.GET_METRICS)
async def metrics_endpoint_handler(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    request: Request,
) -> PlainTextResponse:
    """
    Handle request to the /metrics endpoint.

    Process GET requests to the /metrics endpoint, returning the
    latest Prometheus metrics in plain text Prometheus format.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Returns:
    - PlainTextResponse: Response body containing the Prometheus metrics text
      and the Prometheus content type.
    """
    # Used only for authorization
    _ = auth

    # Nothing interesting in the request
    _ = request

    return PlainTextResponse(generate_latest(), media_type=str(CONTENT_TYPE_LATEST))
