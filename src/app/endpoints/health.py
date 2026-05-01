"""Handlers for health REST API endpoints.

These endpoints are used to check if service is live and prepared to accept
requests. Note that these endpoints can be accessed using GET or HEAD HTTP
methods. For HEAD HTTP method, just the HTTP response code is used.
"""

from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from llama_stack_client import APIConnectionError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.api.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ForbiddenResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.config import Action
from models.responses import (
    LivenessResponse,
    ProviderHealthStatus,
    ReadinessResponse,
)

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


# HealthStatus enum was removed from llama_stack in newer versions
# Defining locally for compatibility
class HealthStatus(str, Enum):
    """Health status enum for provider health checks."""

    OK = "ok"
    ERROR = "Error"
    NOT_IMPLEMENTED = "not_implemented"
    HEALTHY = "healthy"
    UNKNOWN = "unknown"


get_readiness_responses: dict[int | str, dict[str, Any]] = {
    200: ReadinessResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}

get_liveness_responses: dict[int | str, dict[str, Any]] = {
    200: LivenessResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


async def get_providers_health_statuses() -> list[ProviderHealthStatus]:
    """
    Retrieve the health status of all configured providers.

    Returns:
        list[ProviderHealthStatus]: A list containing the health
        status of each provider. If provider health cannot be
        determined, returns a single entry indicating an error.
    """
    try:
        client = AsyncLlamaStackClientHolder().get_client()

        providers = await client.providers.list()
        logger.debug("Found %d providers", len(providers))

        return [
            ProviderHealthStatus(
                provider_id=provider.provider_id,
                status=str(provider.health.get("status", "unknown")),
                message=str(provider.health.get("message", "")),
            )
            for provider in providers
        ]

    except APIConnectionError as e:
        logger.error("Failed to check providers health: %s", e)
        return [
            ProviderHealthStatus(
                provider_id="unknown",
                status=HealthStatus.ERROR.value,
                message=f"Failed to initialize health check: {e!s}",
            )
        ]


async def check_default_model_available() -> tuple[bool, str]:
    """Check that the configured default model is registered in the model registry.

    Retrieves the default model and provider from configuration and delegates
    the availability check to the client holder.

    Returns:
        A tuple of (available, reason) where available is True if the default
        model was found or no default model is configured, and reason describes
        the outcome.
    """
    inference = configuration.inference
    if (
        inference is None
        or not inference.default_model
        or not inference.default_provider
    ):
        return True, "No default model configured"

    expected_model_id = f"{inference.default_provider}/{inference.default_model}"

    client_holder = AsyncLlamaStackClientHolder()
    return await client_holder.check_model_available(expected_model_id)


@router.get("/readiness", responses=get_readiness_responses)
@authorize(Action.INFO)
async def readiness_probe_get_method(
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    response: Response,
) -> ReadinessResponse:
    """
    Handle the readiness probe endpoint, returning service readiness.

    If any provider reports an error status, responds with HTTP 503
    and details of unhealthy providers; otherwise, indicates the
    service is ready.

    ### Parameters:
    - response: The outgoing HTTP response (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Returns:
    - ReadinessResponse: Object with `ready` indicating overall readiness,
      `reason` explaining the outcome, and `providers` containing the list of
      unhealthy ProviderHealthStatus entries (empty when ready).
    """
    # Used only for authorization
    _ = auth

    logger.info("Response to /v1/readiness endpoint")

    provider_statuses = await get_providers_health_statuses()

    # Check if any provider is unhealthy (not counting not_implemented as unhealthy)
    unhealthy_providers = [
        p for p in provider_statuses if p.status == HealthStatus.ERROR.value
    ]

    if unhealthy_providers:
        ready = False
        unhealthy_provider_names = [p.provider_id for p in unhealthy_providers]
        reason = f"Providers not healthy: {', '.join(unhealthy_provider_names)}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            ready=ready, reason=reason, providers=unhealthy_providers
        )

    # Check that the default model is registered in the model registry
    model_available, model_reason = await check_default_model_available()
    if not model_available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            ready=False, reason=model_reason, providers=unhealthy_providers
        )

    return ReadinessResponse(
        ready=True, reason="All providers are healthy", providers=unhealthy_providers
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

    ### Returns:
    - LivenessResponse: Indicates that the service is alive.
    """
    # Used only for authorization
    _ = auth

    logger.info("Response to /v1/liveness endpoint")

    return LivenessResponse(alive=True)
