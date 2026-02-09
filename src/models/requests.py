"""Models for REST API requests."""

from typing import Optional, Self, Any
from enum import Enum
from typing import Dict, Iterable, List, Optional, Self, Union, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from constants import MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT
from log import get_logger
from models.responses_api_types import (
    IncludeParameter,
    Prompt,
    ResponseInput,
    Text,
    Tool,
    ToolChoice,
)
from utils import suid

logger = get_logger(__name__)


class Attachment(BaseModel):
    """Model representing an attachment that can be send from the UI as part of query.

    A list of attachments can be an optional part of 'query' request.

    Attributes:
        attachment_type: The attachment type, like "log", "configuration" etc.
        content_type: The content type as defined in MIME standard
        content: The actual attachment content

    YAML attachments with **kind** and **metadata/name** attributes will
    be handled as resources with the specified name:
    ```
    kind: Pod
    metadata:
        name: private-reg
    ```
    """

    attachment_type: str = Field(
        description="The attachment type, like 'log', 'configuration' etc.",
        examples=["log"],
    )
    content_type: str = Field(
        description="The content type as defined in MIME standard",
        examples=["text/plain"],
    )
    content: str = Field(
        description="The actual attachment content",
        examples=["warning: quota exceeded"],
    )

    # provides examples for /docs endpoint
    model_config = {
        "extra": "forbid",
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
        },
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
        no_tools: Whether to bypass all tools and MCP servers (default: False).
        generate_topic_summary: Whether to generate topic summary for new conversations.
        media_type: The optional media type for response format (application/json or text/plain).
        vector_store_ids: The optional list of specific vector store IDs to query for RAG.

    Example:
        ```python
        query_request = QueryRequest(query="Tell me about Kubernetes")
        ```
    """

    query: str = Field(
        description="The query string",
        examples=["What is Kubernetes?"],
    )

    conversation_id: Optional[str] = Field(
        None,
        description="The optional conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    provider: Optional[str] = Field(
        None,
        description="The optional provider",
        examples=["openai", "watsonx"],
    )

    model: Optional[str] = Field(
        None,
        description="The optional model",
        examples=["gpt4mini"],
    )

    system_prompt: Optional[str] = Field(
        None,
        description="The optional system prompt.",
        examples=["You are OpenShift assistant.", "You are Ansible assistant."],
    )

    attachments: Optional[list[Attachment]] = Field(
        None,
        description="The optional list of attachments.",
        examples=[
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
        ],
    )

    no_tools: Optional[bool] = Field(
        False,
        description="Whether to bypass all tools and MCP servers",
        examples=[True, False],
    )

    generate_topic_summary: Optional[bool] = Field(
        True,
        description="Whether to generate topic summary for new conversations",
        examples=[True, False],
    )

    media_type: Optional[str] = Field(
        None,
        description="Media type for the response format",
        examples=[MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT],
    )

    vector_store_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of specific vector store IDs to query for RAG. "
        "If not provided, all available vector stores will be queried.",
        examples=["ocp_docs", "knowledge_base", "vector_db_1"],
    )

    solr: Optional[dict[str, Any]] = Field(
        None,
        description="Solr-specific query parameters including filter queries",
        examples=[
            {"fq": ["product:*openshift*", "product_version:*4.16*"]},
        ],
    )
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
                    "no_tools": False,
                    "generate_topic_summary": True,
                    "vector_store_ids": ["ocp_docs", "knowledge_base"],
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

    @field_validator("conversation_id")
    @classmethod
    def check_uuid(cls, value: Optional[str]) -> Optional[str]:
        """
        Validate that a conversation identifier matches the expected SUID format.

        Parameters:
            value (Optional[str]): Conversation identifier to validate; may be None.

        Returns:
            Optional[str]: The original `value` if valid or `None` if not provided.

        Raises:
            ValueError: If `value` is provided and does not conform to the
                        expected SUID format.
        """
        if value and not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID '{value}'")
        return value

    @model_validator(mode="after")
    def validate_provider_and_model(self) -> Self:
        """
        Ensure `provider` and `model` are specified together.

        Raises:
            ValueError: If only `provider` or only `model` is provided (they must be set together).

        Returns:
            Self: The validated model instance.
        """
        if self.model and not self.provider:
            raise ValueError("Provider must be specified if model is specified")
        if self.provider and not self.model:
            raise ValueError("Model must be specified if provider is specified")
        return self

    @model_validator(mode="after")
    def validate_media_type(self) -> Self:
        """
        Ensure the `media_type`, if present, is one of the allowed response media types.

        Raises:
            ValueError: If `media_type` is not equal to `MEDIA_TYPE_JSON` or `MEDIA_TYPE_TEXT`.

        Returns:
            Self: The model instance when validation passes.
        """
        if self.media_type and self.media_type not in [
            MEDIA_TYPE_JSON,
            MEDIA_TYPE_TEXT,
        ]:
            raise ValueError(
                f"media_type must be either '{MEDIA_TYPE_JSON}' or '{MEDIA_TYPE_TEXT}'"
            )
        return self


class ResponsesRequest(BaseModel):
    """Model representing a request for the Responses API following LCORE specification.

    This model inherits a subset of request attributes directly from the LLS OpenAPI specification
    and includes LCORE-specific extensions and mappings.

    LCORE Extensions:
        - model: Optional (unlike LLS which requires it). If not provided, LCORE automatically
          selects an appropriate LLM model based on conversation history or available models.
        - generate_topic_summary: LCORE-specific flag for generating topic summaries.

    Attributes:
        input: The input text or iterable of message objects (required, inherited from LLS).
        model: The model identifier in format 'provider/model' (optional in LCORE, required in LLS).
            If not provided, LCORE will automatically select an appropriate LLM model.
        conversation: The conversation ID, accepts OpenAI conv_* format or LCORE hex UUID.
        include: Include parameter (inherited from LLS).
        instructions: System instructions (inherited from LLS, maps from system_prompt).
        max_infer_iters: Maximum inference iterations (inherited from LLS).
        max_tool_calls: Maximum tool calls (inherited from LLS).
        metadata: Metadata dictionary (inherited from LLS).
        parallel_tool_calls: Parallel tool calls flag (inherited from LLS).
        previous_response_id: Previous response ID (inherited from LLS).
        prompt: Prompt parameter (inherited from LLS).
        store: Store flag (inherited from LLS, defaults to True).
        stream: Stream flag (inherited from LLS, defaults to False).
        temperature: Temperature parameter (inherited from LLS).
        text: Text parameter (inherited from LLS).
        tool_choice: Tool choice parameter (inherited from LLS, maps from no_tools).
        tools: Tools list (inherited from LLS, includes vector_store_ids).
        generate_topic_summary: LCORE-specific flag for generating topic summaries.
    """

    input: ResponseInput = Field(
        ...,
        description="The input text (string) or iterable of message objects (complex input)",
        examples=[
            "What is Kubernetes?",
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "What is Kubernetes?"},
                        {
                            "type": "input_image",
                            "image_url": "https://example.com/image.png",
                        },
                    ],
                }
            ],
        ],
    )
    model: Optional[str] = Field(
        None,
        description=(
            "The model identifier in format 'provider/model'. "
            "If not provided, LCORE will automatically select an appropriate LLM model "
            "based on conversation history or available models."
        ),
        examples=["openai/gpt-4-turbo"],
    )
    conversation: Optional[str] = Field(
        None,
        description="The conversation ID, accepts OpenAI conv_* format or LCORE hex UUID",
        examples=["conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e", "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"],
    )
    include: Optional[List[IncludeParameter]] = Field(
        None,
        description="Include parameter",
    )
    instructions: Optional[str] = Field(
        None,
        description="System instructions (maps from system_prompt)",
        examples=["You are a helpful assistant"],
    )
    max_infer_iters: Optional[int] = Field(
        None,
        description="Maximum inference iterations",
    )
    max_tool_calls: Optional[int] = Field(
        None,
        description="Maximum tool calls",
    )
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary",
    )
    parallel_tool_calls: Optional[bool] = Field(
        None,
        description="Parallel tool calls flag",
    )
    previous_response_id: Optional[str] = Field(
        None,
        description="Previous response ID",
    )
    prompt: Optional[Prompt] = Field(
        None,
        description="OpenAI compatible Prompt object that is used in OpenAI responses",
    )
    store: bool = Field(
        default=True,
        description="Store flag",
    )
    stream: bool = Field(
        default=False,
        description="Stream flag",
    )
    temperature: Optional[float] = Field(
        None,
        description="Temperature parameter",
    )
    text: Optional[str] = Field(
        None,
        description="Text parameter",
    )
    tool_choice: Optional[ToolChoice] = Field(
        None,
        description="Constrains the tools available to the model to a pre-defined set",
    )
    tools: Optional[Iterable[Tool]] = Field(
        None,
        description="Tools list (includes vector_store_ids)",
    )
    generate_topic_summary: Optional[bool] = Field(
        None,
        description="LCORE-specific flag for generating topic summaries",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "input": "What is Kubernetes?",
                    "model": "openai/gpt-4o-mini",
                    "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                    "instructions": "You are a helpful assistant",
                    "store": True,
                    "stream": False,
                    "generate_topic_summary": True,
                }
            ]
        },
    }

    @model_validator(mode="after")
    def validate_conversation_and_previous_response_id_mutually_exclusive(self) -> Self:
        """
        Ensure `conversation` and `previous_response_id` are mutually exclusive.

        These two parameters cannot be provided together as they represent
        different ways of referencing conversation context.

        Raises:
            ValueError: If both `conversation` and `previous_response_id` are provided.

        Returns:
            Self: The validated model instance.
        """
        if self.conversation and self.previous_response_id:
            raise ValueError(
                "`conversation` and `previous_response_id` are mutually exclusive. "
                "Only one can be provided at a time."
            )
        return self

    @field_validator("conversation")
    @classmethod
    def validate_conversation_id(cls, value: Optional[str]) -> Optional[str]:
        """
        Validate that a conversation identifier matches the expected format.

        Accepts OpenAI format (conv_*) or LCORE hex UUID format.

        Parameters:
            value (Optional[str]): Conversation identifier to validate; may be None.

        Returns:
            Optional[str]: The original `value` if valid or `None` if not provided.

        Raises:
            ValueError: If `value` is provided and does not conform to the expected format.
        """
        if value and not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID '{value}'")
        return value


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
        """
        Validate that a conversation identifier conforms to the application's SUID format.

        Parameters:
            value (str): Conversation identifier to validate.

        Returns:
            str: The validated conversation identifier.

        Raises:
            ValueError: If `value` is not a valid SUID.
        """
        if not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID {value}")
        return value

    @field_validator("sentiment")
    @classmethod
    def check_sentiment(cls, value: Optional[int]) -> Optional[int]:
        """
        Validate a sentiment value is one of the allowed options.

        Parameters:
            value (Optional[int]): Sentiment value; must be -1, 1, or None.

        Returns:
            Optional[int]: The validated sentiment value.

        Raises:
            ValueError: If `value` is not -1, 1, or None.
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
        """
        Normalize and deduplicate a feedback categories list.

        Converts an empty list to None for consistency and removes duplicate
        categories while preserving their original order. If `value` is None,
        it is returned unchanged.

        Parameters:
            value (Optional[list[FeedbackCategory]]): List of feedback categories or None.

        Returns:
            Optional[list[FeedbackCategory]]: The normalized list with duplicates removed, or None.
        """
        if value is None:
            return value

        if len(value) == 0:
            return None  # Convert empty list to None for consistency

        unique_categories = list(dict.fromkeys(value))  # don't lose ordering
        return unique_categories

    @model_validator(mode="after")
    def check_feedback_provided(self) -> Self:
        """
        Ensure at least one form of feedback is provided.

        Raises:
            ValueError: If none of 'sentiment', 'user_feedback', or 'categories' are provided.

        Returns:
            Self: The validated FeedbackRequest instance.
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

    Example:
        ```python
        feedback_request = FeedbackRequest(
            status=false
        )
        ```
    """

    status: bool = Field(
        False,
        description="Desired state of feedback enablement, must be False or True",
        examples=[True, False],
    )

    # Reject unknown fields
    model_config = {"extra": "forbid"}

    def get_value(self) -> bool:
        """
        Get the desired feedback enablement status.

        Returns:
            bool: `true` if feedback is enabled, `false` otherwise.
        """
        return self.status


class ConversationUpdateRequest(BaseModel):
    """Model representing a request to update a conversation topic summary.

    Attributes:
        topic_summary: The new topic summary for the conversation.

    Example:
        ```python
        update_request = ConversationUpdateRequest(
            topic_summary="Discussion about machine learning algorithms"
        )
        ```
    """

    topic_summary: str = Field(
        ...,
        description="The new topic summary for the conversation",
        examples=["Discussion about machine learning algorithms"],
        min_length=1,
        max_length=1000,
    )

    # Reject unknown fields
    model_config = {"extra": "forbid"}


class ModelFilter(BaseModel):
    """Model representing a query parameter to select models by its type.

    Attributes:
        model_type: Required model type, such as 'llm', 'embeddings' etc.
    """

    model_config = {"extra": "forbid"}
    model_type: Optional[str] = Field(
        None,
        description="Optional filter to return only models matching this type",
        examples=["llm", "embeddings"],
    )
