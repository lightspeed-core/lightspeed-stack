"""Unit tests for the accounting of the summarization calls (LCORE-3910).

Compaction makes LLM calls of its own: one to summarize older turns, and one
to fold the summaries when they grow too large. The provider bills them, so
each is counted as soon as its response arrived: recorded in the LLM metrics,
handed to ``charge``, and added to the usage the request is told.
"""

# pylint: disable=protected-access

from typing import Any

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration, InferenceConfiguration
from utils import conversation_compaction as cc
from utils.token_counter import TokenCounter

MODEL = "openai/gpt-4o-mini"
ENDPOINT = "/v1/query"

SUMMARIZATION = TokenCounter(input_tokens=640, output_tokens=72, llm_calls=1)
FOLD = TokenCounter(input_tokens=310, output_tokens=45, llm_calls=1)


def _response(mocker: MockerFixture, text: str, usage: TokenCounter) -> Any:
    """Build the result of ``client.responses.create`` with the given usage."""
    return mocker.Mock(
        output=[mocker.Mock(content=[mocker.Mock(text=text)])],
        usage=mocker.Mock(
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens
        ),
    )


def _client(mocker: MockerFixture) -> Any:
    """Build an OGX client that answers the summarization, then the fold call."""
    client = mocker.AsyncMock()
    client.responses.create.side_effect = [
        _response(mocker, "condensed", SUMMARIZATION),
        _response(mocker, "folded", FOLD),
    ]
    return client


LONG_CONVERSATION = [
    OpenAIResponseMessage(role="user", content="q1 " * 50),
    OpenAIResponseMessage(role="assistant", content="a1 " * 50),
]
"""One stored turn, long enough for the next request to summarize it."""


@pytest.fixture(name="recorded")
def recorded_fixture(mocker: MockerFixture) -> Any:
    """Replace the metric recorders and return them."""
    return mocker.patch("utils.compaction_usage.recording")


async def _compact(  # pylint: disable=too-many-arguments
    mocker: MockerFixture,
    items: list[Any],
    *,
    charge: Any = None,
    cache: Any = None,
    write_marker: Any = None,
    threshold_ratio: float = 0.1,
) -> cc.CompactionResult:
    """Apply compaction to a follow-up request on the stored items."""
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    mocker.patch.object(cc, "_write_summary_marker", write_marker or mocker.AsyncMock())
    return await cc.apply_compaction_blocking(
        client=_client(mocker),
        params=ResponsesApiParams(
            input="follow-up",
            model=MODEL,
            conversation="conv_abc123",
            instructions="system prompt",
            store=True,
            stream=False,
        ),
        inference_config=InferenceConfiguration(context_windows={MODEL: 50}),
        compaction_config=CompactionConfiguration(
            enabled=True,
            threshold_ratio=threshold_ratio,
            token_floor=0,
            buffer_turns=0,
            buffer_max_ratio=0.3,
        ),
        cache=cache,
        user_id="u1",
        endpoint_path=ENDPOINT,
        charge=charge,
    )


def test_token_counters_add_up() -> None:
    """The sum counts the tokens and the calls of both, and changes neither."""
    turn = TokenCounter(100, 50, input_tokens_counted=90, llm_calls=1)

    assert turn + SUMMARIZATION == TokenCounter(
        input_tokens=740, output_tokens=122, input_tokens_counted=90, llm_calls=2
    )
    assert SUMMARIZATION + turn == turn + SUMMARIZATION
    assert turn == TokenCounter(100, 50, input_tokens_counted=90, llm_calls=1)
    assert SUMMARIZATION == TokenCounter(640, 72, llm_calls=1)


@pytest.mark.asyncio
async def test_request_that_summarizes(mocker: MockerFixture, recorded: Any) -> None:
    """The call is recorded in the metrics, charged, and the request is told."""
    charge = mocker.Mock()

    result = await _compact(mocker, LONG_CONVERSATION, charge=charge)

    assert result.compacted is True
    assert result.summarization_usage == SUMMARIZATION
    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_token_usage.assert_called_once_with(
        "openai", "gpt-4o-mini", 640, 72, ENDPOINT
    )
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


@pytest.mark.asyncio
async def test_request_served_from_an_earlier_summary(
    mocker: MockerFixture, recorded: Any
) -> None:
    """A request that makes no summarization call counts nothing."""
    charge = mocker.Mock()
    marker = OpenAIResponseMessage(
        role="user", content=f"{cc.MARKER_SENTINEL} an earlier summary"
    )

    result = await _compact(mocker, [marker], charge=charge, threshold_ratio=0.9)

    assert result.compacted is True
    assert result.summarization_usage == TokenCounter()
    charge.assert_not_called()
    recorded.record_llm_token_usage.assert_not_called()
    recorded.record_llm_call.assert_not_called()


@pytest.mark.asyncio
async def test_call_is_counted_when_the_marker_cannot_be_written(
    mocker: MockerFixture, recorded: Any
) -> None:
    """The request fails after the call was made; the call is counted all the same."""
    charge = mocker.Mock()

    with pytest.raises(RuntimeError, match="the store is down"):
        await _compact(
            mocker,
            LONG_CONVERSATION,
            charge=charge,
            write_marker=mocker.AsyncMock(
                side_effect=RuntimeError("the store is down")
            ),
        )

    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


@pytest.mark.asyncio
async def test_summarization_and_fold_are_both_counted(
    mocker: MockerFixture, recorded: Any
) -> None:
    """A request that summarizes and then folds counts each of the two calls."""
    earlier = ConversationSummary(
        summary_text="earlier",
        summarized_through_turn=2,
        token_count=20,
        created_at="2026-09-28T00:00:00Z",
        model_used=MODEL,
    )
    cache = mocker.Mock()
    cache.get_summaries.return_value = [earlier, earlier]
    charge = mocker.Mock()

    result = await _compact(mocker, LONG_CONVERSATION, charge=charge, cache=cache)

    assert result.summarization_usage == TokenCounter(
        input_tokens=950, output_tokens=117, llm_calls=2
    )
    assert charge.call_args_list == [
        mocker.call(MODEL, SUMMARIZATION),
        mocker.call(MODEL, FOLD),
    ]
    assert recorded.record_llm_token_usage.call_args_list == [
        mocker.call("openai", "gpt-4o-mini", 640, 72, ENDPOINT),
        mocker.call("openai", "gpt-4o-mini", 310, 45, ENDPOINT),
    ]
    assert recorded.record_llm_call.call_count == 2
