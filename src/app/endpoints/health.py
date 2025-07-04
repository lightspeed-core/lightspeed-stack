"""Handlers for health REST API endpoints.

These endpoints are used to check if service is live and prepared to accept
requests. Note that these endpoints can be accessed using GET or HEAD HTTP
methods. For HEAD HTTP method, just the HTTP response code is used.
"""

import logging
from typing import Any

from llama_stack.providers.datatypes import HealthStatus

from fastapi import APIRouter, status, Response
from client import lsc_holder
from models.responses import (
    LivenessResponse,
    ReadinessResponse,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def get_providers_health_statuses() -> list[ProviderHealthStatus]:
    """Check health of all providers.

    Returns:
        List of provider health statuses.
    """
    try:
        client = lsc_holder.get_llama_stack_client()

        providers = client.providers.list()
        logger.debug("Found %d providers", len(providers))

        health_results = [
            ProviderHealthStatus(
                provider_id=provider.provider_id,
                status=str(provider.health.get("status", "unknown")),
                message=str(provider.health.get("message", "")),
            )
            for provider in providers
        ]
        return health_results

    except Exception as e:  # pylint: disable=broad-exception-caught
        # eg. no providers defined
        logger.error("Failed to check providers health: %s", e)
        return [
            ProviderHealthStatus(
                provider_id="unknown",
                status=HealthStatus.ERROR.value,
                message=f"Failed to initialize health check: {str(e)}",
            )
        ]


get_readiness_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Service is ready",
        "model": ReadinessResponse,
    },
    503: {
        "description": "Service is not ready",
        "model": ReadinessResponse,
    },
}


@router.get("/readiness", responses=get_readiness_responses)
def readiness_probe_get_method(response: Response) -> ReadinessResponse:
    """Ready status of service with provider health details."""
    provider_statuses = get_providers_health_statuses()

    # Check if any provider is unhealthy (not counting not_implemented as unhealthy)
    unhealthy_providers = [
        p for p in provider_statuses if p.status == HealthStatus.ERROR.value
    ]

    if unhealthy_providers:
        ready = False
        unhealthy_provider_names = [p.provider_id for p in unhealthy_providers]
        reason = f"Providers not healthy: {', '.join(unhealthy_provider_names)}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        ready = True
        reason = "All providers are healthy"

    return ReadinessResponse(ready=ready, reason=reason, providers=unhealthy_providers)


get_liveness_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Service is alive",
        "model": LivenessResponse,
    },
    503: {
        "description": "Service is not alive",
        "model": LivenessResponse,
    },
}


@router.get("/liveness", responses=get_liveness_responses)
def liveness_probe_get_method() -> LivenessResponse:
    """Live status of service."""
    return LivenessResponse(alive=True)
