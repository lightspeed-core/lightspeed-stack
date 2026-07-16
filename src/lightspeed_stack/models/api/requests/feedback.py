"""Request models for feedback endpoints."""

from typing import Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from models.common import FeedbackCategory
from utils import suid


class FeedbackRequest(BaseModel):
    """Model representing a feedback request.

    Attributes:
        conversation_id: The required conversation ID (UUID).
        user_question: The required user question.
        llm_response: The required LLM response.
        sentiment: The optional sentiment.
        user_feedback: The optional user feedback.
        categories: The optional list of feedback categories (multi-select for negative feedback).
    """

    conversation_id: str = Field(
        description="The required conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    user_question: str = Field(
        description="User question (the query string)",
        examples=["What is Kubernetes?"],
    )

    llm_response: str = Field(
        description="Response from LLM",
        examples=[
            "Kubernetes is an open-source container orchestration system for automating ..."
        ],
    )

    sentiment: Optional[int] = Field(
        None,
        description="User sentiment, if provided must be -1 or 1",
        examples=[-1, 1],
    )

    # Optional user feedback limited to 1-4096 characters to prevent abuse.
    user_feedback: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Feedback on the LLM response.",
        examples=["I'm not satisfied with the response because it is too vague."],
    )

    # Optional list of predefined feedback categories for negative feedback
    categories: Optional[list[FeedbackCategory]] = Field(
        default=None,
        description=(
            "List of feedback categories that describe issues with the LLM response "
            "(for negative feedback)."
        ),
        examples=[["incorrect", "incomplete"]],
    )

    # provides examples for /docs endpoint
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                    "user_question": "foo",
                    "llm_response": "bar",
                    "user_feedback": "Not satisfied with the response quality.",
                    "sentiment": -1,
                },
                {
                    "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                    "user_question": "What is the capital of France?",
                    "llm_response": "The capital of France is Berlin.",
                    "sentiment": -1,
                    "categories": ["incorrect"],
                },
                {
                    "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                    "user_question": "How do I deploy a web app?",
                    "llm_response": "Use Docker.",
                    "user_feedback": (
                        "This response is too general and doesn't provide specific steps."
                    ),
                    "sentiment": -1,
                    "categories": ["incomplete", "not_relevant"],
                },
            ]
        },
    }

    @field_validator("conversation_id")
    @classmethod
    def check_uuid(cls, value: str) -> str:
        """Validate that a conversation identifier conforms to the application's SUID format.

        Args:
            value: Conversation identifier to validate.

        Returns:
            The validated conversation identifier.

        Raises:
            ValueError: If value is not a valid SUID.
        """
        if not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID {value}")
        return value

    @field_validator("sentiment")
    @classmethod
    def check_sentiment(cls, value: Optional[int]) -> Optional[int]:
        """Validate a sentiment value is one of the allowed options.

        Args:
            value: Sentiment value; must be -1, 1, or None.

        Returns:
            The validated sentiment value.

        Raises:
            ValueError: If value is not -1, 1, or None.
        """
        if value not in {-1, 1, None}:
            raise ValueError(
                f"Improper sentiment value of {value}, needs to be -1 or 1"
            )
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls, value: Optional[list[FeedbackCategory]]
    ) -> Optional[list[FeedbackCategory]]:
        """Normalize and deduplicate a feedback categories list.

        Converts an empty list to None for consistency and removes duplicate
        categories while preserving their original order. If value is None, it
        is returned unchanged.

        Args:
            value: List of feedback categories or None.

        Returns:
            The normalized list with duplicates removed, or None.
        """
        if value is None:
            return value

        if len(value) == 0:
            return None  # Convert empty list to None for consistency

        return list(dict.fromkeys(value))  # don't lose ordering

    @model_validator(mode="after")
    def check_feedback_provided(self) -> Self:
        """Ensure at least one form of feedback is provided.

        Returns:
            The validated FeedbackRequest instance.

        Raises:
            ValueError: If none of sentiment, user_feedback, or categories are provided.
        """
        if (
            self.sentiment is None
            and (self.user_feedback is None or self.user_feedback == "")
            and self.categories is None
        ):
            raise ValueError(
                "At least one form of feedback must be provided: "
                "'sentiment', 'user_feedback', or 'categories'"
            )
        return self


class FeedbackStatusUpdateRequest(BaseModel):
    """Model representing a feedback status update request.

    Attributes:
        status: Value of the desired feedback enabled state.
    """

    status: bool = Field(
        False,
        description="Desired state of feedback enablement, must be False or True",
        examples=[True, False],
    )

    # Reject unknown fields
    model_config = {"extra": "forbid"}

    def get_value(self) -> bool:
        """Get the desired feedback enablement status.

        Returns:
            True if feedback is enabled, False otherwise.
        """
        return self.status
