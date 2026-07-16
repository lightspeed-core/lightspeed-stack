"""Health-related shared models for readiness and diagnostics."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status enum for provider and service health checks.

    This enum serves two purposes:

    1. Provider-level health (returned by Llama Stack providers):
       - OK: Provider is healthy and operational
       - ERROR: Provider is unhealthy or failed health check
       - NOT_IMPLEMENTED: Provider does not implement health checks
       - UNKNOWN: Fallback when provider status cannot be determined

    2. Service-level health (overall LCORE status):
       - HEALTHY: All systems operational, LLS connected, all providers healthy
       - DEGRADED: Service running with reduced functionality (e.g., LLS unavailable)
       - UNHEALTHY: Service connected but one or more providers are unhealthy
    """

    # Provider-level statuses (from Llama Stack)
    OK = "ok"
    ERROR = "error"
    NOT_IMPLEMENTED = "not_implemented"
    UNKNOWN = "unknown"

    # Service-level statuses (LCORE overall health)
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProviderHealthStatus(BaseModel):
    """Model representing the health status of a provider.

    Attributes:
        provider_id: The ID of the provider.
        status: The health status ('ok', 'unhealthy', 'not_implemented').
        message: Optional message about the health status.
    """

    provider_id: str = Field(
        description="The ID of the provider",
    )
    status: str = Field(
        description="The health status",
        examples=["ok", "unhealthy", "not_implemented"],
    )
    message: Optional[str] = Field(
        None,
        description="Optional message about the health status",
        examples=["All systems operational", "Provider is unavailable"],
    )
