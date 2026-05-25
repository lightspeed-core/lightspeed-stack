"""Draft translator from pydantic-ai stream events to Lightspeed streaming_query SSE payloads.

Maps ``AgentStreamEvent`` (and related model-stream events) into the same
``StreamLlmEventPayload`` shapes emitted today by ``/streaming_query`` via
``chunk_dispatchers`` / ``output_item_dispatchers``.

Not wired into any endpoint yet. Lifecycle envelopes (``start``, ``end``,
``interrupted``) remain the responsibility of ``streaming_query.generate_response``;
this module only covers events produced from the model response stream:

- ``token``
- ``tool_call``
- ``tool_result``
- ``turn_complete`` (via :meth:`PydanticAiStreamTranslator.translate_turn_complete`)
- ``error`` (via :meth:`PydanticAiStreamTranslator.translate_error`)

Events that pydantic-ai may emit but streaming_query does **not** forward are
ignored (no output): ``part_end``, ``final_result``, thinking/reasoning parts,
file/compaction parts, and agent-layer ``HandleResponseEvent`` variants
(``function_tool_call``, ``function_tool_result``, etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import (
    AgentStreamEvent,
    BaseToolCallPart,
    BuiltinToolCallEvent,
    BuiltinToolResultEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelResponseStreamEvent,
    NativeToolCallPart,
    NativeToolReturnPart,
    OutputToolCallEvent,
    OutputToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolResultEvent,
)
from pydantic_ai.native_tools import FileSearchTool, MCPServerTool, WebSearchTool

from constants import DEFAULT_RAG_TOOL
from models.common.streaming import (
    ErrorEventData,
    ErrorStreamPayload,
    LlmTokenChunkData,
    LlmTokenStreamPayload,
    LlmToolCallStreamPayload,
    LlmToolResultStreamPayload,
    LlmTurnCompleteStreamPayload,
    StreamLlmEventPayload,
)
from models.common.turn_summary import ToolCallSummary, ToolResultSummary
from utils.responses import parse_arguments_string

_MCP_SERVER_PREFIX = f"{MCPServerTool.kind}:"


@dataclass(slots=True)
class PydanticAiStreamTranslationState:
    """Incremental state while translating a pydantic-ai event stream."""

    chunk_id: int = 0
    text_parts: list[str] = field(default_factory=list)
    llm_response: str = ""
    pending_tool_calls: dict[str, BaseToolCallPart] = field(default_factory=dict)
    emitted_tool_call_ids: set[str] = field(default_factory=set)


@dataclass
class PydanticAiStreamTranslator:
    """Stateful translator from pydantic-ai ``AgentStreamEvent`` to LCS stream payloads.

    Parameters:
        state: Optional initial reducer state; a fresh instance is created when omitted.
    """

    state: PydanticAiStreamTranslationState = field(
        default_factory=PydanticAiStreamTranslationState
    )

    def translate(self, event: AgentStreamEvent) -> list[StreamLlmEventPayload]:
        """Translate one pydantic-ai stream event into zero or more LCS payloads.

        Parameters:
            event: A model- or agent-layer stream event from pydantic-ai.

        Returns:
            Payloads using the same ``event`` discriminator values as ``/streaming_query``.
            Empty when the input event has no streaming_query analogue.
        """
        if isinstance(event, PartStartEvent):
            return self._translate_part_start(event)
        if isinstance(event, PartDeltaEvent):
            return self._translate_part_delta(event)
        if isinstance(event, PartEndEvent):
            return self._translate_part_end(event)
        if isinstance(event, FinalResultEvent):
            return []
        if isinstance(event, (FunctionToolCallEvent, FunctionToolResultEvent)):
            return []
        if isinstance(event, (OutputToolCallEvent, OutputToolResultEvent)):
            return []
        if isinstance(event, (BuiltinToolCallEvent, BuiltinToolResultEvent)):
            return []
        if isinstance(event, ToolResultEvent):
            return []
        return []

    def translate_turn_complete(
        self,
        final_text: str | None = None,
    ) -> LlmTurnCompleteStreamPayload:
        """Build a ``turn_complete`` payload matching ``CompletedChunk`` dispatch.

        Parameters:
            final_text: Full assistant text; when omitted, joined buffered text deltas
                and any stored ``llm_response`` are used.

        Returns:
            A ``LlmTurnCompleteStreamPayload`` with the same shape as chunk dispatch.
        """
        resolved = final_text if final_text is not None else (
            self.state.llm_response or "".join(self.state.text_parts)
        )
        self.state.llm_response = resolved
        payload = LlmTurnCompleteStreamPayload(
            data=LlmTokenChunkData(id=self.state.chunk_id, token=resolved),
        )
        self.state.chunk_id += 1
        return payload

    def translate_error(
        self,
        *,
        status_code: int,
        response: str,
        cause: str,
    ) -> ErrorStreamPayload:
        """Build an ``error`` payload matching incomplete/failed chunk dispatch.

        Parameters:
            status_code: HTTP-style status code for the client.
            response: Short error response label.
            cause: Detailed cause string.

        Returns:
            An ``ErrorStreamPayload``.
        """
        return ErrorStreamPayload(
            data=ErrorEventData(
                status_code=status_code,
                response=response,
                cause=cause,
            ),
        )

    def _translate_part_start(self, event: PartStartEvent) -> list[StreamLlmEventPayload]:
        part = event.part
        if isinstance(part, TextPart):
            return self._emit_token(part.content)
        if isinstance(part, ThinkingPart):
            return []
        if isinstance(part, (ToolCallPart, NativeToolCallPart)):
            self.state.pending_tool_calls[part.tool_call_id] = part
            if _tool_call_is_complete(part):
                return self._emit_tool_call_if_new(part)
            return []
        if isinstance(part, NativeToolReturnPart):
            payloads: list[StreamLlmEventPayload] = []
            call_part = self.state.pending_tool_calls.get(part.tool_call_id)
            if call_part is not None and part.tool_call_id not in self.state.emitted_tool_call_ids:
                payloads.extend(self._emit_tool_call_if_new(call_part))
            payloads.extend(self._emit_tool_result(part))
            return payloads
        return []

    def _translate_part_delta(self, event: PartDeltaEvent) -> list[StreamLlmEventPayload]:
        delta = event.delta
        if isinstance(delta, TextPartDelta):
            if delta.content_delta:
                return self._emit_token(delta.content_delta)
            return []
        if isinstance(delta, ThinkingPartDelta):
            return []
        if isinstance(delta, ToolCallPartDelta):
            pending = self.state.pending_tool_calls.get(
                delta.tool_call_id or "",
            )
            if pending is None:
                new_part = delta.as_part()
                if new_part is not None:
                    self.state.pending_tool_calls[new_part.tool_call_id] = new_part
                    if _tool_call_is_complete(new_part):
                        return self._emit_tool_call_if_new(new_part)
                return []
            merged = _apply_tool_call_delta(pending, delta)
            self.state.pending_tool_calls[merged.tool_call_id] = merged
            if _tool_call_is_complete(merged):
                return self._emit_tool_call_if_new(merged)
            return []
        return []

    def _translate_part_end(self, event: PartEndEvent) -> list[StreamLlmEventPayload]:
        part = event.part
        if isinstance(part, TextPart):
            self.state.llm_response = part.content
            return []
        if isinstance(part, (ToolCallPart, NativeToolCallPart)):
            self.state.pending_tool_calls[part.tool_call_id] = part
            return self._emit_tool_call_if_new(part)
        return []

    def _emit_token(self, token: str) -> list[StreamLlmEventPayload]:
        self.state.text_parts.append(token)
        payload = LlmTokenStreamPayload(
            data=LlmTokenChunkData(id=self.state.chunk_id, token=token),
        )
        self.state.chunk_id += 1
        return [payload]

    def _emit_tool_call_if_new(
        self,
        part: BaseToolCallPart,
    ) -> list[StreamLlmEventPayload]:
        if part.tool_call_id in self.state.emitted_tool_call_ids:
            return []
        summary = _tool_call_summary_from_part(part)
        if summary is None:
            return []
        self.state.emitted_tool_call_ids.add(part.tool_call_id)
        return [LlmToolCallStreamPayload(data=summary)]

    def _emit_tool_result(
        self,
        part: NativeToolReturnPart,
    ) -> list[StreamLlmEventPayload]:
        summary = _tool_result_summary_from_native_return(part)
        if summary is None:
            return []
        return [LlmToolResultStreamPayload(data=summary)]


def _tool_call_is_complete(part: BaseToolCallPart) -> bool:
    """Return whether a tool call part has enough data to emit ``tool_call``."""
    if isinstance(part, NativeToolCallPart):
        if part.tool_name.startswith(_MCP_SERVER_PREFIX):
            args = part.args_as_dict()
            action = args.get("action")
            if action == "list_tools":
                return True
            if action == "call_tool":
                return part.has_content()
            return part.has_content()
        return part.has_content()
    return part.has_content()


def _apply_tool_call_delta(
    part: BaseToolCallPart,
    delta: ToolCallPartDelta,
) -> BaseToolCallPart:
    """Apply a tool-call delta to a buffered part (mirrors parts manager semantics)."""
    updated = delta.apply(part)
    if isinstance(updated, (ToolCallPart, NativeToolCallPart)):
        return updated
    if isinstance(updated, ToolCallPartDelta):
        as_part = updated.as_part()
        if as_part is not None:
            return as_part
    return part


def _normalize_args(part: BaseToolCallPart) -> dict[str, Any]:
    if isinstance(part, NativeToolCallPart):
        return part.args_as_dict()
    if isinstance(part, ToolCallPart):
        if not part.args:
            return {}
        if isinstance(part.args, dict):
            return part.args
        return parse_arguments_string(part.args)
    return {}


def _tool_call_summary_from_part(part: BaseToolCallPart) -> ToolCallSummary | None:
    """Map a completed tool-call part to ``ToolCallSummary``."""
    call_id = part.tool_call_id
    args = _normalize_args(part)

    if isinstance(part, ToolCallPart):
        return ToolCallSummary(
            id=call_id,
            name=part.tool_name,
            args=args,
            type="function_call",
        )

    if not isinstance(part, NativeToolCallPart):
        return None

    if part.tool_name == WebSearchTool.kind:
        return ToolCallSummary(
            id=part.id or call_id,
            name="web_search",
            args={},
            type="web_search_call",
        )

    if part.tool_name == FileSearchTool.kind:
        return ToolCallSummary(
            id=part.id or call_id,
            name=DEFAULT_RAG_TOOL,
            args={"queries": args.get("queries", [])},
            type="file_search_call",
        )

    if part.tool_name.startswith(_MCP_SERVER_PREFIX):
        return _mcp_tool_call_summary(part, args)

    return ToolCallSummary(
        id=part.id or call_id,
        name=part.tool_name,
        args=args,
        type="mcp_call",
    )


def _mcp_tool_call_summary(
    part: NativeToolCallPart,
    args: dict[str, Any],
) -> ToolCallSummary | None:
    call_id = part.id or part.tool_call_id
    action = args.get("action")

    if action == "list_tools":
        server_label = _mcp_server_label(part.tool_name)
        return ToolCallSummary(
            id=call_id,
            name="mcp_list_tools",
            args={"server_label": server_label},
            type="mcp_list_tools",
        )

    if action == "call_tool":
        tool_args = args.get("tool_args")
        if isinstance(tool_args, str):
            tool_args = parse_arguments_string(tool_args)
        if not isinstance(tool_args, dict):
            tool_args = {}
        summary_args = dict(tool_args)
        server_label = _mcp_server_label(part.tool_name)
        if server_label:
            summary_args["server_label"] = server_label
        return ToolCallSummary(
            id=call_id,
            name=str(args.get("tool_name", "")),
            args=summary_args,
            type="mcp_call",
        )

    return ToolCallSummary(
        id=call_id,
        name=part.tool_name,
        args=args,
        type="mcp_call",
    )


def _mcp_server_label(tool_name: str) -> str:
    if tool_name.startswith(_MCP_SERVER_PREFIX):
        return tool_name[len(_MCP_SERVER_PREFIX) :]
    return ""


def _tool_result_summary_from_native_return(
    part: NativeToolReturnPart,
) -> ToolResultSummary | None:
    """Map a native tool return part to ``ToolResultSummary``."""
    call_id = part.tool_call_id
    content_dict = part.content if isinstance(part.content, dict) else {}
    status = str(content_dict.get("status", "success"))

    if part.tool_name == WebSearchTool.kind:
        return ToolResultSummary(
            id=call_id,
            status=status,
            content="",
            type="web_search_call",
            round=1,
        )

    if part.tool_name == FileSearchTool.kind:
        response_payload: dict[str, Any] | None = None
        if results := content_dict.get("results"):
            response_payload = {"results": results}
        return ToolResultSummary(
            id=call_id,
            status=status,
            content=json.dumps(response_payload) if response_payload else "",
            type="file_search_call",
            round=1,
        )

    if part.tool_name.startswith(_MCP_SERVER_PREFIX):
        return _mcp_tool_result_summary(part, content_dict, status)

    return ToolResultSummary(
        id=call_id,
        status=status,
        content=_stringify_tool_content(part.content),
        type="mcp_call",
        round=1,
    )


def _mcp_tool_result_summary(
    part: NativeToolReturnPart,
    content_dict: dict[str, Any],
    status: str,
) -> ToolResultSummary:
    call_id = part.tool_call_id
    args_action = None
    if isinstance(part.content, dict):
        args_action = part.content.get("action")

    if content_dict.get("tools") is not None or args_action == "list_tools":
        server_label = _mcp_server_label(part.tool_name)
        tools_info = content_dict.get("tools", [])
        payload = {
            "server_label": server_label,
            "tools": tools_info,
        }
        return ToolResultSummary(
            id=call_id,
            status="success",
            content=json.dumps(payload),
            type="mcp_list_tools",
            round=1,
        )

    error = content_dict.get("error")
    if error is not None:
        content = str(error)
        result_status = "failure"
    else:
        content = _stringify_tool_content(part.content)
        result_status = "success" if status != "failure" else "failure"

    return ToolResultSummary(
        id=call_id,
        status=result_status,
        content=content,
        type="mcp_call",
        round=1,
    )


def _stringify_tool_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content)


def translate_model_response_stream_event(
    event: ModelResponseStreamEvent,
    *,
    translator: PydanticAiStreamTranslator | None = None,
) -> tuple[PydanticAiStreamTranslator, list[StreamLlmEventPayload]]:
    """Convenience wrapper for model-only streams (no ``HandleResponseEvent``).

    Parameters:
        event: A ``ModelResponseStreamEvent`` from pydantic-ai.
        translator: Optional shared translator instance.

    Returns:
        Updated translator and translated payloads.
    """
    active = translator or PydanticAiStreamTranslator()
    return active, active.translate(event)
