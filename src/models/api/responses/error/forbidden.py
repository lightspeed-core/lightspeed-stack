"""OpenAPI-aligned error response models: HTTP 403 Forbidden."""

from typing import ClassVar

from fastapi import status
from typing_extensions import Self  # noqa: UP035

from models.api.responses.constants import FORBIDDEN_DESCRIPTION
from models.api.responses.error.bases import AbstractErrorResponse
from models.config import Action


class ForbiddenResponse(AbstractErrorResponse):
    """403 Forbidden. Access denied."""

    description: ClassVar[str] = FORBIDDEN_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation read",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to read conversation "
                            "with ID 123e4567-e89b-12d3-a456-426614174000"
                        ),
                    },
                },
                {
                    "label": "conversation delete",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to delete conversation "
                            "with ID 123e4567-e89b-12d3-a456-426614174000"
                        ),
                    },
                },
                {
                    "label": "endpoint",
                    "detail": {
                        "response": "User does not have permission to access this endpoint",
                        "cause": "User 6789 is not authorized to access this endpoint.",
                    },
                },
                {
                    "label": "prompt read",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to list or read stored prompts "
                            "(missing permission: read_prompts)."
                        ),
                    },
                },
                {
                    "label": "prompt manage",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to create, update, or delete "
                            "stored prompts (missing permission: manage_prompts)."
                        ),
                    },
                },
                {
                    "label": "feedback",
                    "detail": {
                        "response": "Storing feedback is disabled",
                        "cause": "Storing feedback is disabled.",
                    },
                },
                {
                    "label": "model override",
                    "detail": {
                        "response": (
                            "This instance does not permit overriding model/provider in the "
                            "query request (missing permission: model_override). Please remove "
                            "the model and provider fields from your request."
                        ),
                        "cause": (
                            "User lacks model_override permission required "
                            "to override model/provider."
                        ),
                    },
                },
            ]
        }
    }

    @classmethod
    def conversation(cls, action: str, resource_id: str, user_id: str) -> Self:
        """Create a ForbiddenResponse for a denied conversation action.

        Args:
            action: The attempted action (e.g. read, delete, update).
            resource_id: The conversation identifier targeted by the action.
            user_id: The identifier of the user who attempted the action.

        Returns:
            Error response indicating the user is not permitted to perform the
            specified action on the conversation, with response and cause set.
        """
        response = "User does not have permission to perform this action"
        cause = (
            f"User {user_id} does not have permission to "
            f"{action} conversation with ID {resource_id}"
        )
        return cls(response=response, cause=cause)

    @classmethod
    def endpoint(cls, user_id: str) -> Self:
        """Create a ForbiddenResponse indicating the user is denied access to the endpoint.

        Args:
            user_id: Identifier of the user denied access.

        Returns:
            Error response with a message and a cause referencing the given user_id.
        """
        response = "User does not have permission to access this endpoint"
        cause = f"User {user_id} is not authorized to access this endpoint."
        return cls(response=response, cause=cause)

    @classmethod
    def feedback_disabled(cls) -> Self:
        """Create a ForbiddenResponse indicating that storing feedback is disabled.

        Returns:
            Error response with response set to "Storing feedback is disabled"
            and cause set to "Storing feedback is disabled.".
        """
        return cls(
            response="Storing feedback is disabled",
            cause="Storing feedback is disabled.",
        )

    @classmethod
    def model_override(cls) -> Self:
        """Create a ForbiddenResponse when overriding the model or provider is disallowed.

        Returns:
            An error response with a user-facing message instructing removal of
            model/provider fields and a cause stating the missing MODEL_OVERRIDE
            permission.
        """
        return cls(
            response=(
                f"This instance does not permit overriding model/provider in the "
                f"query request (missing permission: {Action.MODEL_OVERRIDE.value}). "
                "Please remove the model and provider fields from your request."
            ),
            cause=(
                f"User lacks {Action.MODEL_OVERRIDE.value} permission required "
                "to override model/provider."
            ),
        )

    def __init__(self, *, response: str, cause: str) -> None:
        """Construct a ForbiddenResponse with a public message and an internal cause.

        Args:
            response: Human-facing error message describing the forbidden action.
            cause: Detailed reason for the denial, for logs or diagnostics.
        """
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_403_FORBIDDEN
        )
