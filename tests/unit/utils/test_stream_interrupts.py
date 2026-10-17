"""Unit tests for stream interrupt registry and persistence utilities."""

import asyncio
from typing import Any

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from constants import INTERRUPTED_RESPONSE_MESSAGE
from models.api.requests import QueryRequest
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.common.turn_summary import TurnSummary
from utils.pending_turn import PendingTurn
from utils.stream_interrupts import (
    StreamInterruptRegistry,
    build_interrupted_response,
    persist_interrupted_turn,
    register_interrupt_callback,
)
from utils.token_estimator import extract_message_text

INTERRUPTED_INDICATOR = f"\n\n*{INTERRUPTED_RESPONSE_MESSAGE}*"


def _params(
    conversation: str,
    input_items: ResponseInput,
    omit_conversation: bool = False,
) -> ResponsesApiParams:
    """Build the parameters of a streaming request."""
    return ResponsesApiParams(
        input=input_items,
        model="provider1/model1",
        conversation=conversation,
        store=True,
        stream=True,
        omit_conversation=omit_conversation,
    )


def _capture_conversation_writes(context: Any) -> list[tuple[str, str]]:
    """Wire a stateful fake onto the client and return what it is asked to store."""
    stored: list[tuple[str, str]] = []

    async def _create(
        _conversation_id: str, *, add_items_request: Any = None, **_kwargs: Any
    ) -> None:
        stored.extend(
            (str(item.role), extract_message_text(item))
            for item in add_items_request.items
        )

    context.client.items.create = _create
    return stored


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

    stored = _capture_conversation_writes(context)

    responses_params = _params(
        conversation=conv,
        input_items=[OpenAIResponseMessage(role="user", content="explicit rewrite")],
        omit_conversation=True,
    )

    turn_summary = TurnSummary()
    turn_summary.llm_response = f"partial content{INTERRUPTED_INDICATOR}"
    background_tasks: list[asyncio.Task[None]] = []
    mocker.patch("utils.stream_interrupts.store_query_results")

    await persist_interrupted_turn(
        context,
        responses_params,
        turn_summary,
        background_tasks,
        turn=PendingTurn.for_request(
            context.client, responses_params, "the original query"
        ),
    )

    assert stored == [
        ("user", "the original query"),
        ("assistant", f"partial content{INTERRUPTED_INDICATOR}"),
    ]


@pytest.mark.asyncio
async def test_persist_interrupted_turn_stores_the_turn_once(
    mocker: MockerFixture,
) -> None:
    """Both reactions to an interrupt persist; the conversation gains one turn.

    The cancellation handler and the interrupt callback are told apart by a
    guard of their own. Should both get through, the turn still is stored
    once, because they share its owner (LCORE-3908).
    """
    context = mocker.Mock(spec=ResponseGeneratorContext)
    context.client = mocker.AsyncMock()
    context.request_id = "req-1"
    context.user_id = "user_1"
    context.conversation_id = "conv_1"
    context.started_at = "2024-01-01T00:00:00Z"
    context.skip_userid_check = False
    context.query_request = QueryRequest(
        query="hi", conversation_id=None
    )  # pyright: ignore[reportCallIssue]
    stored = _capture_conversation_writes(context)
    responses_params = _params(conversation="conv_1", input_items="hi")
    turn = PendingTurn.for_request(context.client, responses_params)

    turn_summary = TurnSummary()
    turn_summary.llm_response = f"partial{INTERRUPTED_INDICATOR}"
    mocker.patch("utils.stream_interrupts.store_query_results")

    await persist_interrupted_turn(context, responses_params, turn_summary, [], turn)
    await persist_interrupted_turn(context, responses_params, turn_summary, [], turn)

    assert stored == [
        ("user", "hi"),
        ("assistant", f"partial{INTERRUPTED_INDICATOR}"),
    ]


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

    responses_params = _params(conversation="conv_new", input_items="hello")

    turn_summary = TurnSummary()
    turn_summary.llm_response = INTERRUPTED_INDICATOR
    background_tasks: list[asyncio.Task[None]] = []

    mocker.patch("utils.stream_interrupts.store_query_results")
    background_mock = mocker.patch(
        "utils.stream_interrupts.background_update_topic_summary",
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
        "utils.stream_interrupts.get_stream_interrupt_registry",
        return_value=registry,
    )
    persist_mock = mocker.patch(
        "utils.stream_interrupts.persist_interrupted_turn",
        new=mocker.AsyncMock(),
    )

    context = mocker.Mock(spec=ResponseGeneratorContext)
    context.request_id = "req-1"
    context.user_id = "user_1"
    context.conversation_id = "conv-1"
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
    assert registry.register_stream.call_args.kwargs["conversation_id"] == "conv-1"
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
