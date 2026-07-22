"""Unit tests for stream interrupt registry and persistence utilities."""

import asyncio

import pytest
from pytest_mock import MockerFixture

from lightspeed_stack.constants import INTERRUPTED_RESPONSE_MESSAGE
from lightspeed_stack.models.api.requests import QueryRequest
from lightspeed_stack.models.common.responses.contexts import ResponseGeneratorContext
from lightspeed_stack.models.common.responses.responses_api_params import (
    ResponsesApiParams,
)
from lightspeed_stack.models.common.turn_summary import TurnSummary
from lightspeed_stack.utils.stream_interrupts import (
    StreamInterruptRegistry,
    build_interrupted_response,
    persist_interrupted_turn,
    register_interrupt_callback,
)

INTERRUPTED_INDICATOR = f"\n\n*{INTERRUPTED_RESPONSE_MESSAGE}*"


@pytest.mark.asyncio
async def test_persist_interrupted_turn_compacted_uses_original_input(
    mocker: MockerFixture,
) -> None:
    """Interrupted compacted turn persists the original input (LCORE-1572).

    Not the explicit rewrite carried on responses_params.input.
    """
    conv = "123e4567-e89b-12d3-a456-426614174000"
    context = mocker.Mock(spec=ResponseGeneratorContext)
    context.client = mocker.AsyncMock()
    context.request_id = "req-1"
    context.user_id = "user_1"
    context.conversation_id = conv
    context.started_at = "2024-01-01T00:00:00Z"
    context.skip_userid_check = False
    context.query_request = QueryRequest(
        query="hi", conversation_id=conv
    )  # pyright: ignore[reportCallIssue]

    responses_params = mocker.Mock(spec=ResponsesApiParams)
    responses_params.conversation = conv
    responses_params.model = "provider1/model1"
    responses_params.input = ["explicit rewrite"]

    turn_summary = TurnSummary()
    turn_summary.llm_response = f"partial content{INTERRUPTED_INDICATOR}"
    background_tasks: list[asyncio.Task[None]] = []
    items = mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.append_turn_items_to_conversation",
        new=mocker.AsyncMock(),
    )
    strs = mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.append_turn_to_conversation",
        new=mocker.AsyncMock(),
    )
    mocker.patch("lightspeed_stack.utils.stream_interrupts.store_query_results")

    await persist_interrupted_turn(
        context,
        responses_params,
        turn_summary,
        background_tasks,
        original_input="the original query",
    )

    items.assert_awaited_once()
    assert items.call_args.args[2] == "the original query"
    call_output = items.call_args.args[3]
    assert call_output[0].content == f"partial content{INTERRUPTED_INDICATOR}"
    strs.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_interrupted_turn_schedules_background_topic_summary(
    mocker: MockerFixture,
) -> None:
    """New conversations with generate_topic_summary enqueue a background task."""
    context = mocker.Mock(spec=ResponseGeneratorContext)
    context.client = mocker.AsyncMock()
    context.request_id = "req-1"
    context.user_id = "user_1"
    context.conversation_id = "conv_new"
    context.started_at = "2024-01-01T00:00:00Z"
    context.skip_userid_check = False
    context.query_request = QueryRequest(
        query="hello",
        conversation_id=None,
        generate_topic_summary=True,
    )  # pyright: ignore[reportCallIssue]

    responses_params = mocker.Mock(spec=ResponsesApiParams)
    responses_params.conversation = "conv_new"
    responses_params.model = "provider1/model1"
    responses_params.input = "hello"

    turn_summary = TurnSummary()
    turn_summary.llm_response = INTERRUPTED_INDICATOR
    background_tasks: list[asyncio.Task[None]] = []

    mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.append_turn_to_conversation",
        new=mocker.AsyncMock(),
    )
    mocker.patch("lightspeed_stack.utils.stream_interrupts.store_query_results")
    background_mock = mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.background_update_topic_summary",
        new=mocker.AsyncMock(),
    )

    await persist_interrupted_turn(
        context, responses_params, turn_summary, background_tasks
    )

    assert len(background_tasks) == 1
    await background_tasks[0]
    background_mock.assert_awaited_once_with(
        context=context,
        model="provider1/model1",
    )


def test_register_interrupt_callback_registers_current_task(
    mocker: MockerFixture,
) -> None:
    """register_interrupt_callback binds the current asyncio task to the registry."""
    registry = mocker.Mock(spec=StreamInterruptRegistry)
    mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.get_stream_interrupt_registry",
        return_value=registry,
    )
    persist_mock = mocker.patch(
        "lightspeed_stack.utils.stream_interrupts.persist_interrupted_turn",
        new=mocker.AsyncMock(),
    )

    context = mocker.Mock(spec=ResponseGeneratorContext)
    context.request_id = "req-1"
    context.user_id = "user_1"
    responses_params = mocker.Mock(spec=ResponsesApiParams)
    turn_summary = TurnSummary()
    background_tasks: list[asyncio.Task[None]] = []

    async def run() -> list[bool]:
        return register_interrupt_callback(
            context,
            responses_params,
            turn_summary,
            background_tasks,
        )

    guard = asyncio.run(run())

    assert guard == [False]
    registry.register_stream.assert_called_once()
    assert registry.register_stream.call_args.kwargs["request_id"] == "req-1"
    assert registry.register_stream.call_args.kwargs["user_id"] == "user_1"
    assert persist_mock.await_count == 0

    on_interrupt = registry.register_stream.call_args.kwargs["on_interrupt"]

    async def invoke_callback() -> None:
        await on_interrupt()

    asyncio.run(invoke_callback())
    persist_mock.assert_awaited_once()


class TestBuildInterruptedResponse:
    """Tests for build_interrupted_response helper."""

    def test_plain_text_partial(self) -> None:
        """Plain text tokens produce text + indicator."""
        tokens = ["Hello ", "world"]
        full, suffix = build_interrupted_response(tokens)
        assert full == f"Hello world{INTERRUPTED_INDICATOR}"
        assert suffix == INTERRUPTED_INDICATOR

    def test_unclosed_code_fence(self) -> None:
        """Unclosed code fence is closed before indicator."""
        tokens = ["```python\n", "def foo():\n", "    pass"]
        full, suffix = build_interrupted_response(tokens)
        assert "```" in suffix
        assert suffix.endswith(INTERRUPTED_INDICATOR)
        assert full.startswith("```python\ndef foo():\n    pass")

    def test_empty_tokens(self) -> None:
        """Empty token list produces just the indicator."""
        full, suffix = build_interrupted_response([])
        assert full == INTERRUPTED_INDICATOR
        assert suffix == INTERRUPTED_INDICATOR
