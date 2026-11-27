"""Completed or in-progress response returned by the API."""

from collections.abc import Sequence
from typing import Literal, Optional

from pydantic import BaseModel

from responses.models.config import (
    ResponseError,
    ResponsePrompt,
    ResponseReasoning,
    ResponseText,
    ResponseUsage,
)
from responses.models.items import ResponseOutput
from responses.models.tools import OutputTool, ToolChoice


class ResponseObject(BaseModel):
    """A response, including output items, usage, and request echo fields."""

    created_at: int
    completed_at: Optional[int] = None
    error: Optional[ResponseError] = None
    id: str
    model: str
    object: Literal["response"] = "response"
    output: Sequence[ResponseOutput]
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    prompt_cache_key: Optional[str] = None
    prompt: Optional[ResponsePrompt] = None
    status: str
    temperature: Optional[float] = None
    text: Optional[ResponseText] = None
    top_p: Optional[float] = None
    tools: Optional[Sequence[OutputTool]] = None
    tool_choice: Optional[ToolChoice] = None
    truncation: Optional[str] = None
    usage: Optional[ResponseUsage] = None
    instructions: Optional[str] = None
    max_tool_calls: Optional[int] = None
    reasoning: Optional[ResponseReasoning] = None
    max_output_tokens: Optional[int] = None
    safety_identifier: Optional[str] = None
    metadata: Optional[dict[str, str]] = None
    store: Optional[bool] = None
    conversation: Optional[str] = None
    available_quotas: dict[str, int]
    output_text: str
