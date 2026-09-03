"""Unit tests for runtime conversation compaction (LCORE-1572)."""

# Tests exercise internal helpers directly.
# pylint: disable=protected-access

import asyncio
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration, InferenceConfiguration
from utils import conversation_compaction as cc

MODEL = "openai/gpt-4o-mini"
CONV = "conv_abc123"


def _msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed Llama Stack message item for tests."""
    return OpenAIResponseMessage(role=cast(Any, role), content=text)


def _marker(text: str) -> OpenAIResponseMessage:
    """Build a typed summary marker message item for tests."""
    return OpenAIResponseMessage(role="user", content=f"{cc.MARKER_SENTINEL} {text}")


def _params(input_text: str = "new question") -> ResponsesApiParams:
    return ResponsesApiParams(
        input=input_text,
        model=MODEL,
        conversation=CONV,
        instructions="system prompt",
        store=True,
        stream=False,
    )


def _inference(window: Optional[int]) -> InferenceConfiguration:
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
    texts = [m.content for m in built]
    assert "Summary of earlier conversation:\nearlier stuff" in texts[0]
    assert texts[1] == "recent q"
    assert texts[2] == "recent a"
    assert texts[3] == "brand new question"
    # items are typed OpenAIResponseMessage objects (so they serialize cleanly)
    assert built[2].role == "assistant"


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
    assert result.compacted is False
    assert result.params.omit_conversation is False
    assert result.params.input == "new question"


@pytest.mark.asyncio
async def test_no_context_window_no_marker_passes_through(
    mocker: MockerFixture,
) -> None:
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
    assert result.compacted is False
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
    assert result.compacted is True
    assert result.params.omit_conversation is True
    assert isinstance(result.params.input, list)
    texts = [m.content for m in result.params.input]
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
    assert result.compacted is True
    assert result.params.omit_conversation is True
    texts = [m.content for m in result.params.input]
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
    assert yielded[-1].compacted is True


@pytest.mark.asyncio
async def test_store_compacted_turn_appends(mocker: MockerFixture) -> None:
    """store_compacted_turn delegates to append_turn_items_to_conversation."""
    append = mocker.patch.object(
        cc, "append_turn_items_to_conversation", mocker.AsyncMock()
    )
    client = mocker.AsyncMock()
    await cc.store_compacted_turn(client, CONV, "the query", ["out"])
    append.assert_awaited_once_with(client, CONV, "the query", ["out"])


# --- needs_compaction_path (the tight gate protecting non-compacting requests) ---


@pytest.mark.asyncio
async def test_needs_compaction_path_disabled(mocker: MockerFixture) -> None:
    """The gate is False (unchanged path) whenever compaction is disabled."""
    assert (
        await cc.needs_compaction_path(
            mocker.AsyncMock(),
            _params(),
            _inference(1000),
            _compaction(enabled=False),
        )
        is False
    )


@pytest.mark.asyncio
async def test_needs_compaction_path_existing_marker(mocker: MockerFixture) -> None:
    """A conversation with a prior summary marker always needs the compaction path."""
    mocker.patch.object(
        cc,
        "get_all_conversation_items",
        mocker.AsyncMock(return_value=[_marker("earlier"), _msg("user", "recent")]),
    )
    assert (
        await cc.needs_compaction_path(
            mocker.AsyncMock(),
            _params(),
            _inference(1_000_000),  # huge window: no new trigger, but marker exists
            _compaction(),
        )
        is True
    )


@pytest.mark.asyncio
async def test_needs_compaction_path_over_threshold(mocker: MockerFixture) -> None:
    """A conversation over the token threshold needs the compaction path."""
    mocker.patch.object(
        cc,
        "get_all_conversation_items",
        mocker.AsyncMock(
            return_value=[_msg("user", "q " * 50), _msg("assistant", "a " * 50)]
        ),
    )
    assert (
        await cc.needs_compaction_path(
            mocker.AsyncMock(),
            _params(),
            _inference(50),  # small window: over threshold
            _compaction(threshold_ratio=0.1),
        )
        is True
    )


@pytest.mark.asyncio
async def test_needs_compaction_path_under_threshold(mocker: MockerFixture) -> None:
    """A short conversation with no marker stays on the unchanged path."""
    mocker.patch.object(
        cc,
        "get_all_conversation_items",
        mocker.AsyncMock(return_value=[_msg("user", "hi"), _msg("assistant", "hello")]),
    )
    assert (
        await cc.needs_compaction_path(
            mocker.AsyncMock(),
            _params(),
            _inference(1_000_000),  # huge window: nowhere near the threshold
            _compaction(),
        )
        is False
    )


# --- cache as source of truth + recursive fold (R3) ---


def _summary(text: str, *, turn: int, tokens: int, at: str) -> ConversationSummary:
    """Build a ConversationSummary for cache tests."""
    return ConversationSummary(
        summary_text=text,
        summarized_through_turn=turn,
        token_count=tokens,
        created_at=at,
        model_used=MODEL,
    )


@pytest.mark.asyncio
async def test_cache_summaries_preferred_over_markers(mocker: MockerFixture) -> None:
    """When the cache returns summaries, they are used instead of marker texts."""
    items = [_marker("STALE marker text"), _msg("user", "recent q")]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summarize = mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock())
    cached = _summary(
        "FRESH cached summary", turn=2, tokens=5, at="2026-05-26T00:00:00Z"
    )
    cache = mocker.Mock()
    cache.get_summaries.return_value = [cached]

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("brand new"),
        inference_config=_inference(1_000_000),  # huge: no new trigger
        compaction_config=_compaction(),
        cache=cache,
        user_id="u1",
        skip_user_id_check=False,
    )

    summarize.assert_not_called()
    cache.get_summaries.assert_called_once_with("u1", CONV, False)
    texts = [m.content for m in result.params.input]
    assert "FRESH cached summary" in texts[0]
    assert "STALE marker text" not in texts[0]


@pytest.mark.asyncio
async def test_store_summary_called_on_compaction(mocker: MockerFixture) -> None:
    """A new summary chunk is persisted to the cache when compaction triggers."""
    items = [_msg("user", "q1 " * 50), _msg("assistant", "a1 " * 50)]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summary = _summary("condensed", turn=2, tokens=4, at="2026-05-26T00:00:00Z")
    mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock(return_value=summary))
    mocker.patch.object(cc, "_write_summary_marker", mocker.AsyncMock())
    cache = mocker.Mock()
    cache.get_summaries.return_value = []

    await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("follow-up"),
        inference_config=_inference(50),  # small window forces the trigger
        compaction_config=_compaction(threshold_ratio=0.1, buffer_turns=0),
        cache=cache,
        user_id="u1",
        skip_user_id_check=False,
    )

    cache.store_summary.assert_called_once()
    assert cache.store_summary.call_args[0] == ("u1", CONV, summary, False)


@pytest.mark.asyncio
async def test_fold_when_cached_summaries_exceed_threshold(
    mocker: MockerFixture,
) -> None:
    """Cached summaries above the threshold are folded and the fold persisted."""
    items = [_marker("m1"), _marker("m2"), _msg("user", "recent")]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    summarize = mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock())
    s1 = _summary("sum one", turn=4, tokens=20, at="2026-05-26T00:00:00Z")
    s2 = _summary("sum two", turn=8, tokens=20, at="2026-05-26T00:10:00Z")
    folded = _summary("FOLDED one+two", turn=8, tokens=10, at="2026-05-26T00:20:00Z")
    cache = mocker.Mock()
    cache.get_summaries.return_value = [s1, s2]
    resum = mocker.patch.object(
        cc, "recursively_resummarize", mocker.AsyncMock(return_value=folded)
    )

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("next"),
        inference_config=_inference(50),  # threshold 25 < 40 summary tokens
        compaction_config=_compaction(threshold_ratio=0.5, buffer_turns=5),
        cache=cache,
        user_id="u1",
        skip_user_id_check=False,
    )

    summarize.assert_not_called()  # estimate stays small; only the fold fires
    resum.assert_awaited_once()
    cache.replace_summaries.assert_called_once()
    assert cache.replace_summaries.call_args[0][2] is folded
    texts = [m.content for m in result.params.input]
    assert "FOLDED one+two" in texts[0]
    assert not any("sum one" in t for t in texts)


@pytest.mark.asyncio
async def test_no_fold_without_cache(mocker: MockerFixture) -> None:
    """With no cache, additive marker summaries are never folded (marker mode)."""
    items = [_marker("m1 " * 30), _marker("m2 " * 30), _msg("user", "recent")]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock())
    resum = mocker.patch.object(cc, "recursively_resummarize", mocker.AsyncMock())

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("next"),
        inference_config=_inference(1_000_000),
        compaction_config=_compaction(),
        cache=None,
    )

    resum.assert_not_awaited()
    assert result.compacted is True  # still compacted via markers


@pytest.mark.asyncio
async def test_marker_fallback_when_cache_empty(mocker: MockerFixture) -> None:
    """An empty cache falls back to the authoritative marker texts."""
    items = [_marker("marker summary text"), _msg("user", "recent")]
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    mocker.patch.object(cc, "summarize_chunk", mocker.AsyncMock())
    cache = mocker.Mock()
    cache.get_summaries.return_value = []

    result = await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=_params("next"),
        inference_config=_inference(1_000_000),
        compaction_config=_compaction(),
        cache=cache,
        user_id="u1",
        skip_user_id_check=False,
    )

    texts = [m.content for m in result.params.input]
    assert "marker summary text" in texts[0]


def test_configured_conversation_cache_none(mocker: MockerFixture) -> None:
    """configured_conversation_cache returns None when no cache is configured."""
    mock_config = mocker.patch.object(cc, "configuration")
    mock_config.compaction.enabled = True
    mock_config.conversation_cache_configuration.type = None
    assert cc.configured_conversation_cache() is None


def test_configured_conversation_cache_returns_cache(mocker: MockerFixture) -> None:
    """configured_conversation_cache returns the configured cache instance."""
    mock_config = mocker.patch.object(cc, "configuration")
    mock_config.compaction.enabled = True
    mock_config.conversation_cache_configuration.type = "sqlite"
    sentinel = object()
    mock_config.conversation_cache = sentinel
    assert cc.configured_conversation_cache() is sentinel


def test_configured_conversation_cache_none_when_compaction_disabled(
    mocker: MockerFixture,
) -> None:
    """Returns None when compaction is disabled, without reading the cache.

    Regression guard (LCORE-1572): the cache must not be initialized on every
    request when compaction is off — that 500'd e2e requests on configs whose
    SQLite cache could not be opened. The stub's ``conversation_cache`` raises if
    read, so the test fails on any eager access, not only on the return value.
    """

    class _ConfigStub:  # pylint: disable=too-few-public-methods
        """Config whose conversation_cache raises if accessed."""

        compaction = SimpleNamespace(enabled=False)
        conversation_cache_configuration = SimpleNamespace(type="sqlite")

        @property
        def conversation_cache(self) -> object:
            """Fail the test if the disabled path reads the cache."""
            raise AssertionError(
                "conversation_cache must not be accessed when compaction is disabled"
            )

    mocker.patch.object(cc, "configuration", _ConfigStub())
    assert cc.configured_conversation_cache() is None


def test_estimate_response_input_tokens_counts_list_form() -> None:
    """List-form ResponseInput is counted toward the estimate, not treated as zero.

    Regression guard: counting only string input would undercount list-form
    input (e.g. /v1/responses) and let a request skip compaction (LCORE-1572).
    """
    big = "incident detail " * 50
    string_tokens = cc._estimate_response_input_tokens(big, cc.DEFAULT_ENCODING_NAME)
    list_tokens = cc._estimate_response_input_tokens(
        cast(Any, [_msg("user", big)]), cc.DEFAULT_ENCODING_NAME
    )
    assert string_tokens > 10
    assert list_tokens > 10


# --- per-conversation lock (R11): ref-counted cleanup ---


@pytest.mark.asyncio
async def test_conversation_lock_serializes_concurrent_callers() -> None:
    """Two callers on the same conversation_id serialize: second waits for first."""
    cc._conversation_locks.clear()
    order: list[str] = []
    a_started = asyncio.Event()
    a_can_finish = asyncio.Event()

    async def first() -> None:
        async with cc._conversation_lock("conv_serial"):
            order.append("a-enter")
            a_started.set()
            await a_can_finish.wait()
            order.append("a-exit")

    async def second() -> None:
        await a_started.wait()
        async with cc._conversation_lock("conv_serial"):
            order.append("b-enter")
            order.append("b-exit")

    t1 = asyncio.create_task(first())
    t2 = asyncio.create_task(second())
    await a_started.wait()
    # Yield the loop a few times so `second` reaches the lock acquire.
    for _ in range(5):
        await asyncio.sleep(0)
    assert order == ["a-enter"]  # second is blocked behind first
    a_can_finish.set()
    await asyncio.gather(t1, t2)
    assert order == ["a-enter", "a-exit", "b-enter", "b-exit"]


@pytest.mark.asyncio
async def test_conversation_lock_entry_deleted_after_last_release() -> None:
    """The registry entry is removed once the last waiter exits (no leak)."""
    cc._conversation_locks.clear()
    async with cc._conversation_lock("conv_to_remove"):
        assert "conv_to_remove" in cc._conversation_locks
        assert cc._conversation_locks["conv_to_remove"].waiters == 1
    assert "conv_to_remove" not in cc._conversation_locks


@pytest.mark.asyncio
async def test_conversation_lock_entry_kept_while_waiters_queued() -> None:
    """While a second caller is queued, the entry stays (not evicted by the first exit)."""
    cc._conversation_locks.clear()
    inside_first = asyncio.Event()
    first_can_finish = asyncio.Event()

    async def first() -> None:
        async with cc._conversation_lock("conv_queue"):
            inside_first.set()
            await first_can_finish.wait()

    async def second() -> None:
        await inside_first.wait()
        async with cc._conversation_lock("conv_queue"):
            pass

    t1 = asyncio.create_task(first())
    t2 = asyncio.create_task(second())
    await inside_first.wait()

    # Wait until `second` has registered as a waiter.
    async def _wait_for_second() -> None:
        while cc._conversation_locks.get("conv_queue") is None or (
            cc._conversation_locks["conv_queue"].waiters < 2
        ):
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_second(), timeout=2)
    assert cc._conversation_locks["conv_queue"].waiters >= 2
    first_can_finish.set()
    await asyncio.gather(t1, t2)
    assert "conv_queue" not in cc._conversation_locks


@pytest.mark.asyncio
async def test_conversation_lock_cleanup_on_cancellation() -> None:
    """A cancelled holder does not leak its registry entry."""
    cc._conversation_locks.clear()
    inside = asyncio.Event()

    async def holder() -> None:
        async with cc._conversation_lock("conv_cancel"):
            inside.set()
            await asyncio.sleep(10)  # held until cancelled

    t = asyncio.create_task(holder())
    await inside.wait()
    assert "conv_cancel" in cc._conversation_locks
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    assert "conv_cancel" not in cc._conversation_locks
