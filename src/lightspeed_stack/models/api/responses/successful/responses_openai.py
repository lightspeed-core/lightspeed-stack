"""Successful response model for the OpenAI-compatible Responses API."""

from typing import Any, Literal, Optional, cast

from llama_stack_api.openai_responses import (
    OpenAIResponseError as Error,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutput as Output,
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
from llama_stack_api.openai_responses import (
    OpenAIResponseTool as OutputTool,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseUsage as Usage,
)

from models.api.responses.constants import SUCCESSFUL_RESPONSE_DESCRIPTION
from models.api.responses.successful.bases import AbstractSuccessfulResponse


class ResponsesResponse(AbstractSuccessfulResponse):
    """Model representing a response from the Responses API following LCORE specification.

    Attributes:
        created_at: Unix timestamp when the response was created.
        completed_at: Unix timestamp when the response was completed, if applicable.
        error: Error details if the response failed or was blocked.
        id: Unique identifier for this response.
        model: Model identifier in "provider/model" format used for generation.
        object: Object type identifier, always "response".
        output: List of structured output items containing messages, tool calls, and
            other content. This is the primary response content.
        parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
        previous_response_id: Identifier of the previous response in a multi-turn
            conversation.
        prompt: The input prompt object that was sent to the model.
        status: Current status of the response (e.g., "completed", "blocked",
            "in_progress").
        temperature: Temperature parameter used for generation (controls randomness).
        text: Text response configuration object used for OpenAI responses.
        top_p: Top-p sampling parameter used for generation.
        tools: List of tools available to the model during generation.
        tool_choice: Tool selection strategy used (e.g., "auto", "required", "none").
        truncation: Strategy used for handling content that exceeds context limits.
        usage: Token usage statistics including input_tokens, output_tokens, and
            total_tokens.
        instructions: System instructions or guidelines provided to the model.
        max_tool_calls: Maximum number of tool calls allowed in a single response.
        reasoning: Reasoning configuration (effort level) used for the response.
        max_output_tokens: Upper bound for tokens generated in the response.
        safety_identifier: Safety/guardrail identifier applied to the request.
        metadata: Additional metadata dictionary with custom key-value pairs.
        store: Whether the response was stored.
        conversation: Conversation ID linking this response to a conversation thread
            (LCORE-specific).
        available_quotas: Remaining token quotas for the user (LCORE-specific).
        output_text: Aggregated text output from all output_text items in the
            output array.
    """

    created_at: int
    completed_at: Optional[int] = None
    error: Optional[Error] = None
    id: str
    model: str
    object: Literal["response"] = "response"
    output: list[Output]
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    prompt: Optional[Prompt] = None
    status: str
    temperature: Optional[float] = None
    text: Optional[Text] = None
    top_p: Optional[float] = None
    tools: Optional[list[OutputTool]] = None
    tool_choice: Optional[ToolChoice] = None
    truncation: Optional[str] = None
    usage: Optional[Usage] = None
    instructions: Optional[str] = None
    max_tool_calls: Optional[int] = None
    reasoning: Optional[Reasoning] = None
    max_output_tokens: Optional[int] = None
    safety_identifier: Optional[str] = None
    metadata: Optional[dict[str, str]] = None
    store: Optional[bool] = None
    # LCORE-specific attributes
    conversation: Optional[str] = None
    available_quotas: dict[str, int]
    output_text: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "created_at": 1704067200,
                    "completed_at": 1704067250,
                    "id": "resp_abc123",
                    "model": "openai/gpt-4-turbo",
                    "object": "response",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": (
                                        "Kubernetes is an open-source container "
                                        "orchestration system..."
                                    ),
                                }
                            ],
                        }
                    ],
                    "parallel_tool_calls": True,
                    "status": "completed",
                    "temperature": 0.7,
                    "text": {"format": {"type": "text"}},
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                    "instructions": "You are a helpful assistant",
                    "store": True,
                    "conversation": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                    "available_quotas": {"daily": 1000, "monthly": 50000},
                    "output_text": (
                        "Kubernetes is an open-source container orchestration system..."
                    ),
                }
            ],
            "sse_example": (
                "event: response.created\n"
                'data: {"type":"response.created","sequence_number":0,'
                '"response":{"id":"resp_abc","object":"response",'
                '"created_at":1704067200,"status":"in_progress","model":"openai/gpt-4o-mini",'
                '"output":[],"store":true,"text":{"format":{"type":"text"}},'
                '"conversation":"0d21ba731f21f798dc9680125d5d6f49",'
                '"available_quotas":{},"output_text":""}}\n\n'
                "event: response.output_item.added\n"
                'data: {"type":"response.output_item.added","sequence_number":1,'
                '"response_id":"resp_abc","output_index":0,'
                '"item":{"id":"msg_abc","type":"message","status":"in_progress",'
                '"role":"assistant","content":[]}}\n\n'
                "...\n\n"
                "event: response.completed\n"
                'data: {"type":"response.completed","sequence_number":30,'
                '"response":{"id":"resp_abc","object":"response",'
                '"created_at":1704067200,"status":"completed","model":"openai/gpt-4o-mini",'
                '"output":[{"id":"msg_abc","type":"message","status":"completed",'
                '"role":"assistant","content":[{"type":"output_text",'
                '"text":"Hello! How can I help?","annotations":[]}]}],'
                '"store":true,"text":{"format":{"type":"text"}},'
                '"usage":{"input_tokens":10,"output_tokens":6,"total_tokens":16,'
                '"input_tokens_details":{"cached_tokens":0},'
                '"output_tokens_details":{"reasoning_tokens":0}},'
                '"conversation":"0d21ba731f21f798dc9680125d5d6f49",'
                '"available_quotas":{"daily":1000,"monthly":50000},'
                '"output_text":"Hello! How can I help?"}}\n\n'
                "data: [DONE]\n\n"
            ),
        }
    }

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """
        Build OpenAPI response dict with application/json and text/event-stream.

        Uses the single JSON example from the model schema and adds
        text/event-stream example from json_schema_extra.sse_example.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples", [])
        json_example = model_examples[0] if model_examples else None

        schema_extra = (
            cast(dict[str, Any], dict(cls.model_config)).get("json_schema_extra") or {}
        )
        sse_example = schema_extra.get("sse_example", "")

        content: dict[str, Any] = {
            "application/json": {"example": json_example} if json_example else {},
            "text/event-stream": {
                "schema": {"type": "string"},
                "example": sse_example,
            },
        }

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": content,
        }
