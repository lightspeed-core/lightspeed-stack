"""Typed JSON bodies for SSE streaming events."""

import json
from typing import Annotated, Literal, Optional, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from lightspeed_stack.models.api.responses.error import AbstractErrorResponse
from lightspeed_stack.models.common import ReferencedDocument, ToolCallSummary, ToolResultSummary


class StreamPayloadBase(BaseModel):
    """Base for streaming SSE JSON payloads."""

    model_config = ConfigDict(extra="forbid")

    def serialize_json(self) -> str:
        """Format this payload as an SSE ``data:`` line."""
        return f"data: {json.dumps(self.model_dump(mode='json'))}\n\n"

    def serialize_text(self) -> str:
        """Format this payload as plain text for text media type clients."""
        return ""


class ErrorEventData(BaseModel):
    """Payload for event: "error"."""

    status_code: int
    response: str
    cause: str


class StartEventData(BaseModel):
    """Payload for event: "start"."""

    conversation_id: str
    request_id: str


class InterruptedEventData(BaseModel):
    """Payload for event: "interrupted"."""

    request_id: str


class EndEventData(BaseModel):
    """Nested data for event: "end"."""

    referenced_documents: list[ReferencedDocument]
    truncated: Optional[bool]
    input_tokens: int
    output_tokens: int


class ErrorStreamPayload(StreamPayloadBase):
    """SSE error event body (event + typed data)."""

    event: Literal["error"] = "error"
    data: ErrorEventData

    @classmethod
    def create(cls, *, status_code: int, response: str, cause: str) -> Self:
        """Create an error stream payload from HTTP error fields.

        Args:
            status_code: HTTP status code for the error.
            response: Short summary of the error.
            cause: Detailed explanation of the error cause.

        Returns:
            Error stream payload instance.
        """
        return cls(
            data=ErrorEventData(status_code=status_code, response=response, cause=cause)
        )

    @classmethod
    def from_error_response(cls, error_response: AbstractErrorResponse) -> Self:
        """Create an error stream payload from a structured API error response.

        Args:
            error_response: Structured error response model.

        Returns:
            Error stream payload instance.
        """
        return cls.create(
            status_code=error_response.status_code,
            response=error_response.detail.response,
            cause=error_response.detail.cause,
        )

    def serialize_text(self) -> str:
        """Serialize error stream payload to plain text."""
        return f"Status: {self.data.status_code} - {self.data.response} - {self.data.cause}"


class StartStreamPayload(StreamPayloadBase):
    """SSE stream start body."""

    event: Literal["start"] = "start"
    data: StartEventData

    @classmethod
    def create(cls, *, conversation_id: str, request_id: str) -> Self:
        """Create a stream-start payload.

        Args:
            conversation_id: Conversation identifier for the stream.
            request_id: Request identifier for the stream.

        Returns:
            Start stream payload instance.
        """
        return cls(
            data=StartEventData(conversation_id=conversation_id, request_id=request_id)
        )


class InterruptedStreamPayload(StreamPayloadBase):
    """SSE interrupted stream body."""

    event: Literal["interrupted"] = "interrupted"
    data: InterruptedEventData

    @classmethod
    def create(cls, *, request_id: str) -> Self:
        """Create an interrupted-stream payload.

        Args:
            request_id: Request identifier for the interrupted stream.

        Returns:
            Interrupted stream payload instance.
        """
        return cls(data=InterruptedEventData(request_id=request_id))


class EndStreamPayload(StreamPayloadBase):
    """SSE end-of-stream body (includes available_quotas beside data)."""

    event: Literal["end"] = "end"
    data: EndEventData
    available_quotas: dict[str, int]

    @classmethod
    def create(
        cls,
        *,
        referenced_documents: list[ReferencedDocument],
        input_tokens: int,
        output_tokens: int,
        available_quotas: dict[str, int],
    ) -> Self:
        """Create an end-of-stream payload.

        Args:
            referenced_documents: Documents referenced during the turn.
            input_tokens: Input token count for the turn.
            output_tokens: Output token count for the turn.
            available_quotas: Remaining quota limits by quota name.

        Returns:
            End stream payload instance.
        """
        return cls(
            data=EndEventData(
                referenced_documents=referenced_documents,
                truncated=None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
            available_quotas=available_quotas,
        )

    def serialize_text(self) -> str:
        """Serialize end stream payload to plain text."""
        ref_docs_string = "\n".join(
            f"{doc.doc_title}: {doc.doc_url}"
            for doc in self.data.referenced_documents
            if doc.doc_url and doc.doc_title
        )
        return f"\n\n---\n\n{ref_docs_string}" if ref_docs_string else ""


class TokenChunkData(BaseModel):
    """Structured data for token and turn-complete stream lines."""

    id: int
    token: str


class TokenStreamPayload(StreamPayloadBase):
    """SSE token delta (event: "token")."""

    event: Literal["token"] = "token"
    data: TokenChunkData

    @classmethod
    def create(cls, *, chunk_id: int, token: str) -> Self:
        """Create a token stream payload.

        Args:
            chunk_id: Monotonic chunk identifier for the token delta.
            token: Token text for the delta.

        Returns:
            Token stream payload instance.
        """
        return cls(data=TokenChunkData(id=chunk_id, token=token))

    def serialize_text(self) -> str:
        """Serialize token stream payload to plain text."""
        return self.data.token


class TurnCompleteStreamPayload(StreamPayloadBase):
    """SSE turn completion (same data shape as token)."""

    event: Literal["turn_complete"] = "turn_complete"
    data: TokenChunkData

    @classmethod
    def create(cls, *, chunk_id: int, token: str) -> Self:
        """Create a turn-complete stream payload.

        Args:
            chunk_id: Monotonic chunk identifier for the final text.
            token: Full assistant text for the completed turn.

        Returns:
            Turn-complete stream payload instance.
        """
        return cls(data=TokenChunkData(id=chunk_id, token=token))


class ToolCallStreamPayload(StreamPayloadBase):
    """SSE tool call summary."""

    event: Literal["tool_call"] = "tool_call"
    data: ToolCallSummary

    def serialize_text(self) -> str:
        """Serialize tool call stream payload to plain text."""
        return f"[Tool Call: {self.data.name}]\n"


class ToolResultStreamPayload(StreamPayloadBase):
    """SSE tool result summary."""

    event: Literal["tool_result"] = "tool_result"
    data: ToolResultSummary

    def serialize_text(self) -> str:
        """Serialize tool result stream payload to plain text."""
        return "[Tool Result]\n"


StreamEventPayload: TypeAlias = Annotated[
    TokenStreamPayload
    | TurnCompleteStreamPayload
    | ToolCallStreamPayload
    | ToolResultStreamPayload
    | EndStreamPayload
    | ErrorStreamPayload
    | InterruptedStreamPayload
    | StartStreamPayload,
    Field(discriminator="event"),
]
