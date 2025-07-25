"""Model for service requests."""

from typing import Optional, Self
from enum import Enum

from pydantic import BaseModel, model_validator, field_validator, Field
from llama_stack_client.types.agents.turn_create_params import Document

from log import get_logger
from utils import suid

logger = get_logger(__name__)


class Attachment(BaseModel):
    """Model representing an attachment that can be send from UI as part of query.

    List of attachments can be optional part of 'query' request.

    Attributes:
        attachment_type: The attachment type, like "log", "configuration" etc.
        content_type: The content type as defined in MIME standard
        content: The actual attachment content

    YAML attachments with **kind** and **metadata/name** attributes will
    be handled as resources with specified name:
    ```
    kind: Pod
    metadata:
        name: private-reg
    ```
    """

    attachment_type: str
    content_type: str
    content: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "attachment_type": "log",
                    "content_type": "text/plain",
                    "content": "this is attachment",
                },
                {
                    "attachment_type": "configuration",
                    "content_type": "application/yaml",
                    "content": "kind: Pod\n metadata:\n name:    private-reg",
                },
                {
                    "attachment_type": "configuration",
                    "content_type": "application/yaml",
                    "content": "foo: bar",
                },
            ]
        }
    }


class QueryRequest(BaseModel):
    """Model representing a request for the LLM (Language Model).

    Attributes:
        query: The query string.
        conversation_id: The optional conversation ID (UUID).
        provider: The optional provider.
        model: The optional model.
        system_prompt: The optional system prompt.
        attachments: The optional attachments.

    Example:
        ```python
        query_request = QueryRequest(query="Tell me about Kubernetes")
        ```
    """

    query: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    attachments: Optional[list[Attachment]] = None
    # media_type is not used in 'lightspeed-stack' that only supports application/json.
    # the field is kept here to enable compatibility with 'road-core' clients.
    media_type: Optional[str] = None

    # provides examples for /docs endpoint
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "query": "write a deployment yaml for the mongodb image",
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "provider": "openai",
                    "model": "model-name",
                    "system_prompt": "You are a helpful assistant",
                    "attachments": [
                        {
                            "attachment_type": "log",
                            "content_type": "text/plain",
                            "content": "this is attachment",
                        },
                        {
                            "attachment_type": "configuration",
                            "content_type": "application/yaml",
                            "content": "kind: Pod\n metadata:\n    name: private-reg",
                        },
                        {
                            "attachment_type": "configuration",
                            "content_type": "application/yaml",
                            "content": "foo: bar",
                        },
                    ],
                }
            ]
        },
    }

    def get_documents(self) -> list[Document]:
        """Return the list of documents from the attachments."""
        if not self.attachments:
            return []
        return [
            Document(content=att.content, mime_type=att.content_type)
            for att in self.attachments  # pylint: disable=not-an-iterable
        ]

    @model_validator(mode="after")
    def validate_provider_and_model(self) -> Self:
        """Perform validation on the provider and model."""
        if self.model and not self.provider:
            raise ValueError("Provider must be specified if model is specified")
        if self.provider and not self.model:
            raise ValueError("Model must be specified if provider is specified")
        return self

    @model_validator(mode="after")
    def validate_media_type(self) -> Self:
        """Log use of media_type that is unsupported but kept for backwards compatibility."""
        if self.media_type:
            logger.warning(
                "media_type was set in the request but is not supported. The value will be ignored."
            )
        return self


class FeedbackCategory(str, Enum):
    """Enum representing predefined feedback categories for AI responses.

    These categories help provide structured feedback about AI inference quality
    when users provide negative feedback (thumbs down). Multiple categories can
    be selected to provide comprehensive feedback about response issues.
    """

    INCORRECT = "incorrect"  # "The answer provided is completely wrong"
    NOT_RELEVANT = "not_relevant"  # "This answer doesn't address my question at all"
    INCOMPLETE = "incomplete"  # "The answer only covers part of what I asked about"
    OUTDATED_INFORMATION = "outdated_information"  # "This information is from several years ago and no longer accurate"  # pylint: disable=line-too-long
    UNSAFE = "unsafe"  # "This response could be harmful or dangerous if followed"
    OTHER = "other"  # "The response has issues not covered by other categories"


class FeedbackRequest(BaseModel):
    """Model representing a feedback request.

    Attributes:
        conversation_id: The required conversation ID (UUID).
        user_question: The required user question.
        llm_response: The required LLM response.
        sentiment: The optional sentiment.
        user_feedback: The optional user feedback.
        categories: The optional list of feedback categories (multi-select for negative feedback).

    Example:
        ```python
        feedback_request = FeedbackRequest(
            conversation_id="12345678-abcd-0000-0123-456789abcdef",
            user_question="what are you doing?",
            user_feedback="This response is not helpful",
            llm_response="I don't know",
            sentiment=-1,
            categories=[FeedbackCategory.INCORRECT, FeedbackCategory.INCOMPLETE]
        )
        ```
    """

    conversation_id: str
    user_question: str
    llm_response: str
    sentiment: Optional[int] = None
    # Optional user feedback limited to 1–4096 characters to prevent abuse.
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
        }
    }

    @field_validator("conversation_id")
    @classmethod
    def check_uuid(cls, value: str) -> str:
        """Check if conversation ID has the proper format."""
        if not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID {value}")
        return value

    @field_validator("sentiment")
    @classmethod
    def check_sentiment(cls, value: Optional[int]) -> Optional[int]:
        """Check if sentiment value is as expected."""
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
        """Validate feedback categories list."""
        if value is None:
            return value

        if len(value) == 0:
            return None  # Convert empty list to None for consistency

        unique_categories = list(set(value))
        return unique_categories

    @model_validator(mode="after")
    def check_feedback_provided(self) -> Self:
        """Ensure that at least one form of feedback is provided."""
        if (
            self.sentiment is None
            and self.user_feedback is None
            and self.categories is None
        ):
            raise ValueError(
                "At least one form of feedback must be provided: "
                "'sentiment', 'user_feedback', or 'categories'"
            )
        return self
