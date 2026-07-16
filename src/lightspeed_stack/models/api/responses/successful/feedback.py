"""Successful responses for feedback and feedback status endpoints."""

from typing import Any

from pydantic import Field

from models.api.responses.successful.bases import AbstractSuccessfulResponse


class FeedbackResponse(AbstractSuccessfulResponse):
    """Model representing a response to a feedback request.

    Attributes:
        response: The response of the feedback request.
    """

    response: str = Field(
        ...,
        description="The response of the feedback request.",
        examples=["feedback received"],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "response": "feedback received",
                }
            ]
        }
    }


class FeedbackStatusUpdateResponse(AbstractSuccessfulResponse):
    """Model representing a response to a feedback status update request.

    Attributes:
        status: The previous and current status of the service and who updated it.
    """

    status: dict[str, Any]

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": {
                        "previous_status": True,
                        "updated_status": False,
                        "updated_by": "user/test",
                        "timestamp": "2023-03-15 12:34:56",
                    },
                }
            ]
        }
    }
