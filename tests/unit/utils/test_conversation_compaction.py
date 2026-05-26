"""Unit tests for runtime conversation compaction (LCORE-1572)."""

# Tests exercise internal helpers directly.
# pylint: disable=protected-access

from typing import Any

import pytest
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration, InferenceConfiguration
from utils import conversation_compaction as cc

MODEL = "openai/gpt-4o-mini"
CONV = "conv_abc123"


def _msg(role: str, text: str) -> dict:
    """Build a duck-typed conversation message item."""
    return {"role": role, "content": text}


def _marker(text: str) -> dict:
    """Build a summary marker message item."""
    return {"role": "user", "content": f"{cc.MARKER_SENTINEL} {text}"}


def _params(input_text: str = "new question") -> ResponsesApiParams:
    return ResponsesApiParams(
        input=input_text,
        model=MODEL,
        conversation=CONV,
        instructions="system prompt",
        store=True,
        stream=False,
    )


def _inference(window: int | None) -> InferenceConfiguration:
    windows = {MODEL: window} if window is not None else {}
    return InferenceConfiguration(context_windows=windows)


def _compaction(**kw: Any) -> CompactionConfiguration:
    base = {
        "enabled": True,
        "threshold_ratio": 0.5,
        "token_floor": 0,
        "buffer_turns": 1,
        "buffer_max_ratio": 0.3,
    }
    base.update(kw)
    return CompactionConfiguration(**base)


# --- pure helpers ---


def test_is_marker_item() -> None:
    """Marker messages are recognized; ordinary messages and non-messages are not."""
    assert cc.is_marker_item(_marker("s")) is True
    assert cc.is_marker_item(_msg("user", "hello")) is False
    assert cc.is_marker_item({"type": "function_call"}) is False


def test_items_after_last_marker() -> None:
    """Only items following the last marker are treated as recent verbatim turns."""
    items = [
        _msg("user", "a"),
        _marker("first summary"),
        _msg("user", "b"),
        _marker("second summary"),
        _msg("assistant", "c"),
    ]
    recent = cc._items_after_last_marker(items)
    assert recent == [_msg("assistant", "c")]


def test_items_after_last_marker_no_marker() -> None:
    """With no marker, every item is recent."""
    items = [_msg("user", "a"), _msg("assistant", "b")]
    assert cc._items_after_last_marker(items) == items


def test_marker_summaries_in_order() -> None:
    """All marker summaries are returned oldest-first with the sentinel stripped."""
    items = [_marker("one"), _msg("user", "x"), _marker("two")]
    assert cc._marker_summaries(items) == ["one", "two"]


def test_build_explicit_input_shape() -> None:
    """Explicit input is summaries, then recent message turns, then the new query."""
    built = cc._build_explicit_input(
        summaries=["earlier stuff"],
        recent_items=[_msg("user", "recent q"), _msg("assistant", "recent a")],
        original_input="brand new question",
    )
    texts = [part["content"][0]["text"] for part in built]
    assert "Summary of earlier conversation:\nearlier stuff" in texts[0]
    assert texts[1] == "recent q"
    assert texts[2] == "recent a"
    assert texts[3] == "brand new question"
    # the assistant turn is rendered with output_text content
    assert built[2]["content"][0]["type"] == "output_text"


def test_should_compact() -> None:
    """Trigger requires exceeding both the ratio threshold and the token floor."""
    cfg = _compaction(threshold_ratio=0.7, token_floor=100)
    assert cc._should_compact(estimated_tokens=800, context_window=1000, config=cfg)
    # below the ratio threshold
    assert not cc._should_compact(600, 1000, cfg)
    # above ratio but below the floor
    assert not cc._should_compact(
        90, 100, _compaction(threshold_ratio=0.5, token_floor=100)
    )


# --- apply_compaction ---


@pytest.mark.asyncio
async def test_disabled_passes_through() -> None:
    """When compaction is disabled the params are returned unchanged."""
    result = await cc.apply_compaction_blocking(
        client=None,  # not used when disabled
        params=_params(),
        inference_config=_inference(1000),
        compaction_config=_compaction(enabled=False),
    )
    assert result.summarized is False
    assert result.params.omit_conversation is False
    assert result.params.input == "new question"


@pytest.mark.asyncio
async def test_no_context_window_no_marker_passes_through(mocker: MockerFixture) -> None:
    """No registered context window and no prior summary => normal flow."""
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=[])
    )
    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params(),
        inference_config=_inference(None),
        compaction_config=_compaction(),
    )
    assert result.summarized is False
    assert result.params.omit_conversation is False


@pytest.mark.asyncio
async def test_existing_marker_builds_explicit_input(mocker: MockerFixture) -> None:
    """A conversation that already has a marker is served in compacted mode.

    Even when below the trigger threshold (large window), the presence of a
    prior summary means lightspeed-stack must own the context: explicit input
    and the conversation parameter dropped.
    """
    items = [
        _msg("user", "old q"),
        _marker("the earlier conversation summary"),
        _msg("user", "recent q"),
        _msg("assistant", "recent a"),
    ]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summarize = mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock())

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("brand new"),
        inference_config=_inference(1_000_000),  # huge: no new trigger
        compaction_config=_compaction(),
    )

    summarize.assert_not_called()  # below threshold, no new summary
    assert result.summarized is True
    assert result.params.omit_conversation is True
    assert isinstance(result.params.input, list)
    texts = [p["content"][0]["text"] for p in result.params.input]
    assert texts[0].endswith("the earlier conversation summary")
    assert texts[-1] == "brand new"
    assert result.original_input == "brand new"


@pytest.mark.asyncio
async def test_triggers_summarization_and_writes_marker(mocker: MockerFixture) -> None:
    """Exceeding the threshold summarizes old turns and writes a marker item."""
    items = [_msg("user", "q1 " * 50), _msg("assistant", "a1 " * 50)]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summary = ConversationSummary(
        summary_text="condensed earlier turns",
        summarized_through_turn=2,
        token_count=4,
        created_at="2026-05-26T00:00:00Z",
        model_used=MODEL,
    )
    summarize = mocker.patch.object(
        cc, "summarize_chunk", mocker.AsyncMock(return_value=summary)
    )
    write_marker = mocker.patch.object(cc, "_write_summary_marker", mocker.AsyncMock())

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("follow-up"),
        inference_config=_inference(50),  # small window forces the trigger
        compaction_config=_compaction(threshold_ratio=0.1, buffer_turns=0),
    )

    summarize.assert_awaited_once()
    write_marker.assert_awaited_once()
    assert result.summarized is True
    assert result.params.omit_conversation is True
    texts = [p["content"][0]["text"] for p in result.params.input]
    assert "condensed earlier turns" in texts[0]
    assert texts[-1] == "follow-up"


@pytest.mark.asyncio
async def test_streaming_emits_event_before_summarizing(mocker: MockerFixture) -> None:
    """In streaming mode a CompactionStartedEvent precedes the summary result."""
    items = [_msg("user", "q1 " * 50), _msg("assistant", "a1 " * 50)]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summary = ConversationSummary(
        summary_text="condensed",
        summarized_through_turn=2,
        token_count=2,
        created_at="2026-05-26T00:00:00Z",
        model_used=MODEL,
    )
    mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock(return_value=summary))
    mocker.patch.object(cc, "_write_summary_marker", mocker.AsyncMock())

    yielded = []
    async for item in cc.apply_compaction(
        client=mocker.AsyncMock(),
        params=_params(),
        inference_config=_inference(50),
        compaction_config=_compaction(threshold_ratio=0.1, buffer_turns=0),
        emit_events=True,
    ):
        yielded.append(item)

    assert isinstance(yielded[0], cc.CompactionStartedEvent)
    assert yielded[0].conversation_id == CONV
    assert isinstance(yielded[-1], cc.CompactionResult)
    assert yielded[-1].summarized is True


@pytest.mark.asyncio
async def test_store_compacted_turn_appends(mocker: MockerFixture) -> None:
    """store_compacted_turn delegates to append_turn_items_to_conversation."""
    append = mocker.patch.object(
        cc, "append_turn_items_to_conversation", mocker.AsyncMock()
    )
    client = mocker.AsyncMock()
    await cc.store_compacted_turn(client, CONV, "the query", ["out"])
    append.assert_awaited_once_with(client, CONV, "the query", ["out"])
