"""Custom OpenAI Responses model that works around Llama Stack streaming quirks.

Llama Stack's Responses API emits ``ResponseFunctionCallArgumentsDeltaEvent`` for MCP
tool calls *before* the corresponding ``ResponseOutputItemAddedEvent``.  pydantic_ai's
default handler creates an orphan ``ToolCallPartDelta`` for the unannounced item_id,
which later causes an IndexError in ``part_end_event``.

Additionally, MCP tool calls arrive as ``McpCall`` items (not ``ResponseFunctionToolCall``),
and pydantic_ai registers them with a ``-call`` vendor_part_id suffix.  The buffered
deltas must be replayed with the matching suffix so pydantic_ai can append the
streamed ``tool_args`` content to the correct part.

This module provides ``LlamaStackResponsesModel`` which wraps the event stream to
buffer those early delta events and replay them correctly once the item is announced.
"""

from __future__ import annotations as _annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from openai import AsyncStream
from openai.types import responses
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai._run_context import RunContext
from pydantic_ai._utils import PeekableAsyncStream, Unset, number_to_datetime
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse
from pydantic_ai.models import (
    ModelRequestParameters,
    ModelSettings,
    StreamedResponse,
    check_allow_model_requests,
)
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
    OpenAIResponsesStreamedResponse,
    _map_api_errors,
)

from log import get_logger

logger = get_logger(__name__)


class _FilteredResponseStream:
    """Wraps an OpenAI AsyncStream to reorder spurious events from Llama Stack.

    Llama Stack emits ``ResponseFunctionCallArgumentsDeltaEvent`` for MCP tool calls
    *before* the ``ResponseOutputItemAddedEvent`` that announces them.  This wrapper
    buffers those early deltas and replays them once the announcement arrives.

    For ``McpCall`` items specifically, pydantic_ai registers the part with a
    ``-call`` vendor_part_id suffix.  Buffered deltas are therefore replayed as a
    single combined event with the suffixed ``item_id`` so they match the part, plus
    a closing ``}`` to complete the outer JSON object that pydantic_ai opens.
    """

    def __init__(self, source: AsyncStream[responses.ResponseStreamEvent]) -> None:
        """Wrap an existing stream with reordering logic.

        Args:
            source: The raw OpenAI AsyncStream to reorder.
        """
        self._source = source
        self._announced_item_ids: set[str] = set()
        self._buffered_deltas: dict[
            str, list[responses.ResponseFunctionCallArgumentsDeltaEvent]
        ] = defaultdict(list)

    async def close(self) -> None:
        """Close the underlying stream."""
        await self._source.close()

    def __aiter__(self) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Return async iterator that reorders events."""
        return self._filtered_iter()

    async def _filtered_iter(
        self,
    ) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Yield events, buffering early argument deltas until their item is announced."""
        async for event in self._source:
            if isinstance(event, responses.ResponseOutputItemAddedEvent):
                if isinstance(event.item, responses.ResponseFunctionToolCall) and event.item.id:
                    item_id = event.item.id
                    self._announced_item_ids.add(item_id)
                    yield event
                    for delta in self._replay_buffered_deltas(item_id):
                        yield delta
                    continue

                if isinstance(event.item, responses.response_output_item.McpCall):
                    item_id = event.item.id
                    self._announced_item_ids.add(item_id)
                    yield event
                    for delta in self._replay_mcp_buffered_deltas(item_id):
                        yield delta
                    continue

            elif isinstance(event, responses.ResponseFunctionCallArgumentsDeltaEvent):
                if event.item_id not in self._announced_item_ids:
                    logger.debug(
                        "Buffering early argument delta for unannounced item_id=%s",
                        event.item_id,
                    )
                    self._buffered_deltas[event.item_id].append(event)
                    continue

            yield event

    def _replay_buffered_deltas(
        self, item_id: str
    ) -> list[responses.ResponseFunctionCallArgumentsDeltaEvent]:
        """Return buffered deltas for a ``ResponseFunctionToolCall`` announcement.

        Args:
            item_id: The announced item ID.

        Returns:
            List of buffered delta events to yield, unchanged.
        """
        buffered = self._buffered_deltas.pop(item_id, [])
        if buffered:
            logger.debug(
                "Replaying %d buffered argument deltas for item_id=%s",
                len(buffered),
                item_id,
            )
        return buffered

    def _replay_mcp_buffered_deltas(
        self, item_id: str
    ) -> list[responses.ResponseFunctionCallArgumentsDeltaEvent]:
        """Return buffered deltas for an ``McpCall`` announcement.

        pydantic_ai registers ``McpCall`` parts with ``vendor_part_id=f'{id}-call'``
        and seeds the args string with everything up to ``"tool_args":``.  The
        buffered deltas contain the actual ``tool_args`` content.  We combine them
        into a single delta with the suffixed ``item_id`` and append a closing ``}``
        to complete the outer JSON object that pydantic_ai opened.

        Args:
            item_id: The announced McpCall item ID.

        Returns:
            List containing one synthetic delta event, or empty if nothing buffered.
        """
        buffered = self._buffered_deltas.pop(item_id, [])
        if not buffered:
            return []

        combined_args = "".join(d.delta for d in buffered) + "}"
        logger.debug(
            "Replaying %d buffered MCP argument deltas as single event "
            "for item_id=%s-call",
            len(buffered),
            item_id,
        )
        return [
            responses.ResponseFunctionCallArgumentsDeltaEvent(
                delta=combined_args,
                item_id=f"{item_id}-call",
                output_index=buffered[0].output_index,
                sequence_number=buffered[-1].sequence_number + 1,
                type="response.function_call_arguments.delta",
            )
        ]


class LlamaStackResponsesModel(OpenAIResponsesModel):
    """OpenAI Responses model with Llama Stack streaming compatibility fixes.

    Overrides the streaming response processing to buffer and replay
    ``ResponseFunctionCallArgumentsDeltaEvent`` events that Llama Stack emits
    before the corresponding ``McpCall`` or ``ResponseFunctionToolCall`` item.
    """

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Request a streaming response, filtering Llama Stack-specific event quirks.

        Args:
            messages: Model messages for the request.
            model_settings: Model-specific settings.
            model_request_parameters: Request parameters for the model.
            run_context: Optional run context from the agent.

        Yields:
            A StreamedResponse with the filtered event stream.
        """
        check_allow_model_requests()
        model_settings, model_request_parameters = self.prepare_request(
            model_settings,
            model_request_parameters,
        )
        model_settings_cast = cast(
            OpenAIResponsesModelSettings, model_settings or {}
        )
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
                _provider_timestamp=number_to_datetime(
                    first_chunk.response.created_at
                )
                if first_chunk.response.created_at
                else None,
            )
