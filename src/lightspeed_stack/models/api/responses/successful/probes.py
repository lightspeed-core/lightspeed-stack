"""Successful probe-related API responses (info, readiness, liveness, status, auth)."""

from typing import Any, Optional

from pydantic import Field

from lightspeed_stack.models.api.responses.successful.bases import (
    AbstractSuccessfulResponse,
)
from lightspeed_stack.models.common.health import (
    HealthStatus,
    ProviderHealthStatus,
)


class InfoResponse(AbstractSuccessfulResponse):
    """Model representing a response to an info request.

    Attributes:
        name: Service name.
        service_version: Service version.
        llama_stack_version: Llama Stack version.
    """

    name: str = Field(
        description="Service name",
        examples=["Lightspeed Stack"],
    )

    service_version: str = Field(
        description="Service version",
        examples=["0.1.0", "0.2.0", "1.0.0"],
    )

    llama_stack_version: str = Field(
        description="Llama Stack version",
        examples=["0.2.1", "0.2.2", "0.2.18", "0.2.21", "0.2.22"],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Lightspeed Stack",
                    "service_version": "1.0.0",
                    "llama_stack_version": "1.0.0",
                }
            ]
        }
    }


class ReadinessResponse(AbstractSuccessfulResponse):
    """Model representing response to a readiness request.

    Attributes:
        ready: If service is ready to handle requests.
        reason: The reason for the readiness status.
        overall_status: Overall service health status (healthy/degraded/unhealthy).
        impacts: Optional list of functional impacts when degraded or unhealthy.
        providers: List of unhealthy providers (empty when all healthy).
    """

    ready: bool = Field(
        ...,
        description="Flag indicating if service is ready to handle requests",
        examples=[True, False],
    )

    reason: str = Field(
        ...,
        description="The reason for the readiness status",
        examples=["Service is ready"],
    )

    overall_status: HealthStatus = Field(
        ...,
        description="Overall service health status",
        examples=["healthy", "degraded", "unhealthy"],
    )

    impacts: Optional[list[str]] = Field(
        None,
        description="List of functional impacts when service is degraded or unhealthy",
        examples=[
            [
                "LLM inference unavailable",
                "RAG functionality unavailable",
                "Agent tools unavailable",
            ]
        ],
    )

    providers: list[ProviderHealthStatus] = Field(
        ...,
        description="List of unhealthy providers (empty when all healthy)",
        examples=[],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ready": True,
                    "reason": "All providers are healthy",
                    "overall_status": "healthy",
                    "impacts": None,
                    "providers": [],
                },
                {
                    "ready": True,
                    "reason": "Service running in degraded mode",
                    "overall_status": "degraded",
                    "impacts": [
                        "LLM inference unavailable",
                        "RAG functionality unavailable",
                        "Agent tools unavailable",
                    ],
                    "providers": [],
                },
            ]
        }
    }


class LivenessResponse(AbstractSuccessfulResponse):
    """Model representing a response to a liveness request.

    Attributes:
        alive: If app is alive.
    """

    alive: bool = Field(
        ...,
        description="Flag indicating that the app is alive",
        examples=[True, False],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "alive": True,
                }
            ]
        }
    }


class StatusResponse(AbstractSuccessfulResponse):
    """Model representing a response to a status request.

    Attributes:
        functionality: The functionality of the service.
        status: The status of the service.
    """

    functionality: str = Field(
        ...,
        description="The functionality of the service",
        examples=["feedback"],
    )

    status: dict[str, Any] = Field(
        ...,
        description="The status of the service",
        examples=[{"enabled": True}],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "functionality": "feedback",
                    "status": {"enabled": True},
                }
            ]
        }
    }


class AuthorizedResponse(AbstractSuccessfulResponse):
    """Model representing a response to an authorization request.

    Attributes:
        user_id: The ID of the logged in user.
        username: The name of the logged in user.
        skip_userid_check: Whether to skip the user ID check.
    """

    user_id: str = Field(
        ...,
        description="User ID, for example UUID",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )
    username: str = Field(
        ...,
        description="User name",
        examples=["John Doe", "Adam Smith"],
    )
    skip_userid_check: bool = Field(
        ...,
        description="Whether to skip the user ID check",
        examples=[True, False],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "user1",
                    "skip_userid_check": False,
                }
            ]
        }
    }
