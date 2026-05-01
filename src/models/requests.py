"""Models for REST API requests."""

# pylint: disable=too-many-lines

import json
from enum import Enum
from typing import Any, Literal, Optional, Self

from llama_stack_api.openai_responses import (
    OpenAIResponseInputTool as InputTool,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from llama_stack_api.openai_responses import (
    OpenAIResponsePrompt as Prompt,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseText as Text,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from constants import (
    MCP_AUTH_CLIENT,
    MCP_AUTH_KUBERNETES,
    MCP_AUTH_OAUTH,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
    RESPONSES_REQUEST_MAX_SIZE,
    SOLR_VECTOR_SEARCH_DEFAULT_MODE,
)
from log import get_logger
from utils import suid
from utils.types import IncludeParameter, ResponseInput

logger = get_logger(__name__)

# Attribute names that are echoed back in the response.
_ECHOED_FIELDS = set(
    {
        "instructions",
        "max_tool_calls",
        "max_output_tokens",
        "metadata",
        "model",
        "parallel_tool_calls",
        "previous_response_id",
        "prompt",
        "reasoning",
        "safety_identifier",
        "temperature",
        "top_p",
        "truncation",
        "text",
        "tool_choice",
        "store",
    }
)


class Attachment(BaseModel):
    """Model representing an attachment that can be sent from the UI as part of query.

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


class SolrVectorSearchRequest(BaseModel):
    """LCORE Solr inline RAG options for ``vector_io.query`` (mode and provider filters).

    Attributes:
        mode: Solr vector_io search mode. When omitted, the server default (hybrid) is used.
        filters: Solr provider filter payload passed through as params['solr'].

    Legacy clients may send a plain JSON object with filter keys only;
    that object is accepted as filters with mode unset (server default applies).
    """

    model_config = ConfigDict(extra="forbid")

    mode: Optional[Literal["semantic", "hybrid", "lexical"]] = Field(
        None,
        description=(
            "Solr vector_io search mode. When omitted, the server default "
            f"({SOLR_VECTOR_SEARCH_DEFAULT_MODE!r}) is used."
        ),
        examples=["hybrid", "semantic", "lexical"],
    )
    filters: Optional[dict[str, Any]] = Field(
        None,
        description="Solr provider filter payload passed through as params['solr'].",
        examples=[{"fq": ["product:*openshift*", "product_version:*4.16*"]}],
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_plain_dict(cls, data: Any) -> Any:
        """Treat a legacy top-level filter dict as filters (backward compatibility).

        Args:
            data: Raw JSON, typically a dict or None.

        Returns:
            Normalized dict for Pydantic model validation, or the original non-dict value.
        """
        if data is None or not isinstance(data, dict):
            return data
        if "filters" in data or "mode" in data:
            return data
        logger.warning(
            "Solr inline RAG: sending filter fields at the top level of `solr` without "
            "`mode` or `filters` is deprecated and will be removed; use "
            '`{"mode": "<semantic|hybrid|lexical>", "filters": {...}}` instead.'
        )
        return {"mode": None, "filters": data}


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
        shield_ids: The optional list of safety shield IDs to apply.
        solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.

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

    shield_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of safety shield IDs to apply. "
        "If None, all configured shields are used. ",
        examples=["llama-guard", "custom-shield"],
    )

    solr: Optional[SolrVectorSearchRequest] = Field(
        None,
        description=(
            "Solr inline RAG config: mode (semantic, hybrid, lexical) and filters; "
            "a legacy filter-only object (e.g. fq) is still accepted."
        ),
        examples=[
            {"mode": "hybrid", "filters": {"fq": ["product:*openshift*"]}},
            {"filters": {"fq": ["product:*openshift*", "product_version:*4.16*"]}},
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
        ----------
            value (Optional[str]): Conversation identifier to validate; may be None.

        Returns:
        -------
            Optional[str]: The original `value` if valid or `None` if not provided.

        Raises:
        ------
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


class StreamingInterruptRequest(BaseModel):
    """Model representing a request to interrupt an active streaming query.

    Attributes:
        request_id: Unique ID of the active streaming request to interrupt.
    """

    request_id: str = Field(
        description="The active streaming request ID to interrupt",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {"request_id": "123e4567-e89b-12d3-a456-426614174000"},
            ]
        },
    }

    @field_validator("request_id")
    @classmethod
    def check_request_id(cls, value: str) -> str:
        """Validate that request identifier matches expected SUID format.

        Parameters:
        ----------
            value: Request identifier submitted by the caller.

        Returns:
        -------
            str: The validated request identifier.

        Raises:
        ------
            ValueError: If the request identifier is not a valid SUID.
        """
        if not suid.check_suid(value):
            raise ValueError(f"Improper request ID {value}")
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
        ----------
            value (str): Conversation identifier to validate.

        Returns:
        -------
            str: The validated conversation identifier.

        Raises:
        ------
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
        ----------
            value (Optional[int]): Sentiment value; must be -1, 1, or None.

        Returns:
        -------
            Optional[int]: The validated sentiment value.

        Raises:
        ------
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
        ----------
            value (Optional[list[FeedbackCategory]]): List of feedback categories or None.

        Returns:
        -------
            Optional[list[FeedbackCategory]]: The normalized list with duplicates removed, or None.
        """
        if value is None:
            return value

        if len(value) == 0:
            return None  # Convert empty list to None for consistency

        return list(dict.fromkeys(value))  # don't lose ordering

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


class ResponsesRequest(BaseModel):
    """Model representing a request for the Responses API following LCORE specification.

    Attributes:
        input: Input text or structured input items containing the query.
        model: Model identifier in format "provider/model". Auto-selected if not provided.
        conversation: Conversation ID linking to an existing conversation. Accepts both
            OpenAI and LCORE formats. Mutually exclusive with previous_response_id.
        include: Explicitly specify output item types that are excluded by default but
            should be included in the response.
        instructions: System instructions or guidelines provided to the model (acts as
            the system prompt).
        max_infer_iters: Maximum number of inference iterations the model can perform.
        max_output_tokens: Maximum number of tokens allowed in the response.
        max_tool_calls: Maximum number of tool calls allowed in a single response.
        metadata: Custom metadata dictionary with key-value pairs for tracking or logging.
        parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
        previous_response_id: Identifier of the previous response in a multi-turn
            conversation. Mutually exclusive with conversation.
        prompt: Prompt object containing a template with variables for dynamic
            substitution.
        reasoning: Reasoning configuration for the response.
        safety_identifier: Safety identifier for the response.
        store: Whether to store the response in conversation history. Defaults to True.
        stream: Whether to stream the response as it is generated. Defaults to False.
        temperature: Sampling temperature controlling randomness (typically 0.0–2.0).
        text: Text response configuration specifying output format constraints (JSON
            schema, JSON object, or plain text).
        tool_choice: Tool selection strategy ("auto", "required", "none", or specific
            tool configuration).
        tools: List of tools available to the model (file search, web search, function
            calls, MCP tools). Defaults to all tools available to the model.
        generate_topic_summary: LCORE-specific flag indicating whether to generate a
            topic summary for new conversations. Defaults to True.
        shield_ids: LCORE-specific list of safety shield IDs to apply. If None, all
            configured shields are used.
        solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.
    """

    input: ResponseInput
    model: Optional[str] = None
    conversation: Optional[str] = None
    include: Optional[list[IncludeParameter]] = None
    instructions: Optional[str] = None
    max_infer_iters: Optional[int] = None
    max_output_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    metadata: Optional[dict[str, str]] = None
    parallel_tool_calls: Optional[bool] = None
    previous_response_id: Optional[str] = None
    prompt: Optional[Prompt] = None
    reasoning: Optional[Reasoning] = None
    safety_identifier: Optional[str] = None
    store: bool = True
    stream: bool = False
    temperature: Optional[float] = None
    text: Optional[Text] = None
    tool_choice: Optional[ToolChoice] = None
    tools: Optional[list[InputTool]] = None
    # LCORE-specific attributes
    generate_topic_summary: Optional[bool] = True
    shield_ids: Optional[list[str]] = None
    solr: Optional[SolrVectorSearchRequest] = None

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "input": "Hello World!",
                    "model": "openai/gpt-4o-mini",
                    "instructions": "You are a helpful assistant",
                    "store": True,
                    "stream": False,
                    "generate_topic_summary": True,
                }
            ]
        },
    }

    @model_validator(mode="before")
    @classmethod
    def validate_body_size(cls, values: Any) -> Any:
        """Validate that the request body does not exceed the maximum allowed size.

        Serializes the raw request payload to JSON and checks the total character
        count against the 65,536-character limit.  This guard runs before field
        coercion so that the limit reflects only what the client actually sent,
        not the expanded representation produced by Pydantic's defaults.

        Parameters:
            values: The raw input dict (or other object) passed to the model.

        Returns:
            Any: ``values`` unchanged when the size check passes.

        Raises:
            ValueError: If the JSON-serialized size of ``values`` exceeds
                65,536 characters.
        """
        try:
            serialized = json.dumps(values)
        except (TypeError, ValueError):
            # Non-JSON-serializable payload (e.g. programmatic use with Pydantic
            # model instances).  The size guard only applies to wire-format HTTP
            # requests which FastAPI always parses into JSON-compatible dicts.
            return values
        if len(serialized) > RESPONSES_REQUEST_MAX_SIZE:
            raise ValueError(
                f"Request body size ({len(serialized)} characters) exceeds maximum "
                f"allowed size of {RESPONSES_REQUEST_MAX_SIZE} characters"
            )
        return values

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
    def check_suid(cls, value: Optional[str]) -> Optional[str]:
        """Validate that a conversation identifier matches the expected SUID format."""
        if value and not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID '{value}'")
        return value

    @field_validator("previous_response_id")
    @classmethod
    def check_previous_response_id(cls, value: Optional[str]) -> Optional[str]:
        """Validate that previous_response_id does not start with 'modr'."""
        if value is not None and value.startswith("modr"):
            raise ValueError("You cannot provide context by moderation response.")
        return value


class MCPServerRegistrationRequest(BaseModel):
    """Request model for dynamically registering an MCP server.

    Attributes:
        name: Unique name for the MCP server.
        url: URL of the MCP server endpoint.
        provider_id: MCP provider identification (defaults to "model-context-protocol").
        authorization_headers: Optional headers to send to the MCP server.
        headers: Optional list of HTTP header names to forward from incoming requests.
        timeout: Optional request timeout in seconds.

    Example:
        ```python
        request = MCPServerRegistrationRequest(
            name="my-tools",
            url="http://localhost:8888/mcp",
        )
        ```
    """

    name: str = Field(
        ...,
        description="Unique name for the MCP server",
        examples=["my-mcp-tools"],
        min_length=1,
        max_length=256,
    )

    url: str = Field(
        ...,
        description="URL of the MCP server endpoint",
        examples=["http://host.docker.internal:7008/api/mcp-actions/v1"],
    )

    provider_id: str = Field(
        "model-context-protocol",
        description="MCP provider identification",
        examples=["model-context-protocol"],
    )

    authorization_headers: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Headers to send to the MCP server. Values must be one of the "
            "supported token resolution keywords: "
            "'client' - forward the caller's token provided via MCP-HEADERS, "
            "'kubernetes' - use the authenticated user's Kubernetes token, "
            "'oauth' - use an OAuth token provided via MCP-HEADERS. "
            "File-path based secrets (used in static YAML config) are not "
            "supported for dynamically registered servers."
        ),
        examples=[
            {"Authorization": "client"},
            {"Authorization": "kubernetes"},
            {"Authorization": "oauth"},
        ],
    )

    headers: Optional[list[str]] = Field(
        default=None,
        description="List of HTTP header names to forward from incoming requests",
        examples=[["x-rh-identity"]],
    )

    timeout: Optional[int] = Field(
        default=None,
        description="Request timeout in seconds for the MCP server",
        gt=0,
        examples=[30],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "mcp-integration-tools",
                    "url": "http://host.docker.internal:7008/api/mcp-actions/v1",
                    "authorization_headers": {"Authorization": "client"},
                },
                {
                    "name": "k8s-internal-service",
                    "url": "http://internal-mcp.default.svc.cluster.local:8080",
                    "authorization_headers": {"Authorization": "kubernetes"},
                },
                {
                    "name": "oauth-mcp-server",
                    "url": "https://mcp.example.com/api",
                    "authorization_headers": {"Authorization": "oauth"},
                },
                {
                    "name": "test-mcp-server",
                    "url": "http://host.docker.internal:8888/mcp",
                    "provider_id": "model-context-protocol",
                    "headers": ["x-rh-identity"],
                    "timeout": 30,
                },
            ]
        },
    }

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Validate that URL uses http or https scheme.

        Parameters:
        ----------
            value: The URL string to validate.

        Returns:
        -------
            The validated URL string.

        Raises:
        ------
            ValueError: If URL does not start with http:// or https://.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must use http:// or https:// scheme")
        return value

    @field_validator("authorization_headers")
    @classmethod
    def validate_authorization_header_values(
        cls, value: Optional[dict[str, str]]
    ) -> Optional[dict[str, str]]:
        """Validate that authorization header values use supported keywords.

        Dynamic registration only supports the token resolution keywords
        ('client', 'kubernetes', 'oauth'). File-path based secrets are
        rejected since the API client cannot guarantee files exist on the
        server filesystem.

        Parameters:
        ----------
            value: The authorization headers dict to validate.

        Returns:
        -------
            The validated authorization headers dict.

        Raises:
        ------
            ValueError: If any header value is not a supported keyword.
        """
        if value is None:
            return value
        allowed = {MCP_AUTH_CLIENT, MCP_AUTH_KUBERNETES, MCP_AUTH_OAUTH}
        for header_name, header_value in value.items():
            stripped = header_value.strip()
            if stripped not in allowed:
                raise ValueError(
                    f"Authorization header '{header_name}' has unsupported value "
                    f"'{stripped}'. Dynamic registration only supports: "
                    f"{', '.join(sorted(allowed))}. "
                    "File-path based secrets are only supported in static YAML config."
                )
        return value


class VectorStoreCreateRequest(BaseModel):
    """Model representing a request to create a vector store.

    Attributes:
        name: Name of the vector store.
        embedding_model: Optional embedding model to use.
        embedding_dimension: Optional embedding dimension.
        chunking_strategy: Optional chunking strategy configuration.
        provider_id: Optional vector store provider identifier.
        metadata: Optional metadata dictionary for storing session information.
    """

    name: str = Field(
        ...,
        description="Name of the vector store",
        examples=["my_vector_store"],
        min_length=1,
        max_length=256,
    )

    embedding_model: Optional[str] = Field(
        None,
        description="Embedding model to use for the vector store",
        examples=["text-embedding-ada-002"],
    )

    embedding_dimension: Optional[int] = Field(
        None,
        description="Dimension of the embedding vectors",
        examples=[1536],
        gt=0,
    )

    chunking_strategy: Optional[dict[str, Any]] = Field(
        None,
        description="Chunking strategy configuration",
        examples=[{"type": "fixed", "chunk_size": 512, "chunk_overlap": 50}],
    )

    provider_id: Optional[str] = Field(
        None,
        description="Vector store provider identifier",
        examples=["rhdh-docs"],
    )

    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary for storing session information",
        examples=[{"user_id": "user123", "session_id": "sess456"}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "my_vector_store",
                    "embedding_model": "text-embedding-ada-002",
                    "embedding_dimension": 1536,
                    "provider_id": "rhdh-docs",
                    "metadata": {"user_id": "user123"},
                },
            ]
        },
    }


class VectorStoreUpdateRequest(BaseModel):
    """Model representing a request to update a vector store.

    Attributes:
        name: New name for the vector store.
        expires_at: Optional expiration timestamp.
        metadata: Optional metadata dictionary for storing session information.
    """

    name: Optional[str] = Field(
        None,
        description="New name for the vector store",
        examples=["updated_vector_store"],
        min_length=1,
        max_length=256,
    )

    expires_at: Optional[int] = Field(
        None,
        description="Unix timestamp when the vector store should expire",
        examples=[1735689600],
        gt=0,
    )

    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary for storing session information",
        examples=[{"user_id": "user123", "session_id": "sess456"}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "updated_vector_store",
                    "expires_at": 1735689600,
                    "metadata": {"user_id": "user123"},
                },
            ]
        },
    }

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        """Ensure at least one field is provided for update.

        Raises:
            ValueError: If all fields are None (empty update).

        Returns:
            Self: The validated model instance.
        """
        if self.name is None and self.expires_at is None and self.metadata is None:
            raise ValueError(
                "At least one field must be provided: name, expires_at, or metadata"
            )
        return self


class VectorStoreFileCreateRequest(BaseModel):
    """Model representing a request to add a file to a vector store.

    Attributes:
        file_id: ID of the file to add to the vector store.
        attributes: Optional metadata key-value pairs (max 16 pairs).
        chunking_strategy: Optional chunking strategy configuration.
    """

    file_id: str = Field(
        ...,
        description="ID of the file to add to the vector store",
        examples=["file-abc123"],
        min_length=1,
    )

    attributes: Optional[dict[str, str | float | bool]] = Field(
        None,
        description=(
            "Set of up to 16 key-value pairs for storing additional information. "
            "Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers."
        ),
        examples=[
            {"created_at": "2026-04-04T15:20:00Z", "updated_at": "2026-04-04T15:20:00Z"}
        ],
    )

    chunking_strategy: Optional[dict[str, Any]] = Field(
        None,
        description="Chunking strategy configuration for this file",
        examples=[{"type": "fixed", "chunk_size": 512, "chunk_overlap": 50}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "file-abc123",
                    "attributes": {"created_at": "2026-04-04T15:20:00Z"},
                    "chunking_strategy": {"type": "fixed", "chunk_size": 512},
                },
            ]
        },
    }

    @field_validator("attributes")
    @classmethod
    def validate_attributes(
        cls, value: Optional[dict[str, str | float | bool]]
    ) -> Optional[dict[str, str | float | bool]]:
        """Validate attributes field constraints.

        Ensures:
        - Maximum 16 key-value pairs
        - Keys are max 64 characters
        - String values are max 512 characters

        Parameters:
            value: The attributes dictionary to validate.

        Raises:
            ValueError: If constraints are violated.

        Returns:
            The validated attributes dictionary.
        """
        if value is None:
            return value

        if len(value) > 16:
            raise ValueError(f"attributes can have at most 16 pairs, got {len(value)}")

        for key, val in value.items():
            if len(key) > 64:
                raise ValueError(f"attribute key '{key}' exceeds 64 characters")

            if isinstance(val, str) and len(val) > 512:
                raise ValueError(f"attribute value for '{key}' exceeds 512 characters")

        return value


class PromptCreateRequest(BaseModel):
    """Request body to create a stored prompt template in Llama Stack."""

    prompt: str = Field(
        ...,
        description="Prompt text with variable placeholders",
        examples=["Summarize: {{text}}"],
        min_length=1,
    )
    variables: Optional[list[str]] = Field(
        None,
        description="Variable names allowed in the template",
        examples=[["text"]],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Summarize: {{text}}",
                    "variables": ["text"],
                }
            ]
        },
    }


class PromptUpdateRequest(BaseModel):
    """Request body to update a stored prompt (creates a new version)."""

    prompt: str = Field(
        ...,
        description="Updated prompt text",
        examples=["Summarize in bullet points: {{text}}"],
        min_length=1,
    )
    version: int = Field(
        ...,
        description="Current version being updated",
        examples=[1],
        gt=0,
    )
    set_as_default: Optional[bool] = Field(
        None,
        description="Whether the new version becomes the default",
        examples=[True],
    )
    variables: Optional[list[str]] = Field(
        None,
        description="Updated allowed variable names",
        examples=[["text"]],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Summarize in bullet points: {{text}}",
                    "version": 1,
                    "set_as_default": True,
                    "variables": ["text"],
                }
            ]
        },
    }
