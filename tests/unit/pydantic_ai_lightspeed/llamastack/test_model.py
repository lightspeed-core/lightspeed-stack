"""Unit tests for pydantic_ai_lightspeed.llamastack._model module."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from openai.types import responses

from pydantic_ai_lightspeed.llamastack._model import _FilteredResponseStream


class _FakeAsyncStream:
    """Minimal AsyncStream stand-in for _FilteredResponseStream tests."""

    def __init__(self, events: list[responses.ResponseStreamEvent]) -> None:
        """Store events to replay from the fake stream.

        Args:
            events: Ordered upstream events before reordering.
        """
        self._events = events

    def __aiter__(self) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Return an async iterator over the configured events."""
        return self._iter_events()

    async def _iter_events(self) -> AsyncIterator[responses.ResponseStreamEvent]:
        """Yield each configured event in order."""
        for event in self._events:
            yield event

    async def close(self) -> None:
        """No-op close for test double compatibility."""


async def _collect_events(
    stream: _FilteredResponseStream,
) -> list[responses.ResponseStreamEvent]:
    """Drain a filtered stream into a list.

    Args:
        stream: Filtered response stream under test.

    Returns:
        All events emitted by the filtered stream.
    """
    return [event async for event in stream]


def _function_delta(
    *,
    item_id: str,
    delta: str,
    sequence_number: int,
) -> responses.ResponseFunctionCallArgumentsDeltaEvent:
    """Build a function-call arguments delta test event.

    Args:
        item_id: Tool-call item identifier.
        delta: Argument fragment string.
        sequence_number: Event sequence number.

    Returns:
        Function-call arguments delta event.
    """
    return responses.ResponseFunctionCallArgumentsDeltaEvent.model_validate(
        {
            "type": "response.function_call_arguments.delta",
            "item_id": item_id,
            "output_index": 1,
            "sequence_number": sequence_number,
            "delta": delta,
        }
    )


def _function_done(
    *,
    item_id: str,
    arguments: str,
    sequence_number: int,
) -> responses.ResponseFunctionCallArgumentsDoneEvent:
    """Build a function-call arguments done test event.

    Args:
        item_id: Tool-call item identifier.
        arguments: Final JSON arguments string.
        sequence_number: Event sequence number.

    Returns:
        Function-call arguments done event.
    """
    return responses.ResponseFunctionCallArgumentsDoneEvent.model_validate(
        {
            "type": "response.function_call_arguments.done",
            "item_id": item_id,
            "output_index": 1,
            "sequence_number": sequence_number,
            "arguments": arguments,
            "name": "client_tool",
        }
    )


def _mcp_added(
    *,
    item_id: str,
    sequence_number: int,
) -> responses.ResponseOutputItemAddedEvent:
    """Build an MCP output item added test event.

    Args:
        item_id: MCP tool-call item identifier.
        sequence_number: Event sequence number.

    Returns:
        Output item added event for an MCP call.
    """
    return responses.ResponseOutputItemAddedEvent.model_validate(
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "sequence_number": sequence_number,
            "item": {
                "type": "mcp_call",
                "id": item_id,
                "name": "unit_convert",
                "arguments": "",
                "server_label": "datautils",
            },
        }
    )


@dataclass
class _LlsMcpArgumentsDone:
    """Llama Stack MCP arguments.done event shape before OpenAI SDK normalization."""

    item_id: str
    output_index: int
    sequence_number: int
    arguments: str
    type: str = "response.mcp_call.arguments.done"

    def model_dump(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Return a dict compatible with MCP done normalization.

        Args:
            exclude: Optional field names to omit from the dump.

        Returns:
            Serialized event fields.
        """
        data = {
            "type": self.type,
            "item_id": self.item_id,
            "output_index": self.output_index,
            "sequence_number": self.sequence_number,
            "arguments": self.arguments,
        }
        if exclude:
            for key in exclude:
                data.pop(key, None)
        return data


def _list_tools_added(
    *,
    item_id: str,
    sequence_number: int,
) -> responses.ResponseOutputItemAddedEvent:
    """Build an MCP list-tools output item added test event.

    Args:
        item_id: MCP list-tools item identifier.
        sequence_number: Event sequence number.

    Returns:
        Output item added event for an MCP list-tools call.
    """
    return responses.ResponseOutputItemAddedEvent.model_validate(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": sequence_number,
            "item": {
                "type": "mcp_list_tools",
                "id": item_id,
                "server_label": "datautils",
                "tools": [],
            },
        }
    )


def _list_tools_done(
    *,
    item_id: str,
    sequence_number: int,
) -> responses.ResponseOutputItemDoneEvent:
    """Build an MCP list-tools output item done test event.

    Args:
        item_id: MCP list-tools item identifier.
        sequence_number: Event sequence number.

    Returns:
        Output item done event for an MCP list-tools call.
    """
    return responses.ResponseOutputItemDoneEvent.model_validate(
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "sequence_number": sequence_number,
            "item": {
                "type": "mcp_list_tools",
                "id": item_id,
                "server_label": "datautils",
                "tools": [{"name": "tool_a", "input_schema": {}}],
            },
        }
    )


def _function_added(
    *,
    item_id: str,
    sequence_number: int,
) -> responses.ResponseOutputItemAddedEvent:
    """Build a function output item added test event.

    Args:
        item_id: Function tool-call item identifier.
        sequence_number: Event sequence number.

    Returns:
        Output item added event for a function tool call.
    """
    return responses.ResponseOutputItemAddedEvent.model_validate(
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "sequence_number": sequence_number,
            "item": {
                "type": "function_call",
                "id": item_id,
                "call_id": "call_123",
                "name": "client_tool",
                "arguments": "",
                "status": "in_progress",
            },
        }
    )


class TestFilteredResponseStream:
    """Tests for _FilteredResponseStream event reordering."""

    @pytest.mark.asyncio
    async def test_reorders_mcp_events_after_output_item_added(self) -> None:
        """Test MCP deltas and done are replayed after output_item.added."""
        item_id = "fc_mcp"
        upstream = [
            _function_delta(item_id=item_id, delta='{"', sequence_number=1),
            _function_delta(item_id=item_id, delta="value", sequence_number=2),
            _function_delta(item_id=item_id, delta='":100}', sequence_number=3),
            _LlsMcpArgumentsDone(
                item_id=item_id,
                output_index=1,
                sequence_number=4,
                arguments='{"value":100}',
            ),
            _mcp_added(item_id=item_id, sequence_number=5),
        ]
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream(upstream))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types[0] == "response.output_item.added"
        assert types[1:4] == ["response.mcp_call_arguments.delta"] * 3
        assert types[4] == "response.mcp_call_arguments.done"
        mcp_deltas = [
            event
            for event in events[1:4]
            if isinstance(event, responses.ResponseMcpCallArgumentsDeltaEvent)
        ]
        assert [delta.delta for delta in mcp_deltas] == ['{"', "value", '":100}']

    @pytest.mark.asyncio
    async def test_reorders_function_events_after_output_item_added(self) -> None:
        """Test function deltas and done are replayed after output_item.added."""
        item_id = "fc_fn"
        delta = _function_delta(item_id=item_id, delta='{"x":1}', sequence_number=1)
        done = _function_done(
            item_id=item_id,
            arguments='{"x":1}',
            sequence_number=2,
        )
        added = _function_added(item_id=item_id, sequence_number=3)
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream([delta, done, added]))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        ]

    @pytest.mark.asyncio
    async def test_passes_through_events_after_output_item_added(self) -> None:
        """Test post-announcement deltas are not buffered."""
        item_id = "fc_live"
        added = _function_added(item_id=item_id, sequence_number=1)
        delta = _function_delta(item_id=item_id, delta='{"x":1}', sequence_number=2)
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream([added, delta]))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.function_call_arguments.delta",
        ]

    @pytest.mark.asyncio
    async def test_reorders_mcp_list_tools_events_after_output_item_added(self) -> None:
        """Test list-tools lifecycle events replay after output_item.added."""
        item_id = "mcp_list_test"
        upstream = [
            responses.ResponseMcpListToolsInProgressEvent.model_validate(
                {
                    "type": "response.mcp_list_tools.in_progress",
                    "item_id": item_id,
                    "output_index": 0,
                    "sequence_number": 1,
                }
            ),
            _list_tools_added(item_id=item_id, sequence_number=2),
            responses.ResponseMcpListToolsCompletedEvent.model_validate(
                {
                    "type": "response.mcp_list_tools.completed",
                    "item_id": item_id,
                    "output_index": 0,
                    "sequence_number": 3,
                }
            ),
            _list_tools_done(item_id=item_id, sequence_number=4),
        ]
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream(upstream))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.mcp_list_tools.in_progress",
            "response.mcp_list_tools.completed",
            "response.output_item.done",
        ]

    @pytest.mark.asyncio
    async def test_reorders_all_mcp_list_tools_events_before_added(self) -> None:
        """Test list-tools events buffered when they all arrive before added."""
        item_id = "mcp_list_early"
        upstream = [
            responses.ResponseMcpListToolsInProgressEvent.model_validate(
                {
                    "type": "response.mcp_list_tools.in_progress",
                    "item_id": item_id,
                    "output_index": 0,
                    "sequence_number": 1,
                }
            ),
            responses.ResponseMcpListToolsCompletedEvent.model_validate(
                {
                    "type": "response.mcp_list_tools.completed",
                    "item_id": item_id,
                    "output_index": 0,
                    "sequence_number": 2,
                }
            ),
            _list_tools_done(item_id=item_id, sequence_number=3),
            _list_tools_added(item_id=item_id, sequence_number=4),
        ]
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream(upstream))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.mcp_list_tools.in_progress",
            "response.mcp_list_tools.completed",
            "response.output_item.done",
        ]

    @pytest.mark.asyncio
    async def test_flushes_buffered_events_when_added_never_arrives(self) -> None:
        """Test buffered events are flushed if output_item.added never arrives."""
        item_id = "fc_orphan"
        delta = _function_delta(item_id=item_id, delta="{}", sequence_number=1)
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream([delta]))  # type: ignore[arg-type]
        )

        assert len(events) == 1
        assert events[0].type == "response.mcp_call_arguments.delta"

    @pytest.mark.asyncio
    async def test_converts_post_added_function_deltas_for_mcp_call(self) -> None:
        """Test function argument deltas after added are rewritten for MCP calls."""
        item_id = "fc_live_mcp"
        added = _mcp_added(item_id=item_id, sequence_number=1)
        delta = _function_delta(item_id=item_id, delta='{"value":1}', sequence_number=2)
        events = await _collect_events(
            _FilteredResponseStream(_FakeAsyncStream([added, delta]))  # type: ignore[arg-type]
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.mcp_call_arguments.delta",
        ]

    @pytest.mark.asyncio
    async def test_buffers_mcp_output_done_until_arguments_done(self) -> None:
        """Test mcp_call output_item.done is held until arguments.done is emitted."""
        item_id = "fc_mcp_done_order"
        added = _mcp_added(item_id=item_id, sequence_number=1)
        output_done = responses.ResponseOutputItemDoneEvent.model_validate(
            {
                "type": "response.output_item.done",
                "output_index": 1,
                "sequence_number": 2,
                "item": {
                    "type": "mcp_call",
                    "id": item_id,
                    "name": "unit_convert",
                    "arguments": '{"action":"call_tool","tool_name":"unit_convert","tool_args":{}}',
                    "server_label": "datautils",
                },
            }
        )
        mcp_done = responses.ResponseMcpCallArgumentsDoneEvent.model_validate(
            {
                "type": "response.mcp_call_arguments.done",
                "item_id": item_id,
                "output_index": 1,
                "sequence_number": 3,
                "arguments": "{}",
            }
        )
        events = await _collect_events(
            _FilteredResponseStream(  # type: ignore[arg-type]
                _FakeAsyncStream([added, output_done, mcp_done])
            )
        )
        types = [event.type for event in events]

        assert types == [
            "response.output_item.added",
            "response.mcp_call_arguments.done",
            "response.output_item.done",
        ]
