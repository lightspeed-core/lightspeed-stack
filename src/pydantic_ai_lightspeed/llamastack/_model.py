"""Custom OpenAI Responses model that works around Llama Stack streaming quirks.

Llama Stack's Responses API emits MCP tool argument events *before*
``ResponseOutputItemAddedEvent`` and uses event type names that differ from the
OpenAI SDK (``response.mcp_call.arguments.*`` vs ``response.mcp_call_arguments.*``).
pydantic_ai expects:

* ``output_item.added`` first so it can register the MCP call part and seed args
  up to ``"tool_args":``
* ``response.mcp_call_arguments.delta`` fragments for the tool-args JSON body
* ``response.mcp_call_arguments.done`` (pydantic_ai appends only ``}``)

This module buffers pre-announcement events per ``item_id`` and replays them in
that order once the ``mcp_call`` output item is announced.  Post-announcement
``function_call_arguments.*`` events for ``mcp_call`` items are converted to the
MCP argument form pydantic_ai handles.
"""

from __future__ import annotations as _annotations

from collections import defaultdict
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from openai import AsyncStream
from openai.types import responses
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai._run_context import RunContext
from pydantic_ai._utils import PeekableAsyncStream, Unset, number_to_datetime
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import (
    ModelRequestParameters,
    StreamedResponse,
    check_allow_model_requests,
)
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
    OpenAIResponsesStreamedResponse,
    _map_api_errors,
)
from pydantic_ai.settings import ModelSettings

from log import get_logger

logger = get_logger(__name__)

_LLS_MCP_ARGUMENTS_DELTA_TYPE = "response.mcp_call.arguments.delta"
_LLS_MCP_ARGUMENTS_DONE_TYPE = "response.mcp_call.arguments.done"
_SDK_MCP_ARGUMENTS_DELTA_TYPE = "response.mcp_call_arguments.delta"
_SDK_MCP_ARGUMENTS_DONE_TYPE = "response.mcp_call_arguments.done"

_MCP_ARGUMENTS_DONE_TYPES = frozenset(
    {
        _LLS_MCP_ARGUMENTS_DONE_TYPE,
        _SDK_MCP_ARGUMENTS_DONE_TYPE,
    }
)


@dataclass
class _PreAnnouncementArguments:
    """Argument fragments buffered before ``output_item.added`` (always MCP for LLS)."""

    delta_fragments: list[str] = field(default_factory=list)
    arguments_done: bool = False
    done_arguments: str = "{}"
    pending_output_done: responses.ResponseOutputItemDoneEvent | None = None

    def has_content(self) -> bool:
        """Return whether any argument events are buffered."""
        return bool(self.delta_fragments) or self.arguments_done


@dataclass
class _BufferedMcpListToolsEvents:
    """Buffered MCP list-tools lifecycle events keyed by item id."""

    in_progress: responses.ResponseMcpListToolsInProgressEvent | None = None
    completed: responses.ResponseMcpListToolsCompletedEvent | None = None
    output_done: responses.ResponseOutputItemDoneEvent | None = None

    def has_content(self) -> bool:
        """Return whether any list-tools lifecycle events are buffered."""
        return (
            self.in_progress is not None
            or self.completed is not None
            or self.output_done is not None
        )


class _FilteredResponseStream:
    """Wraps an OpenAI AsyncStream to reorder and normalize Llama Stack events."""

    def __init__(self, source: AsyncStream[responses.ResponseStreamEvent]) -> None:
        """Wrap an existing stream with reordering logic.

        Args:
            source: The raw OpenAI AsyncStream to reorder.
        """
        self._source = source
        self._released_item_ids: set[str] = set()
        self._item_types: dict[str, str] = {}
        self._mcp_args_complete: set[str] = set()
        self._pre_args_buffers: dict[str, _PreAnnouncementArguments] = defaultdict(
            _PreAnnouncementArguments
        )
        self._list_tools_buffers: dict[str, _BufferedMcpListToolsEvents] = defaultdict(
            _BufferedMcpListToolsEvents
        )

    async def close(self) -> None:
        """Close the underlying stream."""
        await self._source.close()

    def __aiter__(self) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Return async iterator that reorders events."""
        return self._filtered_iter()

    async def _filtered_iter(
        self,
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Yield events, buffering and normalizing Llama Stack streaming quirks."""
        async for event in self._source:
            if isinstance(event, responses.ResponseOutputItemAddedEvent):
                async for reordered in self._handle_output_item_added(event):
                    yield reordered
                continue

            if isinstance(event, responses.ResponseOutputItemDoneEvent):
                async for reordered in self._handle_output_item_done(event):
                    yield reordered
                continue

            if isinstance(event, responses.ResponseFunctionCallArgumentsDeltaEvent):
                async for reordered in self._handle_argument_delta(event):
                    yield reordered
                continue

            if isinstance(event, responses.ResponseFunctionCallArgumentsDoneEvent):
                async for reordered in self._handle_argument_done(event):
                    yield reordered
                continue

            if isinstance(event, responses.ResponseMcpCallArgumentsDeltaEvent):
                async for reordered in self._handle_mcp_argument_delta(event):
                    yield reordered
                continue

            if getattr(event, "type", None) in _MCP_ARGUMENTS_DONE_TYPES:
                async for reordered in self._handle_mcp_argument_done(event):
                    yield reordered
                continue

            event_type = getattr(event, "type", None)
            if event_type == _LLS_MCP_ARGUMENTS_DELTA_TYPE:
                async for reordered in self._handle_lls_mcp_argument_delta(event):
                    yield reordered
                continue

            if isinstance(event, responses.ResponseMcpListToolsInProgressEvent):
                if event.item_id in self._released_item_ids:
                    yield event
                else:
                    self._list_tools_buffers[event.item_id].in_progress = event
                continue

            if isinstance(event, responses.ResponseMcpListToolsCompletedEvent):
                if event.item_id in self._released_item_ids:
                    yield event
                else:
                    self._list_tools_buffers[event.item_id].completed = event
                continue

            yield event

        for item_id, buffer in list(self._pre_args_buffers.items()):
            if not buffer.has_content():
                continue
            logger.warning(
                "Flushing buffered argument event(s) without output_item.added "
                "for item_id=%s",
                item_id,
            )
            for flushed in self._replay_mcp_argument_events(item_id, buffer):
                yield flushed
            if buffer.pending_output_done is not None:
                yield buffer.pending_output_done
            self._pre_args_buffers.pop(item_id, None)

        for item_id, buffer in list(self._list_tools_buffers.items()):
            if not buffer.has_content():
                continue
            logger.warning(
                "Flushing buffered mcp_list_tools event(s) without output_item.added "
                "for item_id=%s",
                item_id,
            )
            for replayed in self._replay_list_tools_events(buffer):
                yield replayed
            self._list_tools_buffers.pop(item_id, None)

    async def _handle_output_item_added(
        self, event: responses.ResponseOutputItemAddedEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Yield ``output_item.added`` then buffered follow-up events for the item."""
        item_id = getattr(event.item, "id", None)
        item_type = getattr(event.item, "type", None)
        if item_id is not None:
            self._released_item_ids.add(item_id)
            if item_type is not None:
                self._item_types[item_id] = item_type

        yield event

        if item_id is None:
            return

        if item_type == "mcp_list_tools":
            list_tools_buffer = self._list_tools_buffers.pop(
                item_id, _BufferedMcpListToolsEvents()
            )
            for replayed in self._replay_list_tools_events(list_tools_buffer):
                yield replayed
            return

        pre_args = self._pre_args_buffers.pop(item_id, _PreAnnouncementArguments())
        if not pre_args.has_content():
            if pre_args.pending_output_done is not None:
                yield pre_args.pending_output_done
            return

        if item_type == "mcp_call":
            logger.debug(
                "Replaying buffered MCP argument events after output_item.added "
                "for item_id=%s",
                item_id,
            )
            for replayed in self._replay_mcp_argument_events(item_id, pre_args):
                yield replayed
        else:
            logger.debug(
                "Replaying buffered function argument events after output_item.added "
                "for item_id=%s",
                item_id,
            )
            for replayed in self._replay_function_argument_events(item_id, pre_args):
                yield replayed

        if pre_args.pending_output_done is not None:
            yield pre_args.pending_output_done

    async def _handle_output_item_done(
        self, event: responses.ResponseOutputItemDoneEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Hold MCP call ``output_item.done`` until argument streaming has finished."""
        item_id = getattr(event.item, "id", None)
        item_type = getattr(event.item, "type", None)

        if (
            item_type == "mcp_list_tools"
            and item_id is not None
            and item_id not in self._released_item_ids
        ):
            self._list_tools_buffers[item_id].output_done = event
            return

        if (
            item_type == "mcp_call"
            and item_id is not None
            and item_id not in self._mcp_args_complete
        ):
            self._pre_args_buffers[item_id].pending_output_done = event
            logger.debug(
                "Buffering mcp_call output_item.done until arguments.done for item_id=%s",
                item_id,
            )
            return

        yield event

    async def _handle_argument_delta(
        self, event: responses.ResponseFunctionCallArgumentsDeltaEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Buffer or convert function argument deltas."""
        if event.item_id not in self._released_item_ids:
            self._pre_args_buffers[event.item_id].delta_fragments.append(event.delta)
            logger.debug(
                "Buffering pre-announcement argument delta for item_id=%s",
                event.item_id,
            )
            return

        if self._item_types.get(event.item_id) == "mcp_call":
            yield self._to_mcp_arguments_delta(event)
            return

        yield event

    async def _handle_argument_done(
        self, event: responses.ResponseFunctionCallArgumentsDoneEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Buffer or drop function argument done events for MCP calls."""
        if event.item_id not in self._released_item_ids:
            self._pre_args_buffers[event.item_id].arguments_done = True
            self._pre_args_buffers[event.item_id].done_arguments = event.arguments
            logger.debug(
                "Buffering pre-announcement arguments.done for item_id=%s",
                event.item_id,
            )
            return

        if self._item_types.get(event.item_id) == "mcp_call":
            if event.item_id not in self._mcp_args_complete:
                yield self._to_mcp_arguments_done(event)
                self._mcp_args_complete.add(event.item_id)
                pending = self._pre_args_buffers[event.item_id].pending_output_done
                if pending is not None:
                    self._pre_args_buffers[event.item_id].pending_output_done = None
                    yield pending
            return

        yield event

    async def _handle_mcp_argument_delta(
        self, event: responses.ResponseMcpCallArgumentsDeltaEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Buffer or pass through OpenAI-form MCP argument deltas."""
        if event.item_id not in self._released_item_ids:
            self._pre_args_buffers[event.item_id].delta_fragments.append(event.delta)
            return
        yield event

    async def _handle_lls_mcp_argument_delta(
        self, event: responses.ResponseStreamEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Normalize Llama Stack dot-form MCP argument deltas."""
        item_id = cast(str, getattr(event, "item_id", None))
        delta = cast(str, getattr(event, "delta", ""))
        if item_id not in self._released_item_ids:
            self._pre_args_buffers[item_id].delta_fragments.append(delta)
            return
        yield self._build_mcp_arguments_delta(
            item_id=item_id,
            delta=delta,
            output_index=getattr(event, "output_index", 0),
            sequence_number=getattr(event, "sequence_number", 0),
        )

    async def _handle_mcp_argument_done(
        self, event: responses.ResponseStreamEvent
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Buffer or normalize MCP arguments.done events."""
        mcp_done = self._normalize_mcp_arguments_done(event)
        if mcp_done.item_id not in self._released_item_ids:
            self._pre_args_buffers[mcp_done.item_id].arguments_done = True
            self._pre_args_buffers[mcp_done.item_id].done_arguments = mcp_done.arguments
            return

        if mcp_done.item_id not in self._mcp_args_complete:
            yield mcp_done
            self._mcp_args_complete.add(mcp_done.item_id)
            pending = self._pre_args_buffers[mcp_done.item_id].pending_output_done
            if pending is not None:
                self._pre_args_buffers[mcp_done.item_id].pending_output_done = None
                yield pending

    def _replay_list_tools_events(
        self, buffer: _BufferedMcpListToolsEvents
    ) -> Iterator[responses.ResponseStreamEvent]:
        """Replay buffered MCP list-tools lifecycle events in pydantic_ai order."""
        if buffer.in_progress is not None:
            yield buffer.in_progress
        if buffer.completed is not None:
            yield buffer.completed
        if buffer.output_done is not None:
            yield buffer.output_done

    def _replay_function_argument_events(
        self,
        item_id: str,
        buffer: _PreAnnouncementArguments,
    ) -> Iterator[responses.ResponseStreamEvent]:
        """Replay buffered argument fragments as function-call events."""
        output_index = 0
        sequence_number = 0
        for fragment in buffer.delta_fragments:
            yield responses.ResponseFunctionCallArgumentsDeltaEvent.model_validate(
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": item_id,
                    "output_index": output_index,
                    "sequence_number": sequence_number,
                    "delta": fragment,
                }
            )
            sequence_number += 1

        if buffer.arguments_done:
            yield responses.ResponseFunctionCallArgumentsDoneEvent.model_validate(
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": item_id,
                    "output_index": output_index,
                    "sequence_number": sequence_number,
                    "arguments": buffer.done_arguments,
                    "name": "",
                }
            )

    def _replay_mcp_argument_events(
        self,
        item_id: str,
        buffer: _PreAnnouncementArguments,
    ) -> Iterator[responses.ResponseStreamEvent]:
        """Replay buffered MCP argument fragments after ``output_item.added``.

        pydantic_ai seeds args up to ``"tool_args":`` when the item is announced,
        then appends delta fragments and closes the JSON object on arguments.done.
        """
        if not buffer.delta_fragments and not buffer.arguments_done:
            return

        output_index = 0
        sequence_number = 0
        for fragment in buffer.delta_fragments:
            yield self._build_mcp_arguments_delta(
                item_id=item_id,
                delta=fragment,
                output_index=output_index,
                sequence_number=sequence_number,
            )
            sequence_number += 1

        if buffer.arguments_done:
            yield self._build_mcp_arguments_done(
                item_id=item_id,
                output_index=output_index,
                sequence_number=sequence_number,
            )
            self._mcp_args_complete.add(item_id)

    def _to_mcp_arguments_delta(
        self, event: responses.ResponseFunctionCallArgumentsDeltaEvent
    ) -> responses.ResponseMcpCallArgumentsDeltaEvent:
        """Convert a function argument delta into the MCP form pydantic_ai expects."""
        return self._build_mcp_arguments_delta(
            item_id=event.item_id,
            delta=event.delta,
            output_index=event.output_index,
            sequence_number=event.sequence_number,
        )

    def _to_mcp_arguments_done(
        self, event: responses.ResponseFunctionCallArgumentsDoneEvent
    ) -> responses.ResponseMcpCallArgumentsDoneEvent:
        """Convert a misclassified function arguments.done into MCP form."""
        return self._build_mcp_arguments_done(
            item_id=event.item_id,
            output_index=event.output_index,
            sequence_number=event.sequence_number,
            arguments=event.arguments,
        )

    @staticmethod
    def _build_mcp_arguments_delta(
        *,
        item_id: str,
        delta: str,
        output_index: int,
        sequence_number: int,
    ) -> responses.ResponseMcpCallArgumentsDeltaEvent:
        """Build an OpenAI SDK MCP arguments delta event."""
        return responses.ResponseMcpCallArgumentsDeltaEvent.model_validate(
            {
                "type": _SDK_MCP_ARGUMENTS_DELTA_TYPE,
                "item_id": item_id,
                "output_index": output_index,
                "sequence_number": sequence_number,
                "delta": delta,
            }
        )

    @staticmethod
    def _build_mcp_arguments_done(
        *,
        item_id: str,
        output_index: int,
        sequence_number: int,
        arguments: str = "{}",
    ) -> responses.ResponseMcpCallArgumentsDoneEvent:
        """Build an OpenAI SDK MCP arguments done event."""
        return responses.ResponseMcpCallArgumentsDoneEvent.model_validate(
            {
                "type": _SDK_MCP_ARGUMENTS_DONE_TYPE,
                "item_id": item_id,
                "output_index": output_index,
                "sequence_number": sequence_number,
                "arguments": arguments,
            }
        )

    @staticmethod
    def _normalize_mcp_arguments_done(
        event: responses.ResponseStreamEvent,
    ) -> responses.ResponseMcpCallArgumentsDoneEvent:
        """Normalize Llama Stack MCP done event types to the OpenAI SDK form."""
        if isinstance(event, responses.ResponseMcpCallArgumentsDoneEvent):
            return event
        return responses.ResponseMcpCallArgumentsDoneEvent.model_validate(
            {
                **event.model_dump(exclude={"type"}),
                "type": _SDK_MCP_ARGUMENTS_DONE_TYPE,
            }
        )


class LlamaStackResponsesModel(OpenAIResponsesModel):
    """OpenAI Responses model with Llama Stack streaming compatibility fixes."""

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Request a streaming response with Llama Stack event normalization."""
        check_allow_model_requests()
        model_settings, model_request_parameters = self.prepare_request(
            model_settings,
            model_request_parameters,
        )
        model_settings_cast = cast(OpenAIResponsesModelSettings, model_settings or {})
        response = await self._responses_create(
            messages, True, model_settings_cast, model_request_parameters
        )

        filtered_stream = _FilteredResponseStream(response)

        async with response:
            peekable: PeekableAsyncStream[
                responses.ResponseStreamEvent, _FilteredResponseStream
            ] = PeekableAsyncStream(filtered_stream)

            with _map_api_errors(self.model_name):
                first_chunk = await peekable.peek()

            if isinstance(first_chunk, Unset):
                raise UnexpectedModelBehavior(
                    "Streamed response ended without content or tool calls"
                )

            assert isinstance(first_chunk, responses.ResponseCreatedEvent)

            yield OpenAIResponsesStreamedResponse(
                model_request_parameters=model_request_parameters,
                _model_name=first_chunk.response.model,
                _model_settings=model_settings_cast,
                _response=peekable,  # type: ignore[arg-type]
                _provider_name=self._provider.name,
                _provider_url=self._provider.base_url,
                _provider_timestamp=(
                    number_to_datetime(first_chunk.response.created_at)
                    if first_chunk.response.created_at
                    else None
                ),
            )
