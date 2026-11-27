"""Handlers for health REST API endpoints.

These endpoints are used to check if service is live and prepared to accept
requests. Note that these endpoints can be accessed using GET or HEAD HTTP
methods. For HEAD HTTP method, just the HTTP response code is used.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from opentelemetry import trace

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from log import get_logger
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import (
    LivenessResponse,
    ReadinessResponse,
)
from models.common import (
    HealthStatus,
)
from models.config import Action
from providers.inference.registry import ProviderRegistry
from utils.types import Responses

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["health"])


get_readiness_responses: Responses = {
    200: ReadinessResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["OGX", "kubernetes api"]
    ),
}

get_liveness_responses: Responses = {
    200: LivenessResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


@router.get("/readiness", responses=get_readiness_responses)
@authorize(Action.INFO)
async def readiness_probe_get_method(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    response: Response,
) -> ReadinessResponse:
    """
    Handle the readiness probe endpoint, returning service readiness and health status.

    Returns comprehensive health information including overall service status,
    provider health, and functional impacts.

    ### Parameters:
    - response: The outgoing HTTP response (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 503 when service is unhealthy (providers down,
      models unavailable).

    ### Returns:
    - ReadinessResponse: Object with comprehensive health status including:
      - ready: True if service can handle requests
      - reason: Description of service state
      - overall_status: healthy or unhealthy
      - impacts: Functional limitations when unhealthy
      - providers: List of unhealthy providers
    """
    # Used only for authorization
    _ = auth

    with tracer.start_as_current_span("readiness.handle_request") as span:
        logger.info("Response to /readiness endpoint")

        registry = ProviderRegistry()

        # ProviderRegistry is not initialized which we should never encounter
        if not registry.is_initialized:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            span.set_attribute("http.status_code", 503)
            return ReadinessResponse(
                ready=False,
                reason="Provider registry is not initialized",
                overall_status=HealthStatus.UNHEALTHY,
                impacts=[
                    "LLM inference unavailable",
                ],
                providers=[],
            )

        # All healthy
        span.set_attribute("http.status_code", 200)
        return ReadinessResponse(
            ready=True,
            reason="All providers are healthy",
            overall_status=HealthStatus.HEALTHY,
            impacts=None,
            providers=[],
        )


@router.get("/liveness", responses=get_liveness_responses)
@authorize(Action.INFO)
async def liveness_probe_get_method(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> LivenessResponse:
    """
    Return the liveness status of the service.

    ### Parameters:
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to OGX.

    ### Returns:
    - LivenessResponse: Indicates that the service is alive.
    """
    # Used only for authorization
    _ = auth

    with tracer.start_as_current_span("liveness.handle_request") as span:
        logger.info("Response to /v1/liveness endpoint")
        span.set_attribute("http.status_code", 200)
        return LivenessResponse(alive=True)
