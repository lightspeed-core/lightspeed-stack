"""Messages, tool calls, approvals, and reasoning items."""

from collections.abc import Sequence
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field

from responses.models.content import (
    InputMessageContent,
    OutputMessageContent,
)


class ResponseMessage(BaseModel):
    """A message from the system, developer, user, or assistant."""

    type: Literal["message"] = "message"
    role: Literal["system", "developer", "user", "assistant"]
    content: str | Sequence[InputMessageContent] | Sequence[OutputMessageContent]
    id: Optional[str] = None
    status: Optional[str] = None


class FileSearchToolCallResult(BaseModel):
    """One chunk returned by file search."""

    attributes: Optional[dict[str, Any]] = None
    file_id: Optional[str] = None
    filename: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None


class FileSearchToolCall(BaseModel):
    """A file search the model ran."""

    type: Literal["file_search_call"] = "file_search_call"
    id: str
    queries: Sequence[str]
    status: str
    results: Optional[Sequence[FileSearchToolCallResult]] = None


class FunctionToolCall(BaseModel):
    """A function the model wants the client to run."""

    type: Literal["function_call"] = "function_call"
    call_id: str
    name: str
    arguments: str
    id: Optional[str] = None
    status: Optional[str] = None


class FunctionToolCallOutput(BaseModel):
    """Result of a function the client already ran."""

    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: str | list[InputMessageContent]
    id: Optional[str] = None
    status: Optional[str] = None


class McpCall(BaseModel):
    """An MCP tool call the model made."""

    type: Literal["mcp_call"] = "mcp_call"
    id: str
    arguments: str
    name: str
    server_label: str
    error: Optional[str] = None
    output: Optional[str] = None


class McpListToolsTool(BaseModel):
    """One tool advertised by an MCP server."""

    input_schema: dict[str, Any]
    name: str
    description: Optional[str] = None


class McpListTools(BaseModel):
    """Tools listed by an MCP server."""

    type: Literal["mcp_list_tools"] = "mcp_list_tools"
    id: str
    server_label: str
    tools: list[McpListToolsTool]


class McpApprovalRequest(BaseModel):
    """Request for a person to approve an MCP tool call."""

    type: Literal["mcp_approval_request"] = "mcp_approval_request"
    arguments: str
    id: str
    name: str
    server_label: str


class McpApprovalResponse(BaseModel):
    """Approval or denial of an MCP tool call."""

    type: Literal["mcp_approval_response"] = "mcp_approval_response"
    approval_request_id: str
    approve: bool
    id: Optional[str] = None
    reason: Optional[str] = None


class ReasoningSummary(BaseModel):
    """Short summary of model reasoning."""

    type: Literal["summary_text"] = "summary_text"
    text: str


class ReasoningContent(BaseModel):
    """Reasoning text from the model."""

    type: Literal["reasoning_text"] = "reasoning_text"
    text: str


class ReasoningItem(BaseModel):
    """Reasoning the model produced while generating a response."""

    type: Literal["reasoning"] = "reasoning"
    id: str
    summary: list[ReasoningSummary]
    content: Optional[list[ReasoningContent]] = None
    status: Optional[Literal["in_progress", "completed", "incomplete"]] = None


ResponseOutput = Annotated[
    ResponseMessage
    | FileSearchToolCall
    | FunctionToolCall
    | McpCall
    | McpListTools
    | McpApprovalRequest
    | ReasoningItem,
    Field(discriminator="type"),
]

ResponseItem = Annotated[
    ResponseMessage
    | FileSearchToolCall
    | FunctionToolCallOutput
    | McpCall
    | McpListTools
    | McpApprovalRequest
    | FunctionToolCall
    | McpApprovalResponse
    | ReasoningItem,
    Field(discriminator="type"),
]

type ResponseInput = str | list[ResponseItem]

type IncludeParameter = Literal[
    "file_search_call.results",
    "message.output_text.logprobs",
]
