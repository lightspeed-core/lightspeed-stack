"""Typed JSON bodies for SSE streaming events."""

from typing import Annotated, Literal, Optional, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from models.common import ReferencedDocument, ToolCallSummary, ToolResultSummary


class StreamPayloadBase(BaseModel):
    """Base for streaming SSE JSON payloads."""

    model_config = ConfigDict(extra="forbid")


class ErrorEventData(StreamPayloadBase):
    """Payload for event: "error"."""

    status_code: int
    response: str
    cause: str


class StartEventData(StreamPayloadBase):
    """Payload for event: "start"."""

    conversation_id: str
    request_id: str


class InterruptedEventData(StreamPayloadBase):
    """Payload for event: "interrupted"."""

    request_id: str


class EndEventData(StreamPayloadBase):
    """Nested data for event: "end"."""

    referenced_documents: list[ReferencedDocument]
    truncated: Optional[bool]
    input_tokens: int
    output_tokens: int


class ErrorStreamPayload(StreamPayloadBase):
    """SSE error event body (event + typed data)."""

    event: Literal["error"] = "error"
    data: ErrorEventData


class StartStreamPayload(StreamPayloadBase):
    """SSE stream start body."""

    event: Literal["start"] = "start"
    data: StartEventData


class InterruptedStreamPayload(StreamPayloadBase):
    """SSE interrupted stream body."""

    event: Literal["interrupted"] = "interrupted"
    data: InterruptedEventData


class EndStreamPayload(StreamPayloadBase):
    """SSE end-of-stream body (includes available_quotas beside data)."""

    event: Literal["end"] = "end"
    data: EndEventData
    available_quotas: dict[str, int]


class LlmTokenChunkData(StreamPayloadBase):
    """Structured data for token and turn-complete stream lines."""

    id: int
    token: str


class LlmTokenStreamPayload(StreamPayloadBase):
    """SSE token delta (event: "token")."""

    event: Literal["token"] = "token"
    data: LlmTokenChunkData


class LlmTurnCompleteStreamPayload(StreamPayloadBase):
    """SSE turn completion (same data shape as token)."""

    event: Literal["turn_complete"] = "turn_complete"
    data: LlmTokenChunkData


class LlmToolCallStreamPayload(StreamPayloadBase):
    """SSE tool call summary."""

    event: Literal["tool_call"] = "tool_call"
    data: ToolCallSummary


class LlmToolResultStreamPayload(StreamPayloadBase):
    """SSE tool result summary."""

    event: Literal["tool_result"] = "tool_result"
    data: ToolResultSummary


StreamLlmEventPayload: TypeAlias = Annotated[
    LlmTokenStreamPayload
    | LlmTurnCompleteStreamPayload
    | LlmToolCallStreamPayload
    | LlmToolResultStreamPayload
    | EndStreamPayload
    | ErrorStreamPayload
    | InterruptedStreamPayload
    | StartStreamPayload,
    Field(discriminator="event"),
]
