"""Request model for the OpenAI-compatible Responses API."""

import json
from typing import Any, Optional, Self

from ogx_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from ogx_api.openai_responses import (
    OpenAIResponsePrompt as Prompt,
)
from ogx_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from ogx_api.openai_responses import (
    OpenAIResponseText as Text,
)
from pydantic import BaseModel, field_validator, model_validator

from constants import RESPONSES_REQUEST_MAX_SIZE
from models.common.query import SolrVectorSearchRequest
from models.common.responses.types import IncludeParameter, InputTool, ResponseInput
from utils import suid


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
