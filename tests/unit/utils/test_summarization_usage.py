"""Unit tests for the token usage of the summarization calls (LCORE-3910).

Compaction makes LLM calls of its own: one to summarize older turns, and one
to fold the summaries when they grow too large. The provider bills them, so
their usage has to reach the metrics, the quota and the token counts of the
turn. Each call is counted as soon as its response arrived, so the count does
not depend on what becomes of the request afterwards.
"""

from typing import Any, Optional, cast

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from cache.cache_error import CacheError
from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration, InferenceConfiguration
from utils import conversation_compaction as cc
from utils.compaction import (
    RECURSIVE_RESUMMARIZATION_PROMPT,
    SUMMARIZATION_PROMPT,
    recursively_resummarize,
    reported_usage,
    summarize_chunk,
)
from utils.token_counter import TokenCounter
from utils.token_estimator import DEFAULT_ENCODING_NAME

MODEL = "openai/gpt-4o-mini"
CONV = "conv_abc123"
ENDPOINT = "/v1/query"

SUMMARIZATION = TokenCounter(input_tokens=640, output_tokens=72, llm_calls=1)
FOLD = TokenCounter(input_tokens=310, output_tokens=45, llm_calls=1)


def _response(
    mocker: MockerFixture,
    text: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> Any:
    """Build the result of ``client.responses.create``, with or without usage."""
    usage = (
        None
        if input_tokens is None
        else mocker.Mock(input_tokens=input_tokens, output_tokens=output_tokens)
    )
    content = [mocker.Mock(text=text)] if text else []
    return mocker.Mock(output=[mocker.Mock(content=content)], usage=usage)


def _summary(text: str, tokens: int) -> ConversationSummary:
    """Build a summary chunk of the given size."""
    return ConversationSummary(
        summary_text=text,
        summarized_through_turn=2,
        token_count=tokens,
        created_at="2026-09-28T00:00:00Z",
        model_used=MODEL,
    )


def _msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed OGX message item."""
    return OpenAIResponseMessage(role=cast("Any", role), content=text)


def _long_conversation() -> list[OpenAIResponseMessage]:
    """One stored turn, long enough for the next request to summarize it."""
    return [_msg("user", "q1 " * 50), _msg("assistant", "a1 " * 50)]


def _params() -> ResponsesApiParams:
    """Build the parameters of a request on an existing conversation."""
    return ResponsesApiParams(
        input="follow-up",
        model=MODEL,
        conversation=CONV,
        instructions="system prompt",
        store=True,
        stream=False,
    )


# --- adding up usage ---


def test_token_counters_add_up() -> None:
    """The sum counts the tokens and the calls of both, and changes neither."""
    turn = TokenCounter(
        input_tokens=100, output_tokens=50, input_tokens_counted=90, llm_calls=1
    )
    summarization = TokenCounter(
        input_tokens=700, output_tokens=80, input_tokens_counted=600, llm_calls=2
    )

    total = turn + summarization

    assert total == TokenCounter(
        input_tokens=800, output_tokens=130, input_tokens_counted=690, llm_calls=3
    )
    assert turn == TokenCounter(
        input_tokens=100, output_tokens=50, input_tokens_counted=90, llm_calls=1
    )
    assert summarization == TokenCounter(
        input_tokens=700, output_tokens=80, input_tokens_counted=600, llm_calls=2
    )


def test_adding_nothing_changes_nothing() -> None:
    """A request that did not summarize adds an empty counter."""
    turn = TokenCounter(input_tokens=100, output_tokens=50, llm_calls=1)

    assert turn + TokenCounter() == turn


# --- what the provider reported ---


def test_reported_usage(mocker: MockerFixture) -> None:
    """The usage of a call is what the provider reported for it."""
    assert reported_usage(_response(mocker, "text", 640, 72)) == SUMMARIZATION


@pytest.mark.parametrize(
    "usage",
    [None, {"input_tokens": None, "output_tokens": None}, {}],
    ids=["no usage", "empty counts", "no counts"],
)
def test_call_without_reported_usage_is_still_a_call(
    mocker: MockerFixture, usage: Optional[dict[str, Any]]
) -> None:
    """A provider that reports no usage leaves the counts at zero; the call counts."""
    response = mocker.Mock(
        usage=None if usage is None else mocker.Mock(spec_set=list(usage), **usage)
    )

    assert reported_usage(response) == TokenCounter(llm_calls=1)


# --- what the two calls report ---


@pytest.mark.asyncio
async def test_summarize_chunk_reports_its_call(mocker: MockerFixture) -> None:
    """The summarization call is reported with the usage the provider gave."""
    client = mocker.AsyncMock()
    client.responses.create.return_value = _response(mocker, "a summary", 640, 72)
    count_call = mocker.Mock()

    await summarize_chunk(
        client=client,
        model=MODEL,
        old_items=[_msg("user", "hi")],
        summarized_through_turn=1,
        encoding_name=DEFAULT_ENCODING_NAME,
        count_call=count_call,
    )

    count_call.assert_called_once_with(MODEL, SUMMARIZATION)


@pytest.mark.asyncio
async def test_summarize_chunk_reports_a_call_that_returned_no_text(
    mocker: MockerFixture,
) -> None:
    """The call was made and billed, even when there is no summary in the answer."""
    client = mocker.AsyncMock()
    client.responses.create.return_value = _response(mocker, "", 640, 72)
    count_call = mocker.Mock()

    with pytest.raises(ValueError, match="no extractable text"):
        await summarize_chunk(
            client=client,
            model=MODEL,
            old_items=[_msg("user", "hi")],
            summarized_through_turn=1,
            encoding_name=DEFAULT_ENCODING_NAME,
            count_call=count_call,
        )

    count_call.assert_called_once_with(MODEL, SUMMARIZATION)


@pytest.mark.asyncio
async def test_summarize_chunk_reports_nothing_for_a_call_that_failed(
    mocker: MockerFixture,
) -> None:
    """A call that raised has no response, so there is no usage to report."""
    client = mocker.AsyncMock()
    client.responses.create.side_effect = RuntimeError("the model is down")
    count_call = mocker.Mock()

    with pytest.raises(RuntimeError):
        await summarize_chunk(
            client=client,
            model=MODEL,
            old_items=[_msg("user", "hi")],
            summarized_through_turn=1,
            encoding_name=DEFAULT_ENCODING_NAME,
            count_call=count_call,
        )

    count_call.assert_not_called()


@pytest.mark.asyncio
async def test_fold_reports_its_call(mocker: MockerFixture) -> None:
    """The fold call is reported with the usage the provider gave."""
    client = mocker.AsyncMock()
    client.responses.create.return_value = _response(mocker, "folded", 310, 45)
    count_call = mocker.Mock()

    await recursively_resummarize(
        client,
        MODEL,
        [_summary("one", 5), _summary("two", 5)],
        DEFAULT_ENCODING_NAME,
        count_call=count_call,
    )

    count_call.assert_called_once_with(MODEL, FOLD)


@pytest.mark.asyncio
async def test_fold_reports_a_call_that_returned_no_text(
    mocker: MockerFixture,
) -> None:
    """The fold call was made and billed, even when its answer is empty."""
    client = mocker.AsyncMock()
    client.responses.create.return_value = _response(mocker, "", 310, 45)
    count_call = mocker.Mock()

    with pytest.raises(ValueError, match="no extractable"):
        await recursively_resummarize(
            client,
            MODEL,
            [_summary("one", 5), _summary("two", 5)],
            DEFAULT_ENCODING_NAME,
            count_call=count_call,
        )

    count_call.assert_called_once_with(MODEL, FOLD)


# --- what a request records, charges and is told ---


@pytest.fixture(name="recorded")
def recorded_fixture(mocker: MockerFixture) -> Any:
    """Replace the metric recorders and return them."""
    return mocker.patch("utils.compaction_usage.recording")


def _answering(mocker: MockerFixture, answers: dict[str, Any]) -> Any:
    """Build an OGX client that answers each LLM call by its instructions.

    Parameters:
        mocker: The pytest-mock fixture.
        answers: The response, or the error to raise, per ``instructions``.

    Returns:
        The mocked client.
    """

    async def _create(**kwargs: Any) -> Any:
        """Answer one call."""
        answer = answers[kwargs["instructions"]]
        if isinstance(answer, Exception):
            raise answer
        return answer

    client = mocker.AsyncMock()
    client.responses.create = mocker.AsyncMock(side_effect=_create)
    return client


async def _compact(  # pylint: disable=too-many-arguments
    mocker: MockerFixture,
    client: Any,
    items: list[Any],
    *,
    charge: Any = None,
    cache: Any = None,
    write_marker: Any = None,
    endpoint_path: Optional[str] = ENDPOINT,
    threshold_ratio: float = 0.1,
) -> cc.CompactionResult:
    """Apply compaction to a follow-up request on the stored items."""
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    mocker.patch.object(cc, "_write_summary_marker", write_marker or mocker.AsyncMock())
    return await cc.apply_compaction_blocking(
        client=client,
        params=_params(),
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
        endpoint_path=endpoint_path,
        charge=charge,
    )


def _summarizing(mocker: MockerFixture) -> Any:
    """Build a client whose summarization call succeeds."""
    return _answering(
        mocker, {SUMMARIZATION_PROMPT: _response(mocker, "condensed", 640, 72)}
    )


@pytest.mark.asyncio
async def test_request_that_summarizes(mocker: MockerFixture, recorded: Any) -> None:
    """The call is recorded in the metrics, charged, and the request is told."""
    charge = mocker.Mock()

    result = await _compact(
        mocker, _summarizing(mocker), _long_conversation(), charge=charge
    )

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
    client = _summarizing(mocker)
    charge = mocker.Mock()
    marker = _msg("user", f"{cc.MARKER_SENTINEL} an earlier summary")

    result = await _compact(
        mocker, client, [marker], charge=charge, threshold_ratio=0.9
    )

    client.responses.create.assert_not_awaited()
    assert result.compacted is True
    assert result.summarization_usage == TokenCounter()
    charge.assert_not_called()
    recorded.record_llm_token_usage.assert_not_called()
    recorded.record_llm_call.assert_not_called()


@pytest.mark.asyncio
async def test_request_on_a_short_conversation(
    mocker: MockerFixture, recorded: Any
) -> None:
    """A request that is not compacted at all counts nothing."""
    charge = mocker.Mock()

    result = await _compact(
        mocker,
        _summarizing(mocker),
        [_msg("user", "hi")],
        charge=charge,
        threshold_ratio=0.9,
    )

    assert result.compacted is False
    assert result.summarization_usage == TokenCounter()
    charge.assert_not_called()
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
            _summarizing(mocker),
            _long_conversation(),
            charge=charge,
            write_marker=mocker.AsyncMock(
                side_effect=RuntimeError("the store is down")
            ),
        )

    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_token_usage.assert_called_once_with(
        "openai", "gpt-4o-mini", 640, 72, ENDPOINT
    )


@pytest.mark.asyncio
async def test_call_that_returned_no_text_is_counted(
    mocker: MockerFixture, recorded: Any
) -> None:
    """The request fails for want of a summary; the call is counted all the same."""
    client = _answering(mocker, {SUMMARIZATION_PROMPT: _response(mocker, "", 640, 72)})
    charge = mocker.Mock()

    with pytest.raises(ValueError, match="no extractable text"):
        await _compact(mocker, client, _long_conversation(), charge=charge)

    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


@pytest.mark.asyncio
async def test_call_without_reported_usage_records_the_call_only(
    mocker: MockerFixture, recorded: Any
) -> None:
    """There are no tokens to record; the call is recorded and handed on."""
    client = _answering(mocker, {SUMMARIZATION_PROMPT: _response(mocker, "condensed")})
    charge = mocker.Mock()

    result = await _compact(mocker, client, _long_conversation(), charge=charge)

    assert result.summarization_usage == TokenCounter(llm_calls=1)
    charge.assert_called_once_with(MODEL, TokenCounter(llm_calls=1))
    recorded.record_llm_token_usage.assert_not_called()
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


@pytest.mark.asyncio
async def test_no_metrics_without_an_endpoint(
    mocker: MockerFixture, recorded: Any
) -> None:
    """A caller that does not say which endpoint it serves records no metrics."""
    charge = mocker.Mock()

    result = await _compact(
        mocker,
        _summarizing(mocker),
        _long_conversation(),
        charge=charge,
        endpoint_path=None,
    )

    assert result.summarization_usage == SUMMARIZATION
    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_token_usage.assert_not_called()
    recorded.record_llm_call.assert_not_called()


@pytest.mark.asyncio
async def test_nobody_is_charged_without_a_charge(
    mocker: MockerFixture, recorded: Any
) -> None:
    """An endpoint without a quota records the call and charges nobody."""
    result = await _compact(mocker, _summarizing(mocker), _long_conversation())

    assert result.summarization_usage == SUMMARIZATION
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


def _cache_with_two_summaries(mocker: MockerFixture) -> Any:
    """Build a cache whose summaries cross the fold threshold with one more."""
    cache = mocker.Mock()
    cache.get_summaries.return_value = [_summary("one", 20), _summary("two", 20)]
    return cache


@pytest.mark.asyncio
async def test_summarization_and_fold_are_both_counted(
    mocker: MockerFixture, recorded: Any
) -> None:
    """A request that summarizes and then folds is charged for each of the calls."""
    client = _answering(
        mocker,
        {
            SUMMARIZATION_PROMPT: _response(mocker, "third", 640, 72),
            RECURSIVE_RESUMMARIZATION_PROMPT: _response(mocker, "folded", 310, 45),
        },
    )
    charge = mocker.Mock()

    result = await _compact(
        mocker,
        client,
        _long_conversation(),
        charge=charge,
        cache=_cache_with_two_summaries(mocker),
    )

    assert result.summarization_usage == TokenCounter(
        input_tokens=950, output_tokens=117, llm_calls=2
    )
    assert charge.call_args_list == [
        mocker.call(MODEL, SUMMARIZATION),
        mocker.call(MODEL, FOLD),
    ]
    assert recorded.record_llm_call.call_count == 2


@pytest.mark.asyncio
async def test_summarization_is_counted_when_the_fold_fails(
    mocker: MockerFixture, recorded: Any
) -> None:
    """The summary is stored by then and never made again, so it is charged now."""
    client = _answering(
        mocker,
        {
            SUMMARIZATION_PROMPT: _response(mocker, "third", 640, 72),
            RECURSIVE_RESUMMARIZATION_PROMPT: RuntimeError("the model is down"),
        },
    )
    charge = mocker.Mock()

    with pytest.raises(RuntimeError, match="the model is down"):
        await _compact(
            mocker,
            client,
            _long_conversation(),
            charge=charge,
            cache=_cache_with_two_summaries(mocker),
        )

    charge.assert_called_once_with(MODEL, SUMMARIZATION)
    recorded.record_llm_call.assert_called_once_with("openai", "gpt-4o-mini", ENDPOINT)


@pytest.mark.asyncio
async def test_fold_that_could_not_be_stored_is_counted(
    mocker: MockerFixture, recorded: Any
) -> None:
    """The fold call was made and billed, even when its result cannot be kept."""
    _ = recorded
    client = _answering(
        mocker,
        {
            SUMMARIZATION_PROMPT: _response(mocker, "third", 640, 72),
            RECURSIVE_RESUMMARIZATION_PROMPT: _response(mocker, "folded", 310, 45),
        },
    )
    cache = _cache_with_two_summaries(mocker)
    cache.replace_summaries.side_effect = CacheError("the cache is down")
    charge = mocker.Mock()

    result = await _compact(
        mocker, client, _long_conversation(), charge=charge, cache=cache
    )

    assert charge.call_args_list == [
        mocker.call(MODEL, SUMMARIZATION),
        mocker.call(MODEL, FOLD),
    ]
    texts = [message.content for message in result.params.input]
    assert not any("folded" in text for text in texts)
