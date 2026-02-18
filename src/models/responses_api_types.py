"""Type definitions for Responses API input/output structures."""

# pylint: disable=line-too-long

from typing import Any, Dict, List, Literal, Optional, Union

from typing_extensions import Self, TypeAlias

from pydantic import BaseModel, field_validator, model_validator

from llama_stack_api.openai_responses import (
    OpenAIResponseInputFunctionToolCallOutput as FunctionToolCallOutput,
    OpenAIResponseMCPApprovalRequest as McpApprovalRequest,
    OpenAIResponseMCPApprovalResponse as McpApprovalResponse,
    OpenAIResponseMessage as MessageInput,
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchToolCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionToolCall,
    OpenAIResponseOutputMessageMCPCall as McpCall,
    OpenAIResponseOutputMessageMCPListTools as McpListTools,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchToolCall,
)
from llama_stack_client.types.response_create_params import (
    Prompt,
    Text,
    Tool,
    ToolChoice,
)
from llama_stack_client.types.response_object import Error, Output, Usage

from models.responses import AbstractSuccessfulResponse
from utils import suid

ResponseInputItem: TypeAlias = Union[
    MessageInput,
    WebSearchToolCall,
    FileSearchToolCall,
    FunctionToolCall,
    McpCall,
    McpListTools,
    McpApprovalRequest,
    FunctionToolCallOutput,
    McpApprovalResponse,
]

ResponseInput: TypeAlias = Union[
    str,
    List[ResponseInputItem],
]


IncludeParameter: TypeAlias = Literal[
    "web_search_call.action.sources",
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
    "reasoning.encrypted_content",
]


class ResponsesRequest(BaseModel):
    """Model representing a request for the Responses API following LCORE specification.

    Attributes:
        input: Input text (string) or list of message objects containing the query or conversation history.
        model: Model identifier in format 'provider/model'. Optional in LCORE - auto-selected if not provided.
        conversation: Conversation ID linking to an existing thread. Accepts OpenAI format (conv_*) or LCORE hex UUID.
        include: List of fields to include in the response (e.g., logprobs, image URLs, tool call sources).
        instructions: System instructions or guidelines provided to the model (acts as system prompt).
        max_infer_iters: Maximum number of inference iterations the model can perform.
        max_tool_calls: Maximum number of tool calls allowed in a single response.
        metadata: Custom metadata dictionary with key-value pairs for tracking or logging.
        parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
        previous_response_id: Identifier of the previous response in a multi-turn conversation. Mutually exclusive with conversation.
        prompt: Prompt object containing a template with variables for dynamic substitution.
        store: Whether to store the response in conversation history. Defaults to True.
        stream: Whether to stream the response as it's generated. Defaults to False.
        temperature: Sampling temperature controlling randomness (typically 0.0-2.0).
        text: Text response configuration object specifying output format constraints (JSON schema, JSON object, or plain text).
        tool_choice: Tool selection strategy ("auto", "required", "none", or specific tool configuration).
        tools: List of tools available to the model (file search, web search, function calls, MCP tools).
        generate_topic_summary: LCORE-specific flag indicating whether to generate a topic summary for new conversations.
    """

    input: ResponseInput
    model: Optional[str] = None
    conversation: Optional[str] = None
    include: Optional[List[IncludeParameter]] = None
    instructions: Optional[str] = None
    max_infer_iters: Optional[int] = None
    max_tool_calls: Optional[int] = None
    metadata: Optional[Dict[str, str]] = None
    parallel_tool_calls: Optional[bool] = None
    previous_response_id: Optional[str] = None
    prompt: Optional[Prompt] = None
    store: bool = True
    stream: bool = False
    temperature: Optional[float] = None
    text: Optional[Text] = None
    tool_choice: Optional[ToolChoice] = None
    tools: Optional[List[Tool]] = None
    generate_topic_summary: Optional[bool] = None

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "input": "What is Kubernetes?",
                    "model": "openai/gpt-4o-mini",
                    "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                    "instructions": "You are a helpful assistant",
                    "include": ["message.output_text.logprobs"],
                    "max_tool_calls": 5,
                    "metadata": {"source": "api"},
                    "parallel_tool_calls": True,
                    "prompt": {
                        "id": "prompt_123",
                        "variables": {
                            "topic": {"type": "input_text", "text": "Kubernetes"}
                        },
                        "version": "1.0",
                    },
                    "store": True,
                    "stream": False,
                    "temperature": 0.7,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "schema": {
                                "type": "object",
                                "properties": {"answer": {"type": "string"}},
                            },
                        }
                    },
                    "tool_choice": "auto",
                    "tools": [
                        {
                            "type": "file_search",
                            "vector_store_ids": ["vs_123"],
                        }
                    ],
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
    def check_suid(cls, value: Optional[str]) -> Optional[str]:
        """Validate that a conversation identifier matches the expected SUID format."""
        if value and not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID '{value}'")
        return value

    def get_mirrored_params(self) -> Dict[str, Any]:
        """
        Get request parameters that should be mirrored in the response.

        Returns a dictionary of request parameters that are included in both
        ResponsesRequest and ResponsesResponse. These parameters represent
        the configuration used for generation and should be echoed back
        in the response for transparency and debugging purposes.
        """
        return self.model_dump(
            include={
                "model",
                "instructions",
                "max_tool_calls",
                "metadata",
                "parallel_tool_calls",
                "previous_response_id",
                "prompt",
                "temperature",
                "text",
                "tool_choice",
                "tools",
                # "top_p",
                # "truncation",
                "conversation",
            },
            exclude_none=True,
        )


class ResponsesResponse(AbstractSuccessfulResponse):
    """Model representing a response from the Responses API following LCORE specification.

    Attributes:
        id: Unique identifier for this response.
        object: Object type identifier, always "response".
        created_at: Unix timestamp when the response was created.
        status: Current status of the response (e.g., "completed", "blocked", "in_progress").
        completed_at: Unix timestamp when the response was completed (if completed).
        model: Model identifier in "provider/model" format used for generation.
        output: List of structured output items containing messages, tool calls, and other content.
            This is the primary response content.
        error: Error details if the response failed or was blocked.
        instructions: System instructions or guidelines provided to the model.
        max_tool_calls: Maximum number of tool calls allowed in a single response.
        metadata: Additional metadata dictionary with custom key-value pairs.
        parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
        previous_response_id: Identifier of the previous response in a multi-turn conversation.
        prompt: The input prompt object that was sent to the model.
        temperature: Temperature parameter used for generation (controls randomness).
        text: Text response configuration object used for OpenAI responses.
        tool_choice: Tool selection strategy used (e.g., "auto", "required", "none").
        tools: List of tools available to the model during generation.
        top_p: Top-p sampling parameter used for generation.
        truncation: Strategy used for handling content that exceeds context limits.
        usage: Token usage statistics including input_tokens, output_tokens, and total_tokens.
        conversation: Conversation ID linking this response to a conversation thread (LCORE-specific).
        available_quotas: Remaining token quotas for the user (LCORE-specific).
        output_text: Aggregated text output from all output_text items in the output array.
    """

    id: str
    object: Literal["response"] = "response"
    created_at: int
    status: str
    completed_at: Optional[int] = None
    model: str
    output: List[Output]
    error: Optional[Error] = None
    instructions: Optional[str] = None
    max_tool_calls: Optional[int] = None
    metadata: Optional[dict[str, str]] = None
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    prompt: Optional[Prompt] = None
    temperature: Optional[float] = None
    text: Optional[Text] = None
    tool_choice: Optional[ToolChoice] = None
    tools: Optional[List[Tool]] = None
    top_p: Optional[float] = None
    truncation: Optional[str] = None
    usage: Usage
    conversation: Optional[str] = None
    available_quotas: dict[str, int]
    output_text: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "resp_abc123",
                    "object": "response",
                    "created_at": 1704067200,
                    "completed_at": 1704067250,
                    "model": "openai/gpt-4-turbo",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Kubernetes is an open-source container orchestration system...",
                                }
                            ],
                        }
                    ],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                    },
                    "instructions": "You are a helpful assistant",
                    "temperature": 0.7,
                    "conversation": "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                    "available_quotas": {"daily": 1000, "monthly": 50000},
                    "output_text": "Kubernetes is an open-source container orchestration system...",
                }
            ]
        }
    }
