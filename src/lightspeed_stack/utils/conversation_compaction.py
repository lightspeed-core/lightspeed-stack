"""Runtime integration of conversation compaction into the request flow.

This module wires the pure compaction primitives (``utils.compaction``,
LCORE-1570) and the token estimator (``utils.token_estimator``, LCORE-1569)
into the actual request path (LCORE-1572). Unlike ``utils.compaction`` — which
is deliberately side-effect free — this module *does* touch conversation state:
it fetches conversation items from Llama Stack, calls the summarization LLM,
writes summary marker items, reads and writes summaries in the cache, and holds
a per-conversation lock.

Design (see ``docs/design/conversation-compaction/conversation-compaction.md``):

* **Option A — lightspeed owns the context after compaction.** Once a
  conversation has been compacted, lightspeed-stack stops handing the
  ``conversation`` parameter to Llama Stack (which would otherwise reload the
  full message history and defeat compaction). Instead it builds the model
  input explicitly from the summaries plus the recent verbatim turns. The
  conversation identity (``conversation_id``) is preserved, and the full
  history remains in Llama Stack's conversation *items* for UI/audit.

* **Marker items track the boundary.** Each compaction writes the summary into
  the conversation as a recognizable *marker* message (a message whose text
  starts with ``MARKER_SENTINEL``). The items after the last marker are the
  recent verbatim turns; the marker texts are the additive summaries. This is
  lightspeed's own bookkeeping — Llama Stack never interprets it (we no longer
  pass ``conversation`` to inference once a marker exists).

* **Streaming notification.** When driven by the streaming endpoint, this
  module yields a :class:`CompactionStartedEvent` *before* the summarization
  LLM call so the client can show a progress indicator (R12). The non-streaming
  wrapper :func:`apply_compaction_blocking` simply ignores those events.

The cache (LCORE-1571) is the preferred source of truth for summaries and the
home of the persisted recursive fold (R3): each summary chunk is written to it,
the active summary set is read back from it, and when the summaries themselves
grow past the threshold they are folded into one and persisted via
``replace_summaries`` so the fold is reused rather than recomputed. When no
persisting cache is configured (or a cache read fails) the module falls back to
the Llama Stack marker texts, which remain authoritative — marker-only mode
keeps additive summaries with no fold. The marker items always carry the
boundary between summarized history and the recent verbatim turns.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Optional, cast

from llama_stack_api.openai_responses import OpenAIResponseMessage
from llama_stack_client import AsyncLlamaStackClient
from llama_stack_client.types.conversations.item_create_params import Item

from lightspeed_stack.cache.cache import Cache
from lightspeed_stack.cache.cache_error import CacheError
from lightspeed_stack.configuration import configuration
from lightspeed_stack.log import get_logger
from lightspeed_stack.models.common.responses.responses_api_params import (
    ResponsesApiParams,
)
from lightspeed_stack.models.common.responses.types import ResponseInput
from lightspeed_stack.models.compaction import ConversationSummary
from lightspeed_stack.models.config import (
    CompactionConfiguration,
    InferenceConfiguration,
)
from lightspeed_stack.utils.compaction import (
    partition_conversation,
    recursively_resummarize,
    summarize_chunk,
)
from lightspeed_stack.utils.conversations import (
    append_turn_items_to_conversation,
    get_all_conversation_items,
)
from lightspeed_stack.utils.token_estimator import (
    DEFAULT_ENCODING_NAME,
    estimate_conversation_tokens,
    estimate_tokens,
    extract_message_text,
    get_context_window,
    is_message_item,
)

logger = get_logger(__name__)


MARKER_SENTINEL = "[lightspeed:compaction-summary]"
"""Prefix that identifies a compaction summary marker message.

Marker items are ordinary conversation messages whose text begins with this
sentinel. They are written by :func:`_write_summary_marker` and recognized by
:func:`is_marker_item`. The sentinel is stripped before the summary is shown to
the model (:func:`_summary_input_message`).
"""


# Per-conversation locks (R11). A request that triggers compaction holds the
# conversation's lock across the summarization LLM call so concurrent requests
# on the same conversation wait rather than racing (e.g. double-compacting or
# appending a turn mid-compaction). Entries are ref-counted: the registry mutex
# guards lookup/insertion/deletion of an entry, and an entry is removed once
# its last waiter exits — so the registry does not grow unbounded with the
# set of conversation_ids ever seen by the process.


@dataclass
class _LockEntry:
    """Per-conversation lock paired with a count of in-flight waiters."""

    lock: asyncio.Lock
    waiters: int = 0


_conversation_locks: dict[str, _LockEntry] = {}
_locks_registry_mutex: asyncio.Lock = asyncio.Lock()


@asynccontextmanager
async def _conversation_lock(conversation_id: str) -> AsyncIterator[None]:
    """Acquire the per-conversation lock and clean up the entry on last release.

    The registry mutex guards lookup/insertion/deletion of the entry; the entry's
    own lock serializes the critical section. ``waiters`` is incremented before
    the critical section and decremented in ``finally``, so while any caller is
    inside the ``async with`` body ``waiters`` is ``>= 1`` and the entry cannot
    be evicted out from under concurrent waiters; once the last waiter exits
    the entry is removed from the registry.
    """
    entry: Optional[_LockEntry] = None
    try:
        async with _locks_registry_mutex:
            entry = _conversation_locks.get(conversation_id)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock())
                _conversation_locks[conversation_id] = entry
            entry.waiters += 1
        async with entry.lock:
            yield
    finally:
        if entry is not None:
            async with _locks_registry_mutex:
                entry.waiters -= 1
                if entry.waiters == 0:
                    _conversation_locks.pop(conversation_id, None)


@dataclass
class CompactionStartedEvent:
    """Sentinel yielded before the summarization LLM call (streaming only).

    The streaming endpoint formats this into an SSE ``compaction`` event so the
    client can display a progress indicator. The module stays decoupled from SSE
    formatting by yielding this typed value instead of a formatted string.

    Attributes:
        conversation_id: The conversation being compacted (llama-stack format).
    """

    conversation_id: str


@dataclass
class CompactionResult:
    """Outcome of applying compaction to a request.

    Attributes:
        params: The (possibly rewritten) Responses API params to send. When
            ``compacted`` is True, ``params.input`` is an explicit item list
            (summaries + recent turns + new query) and the ``conversation``
            parameter is omitted from the request body.
        compacted: Whether the request is served in compacted (explicit-input)
            mode — i.e. the conversation has at least one summary (from a marker
            or the cache), so the ``conversation`` parameter is omitted. This is
            True whether the summary was created this request or reused from a
            prior one. Drives ``context_status``.
        original_input: The new user query exactly as it arrived (before the
            explicit-input rewrite). Populated only in compacted mode (where
            ``compacted`` is True); ``None`` otherwise. In compacted mode the
            caller must append this plus the LLM output to the conversation
            items itself, since the ``conversation`` parameter is no longer
            passed to Llama Stack.
    """

    params: ResponsesApiParams
    compacted: bool
    original_input: Optional[ResponseInput] = None


def is_marker_item(item: Any) -> bool:
    """Return True when *item* is a compaction summary marker message."""
    if not is_message_item(item):
        return False
    return extract_message_text(item).startswith(MARKER_SENTINEL)


def _summary_text_of(item: Any) -> str:
    """Extract the summary text from a marker item (sentinel stripped)."""
    return extract_message_text(item)[len(MARKER_SENTINEL) :].strip()


def _items_after_last_marker(items: list[Any]) -> list[Any]:
    """Return the conversation items that follow the last summary marker.

    These are the recent turns kept verbatim. When there is no marker the whole
    list is returned (no compaction has happened yet).
    """
    last = -1
    for index, item in enumerate(items):
        if is_marker_item(item):
            last = index
    return items[last + 1 :]


def _marker_summaries(items: list[Any]) -> list[str]:
    """Return the summary texts of every marker item, in order (oldest first)."""
    return [_summary_text_of(item) for item in items if is_marker_item(item)]


def _summary_input_message(summary_text: str) -> OpenAIResponseMessage:
    """Build an explicit input message carrying a summary for the model.

    Returns a typed ``OpenAIResponseMessage`` (a member of the ``ResponseInput``
    union) so it serializes cleanly when the request body is dumped.
    """
    return OpenAIResponseMessage(
        role="user", content=f"Summary of earlier conversation:\n{summary_text}"
    )


def _verbatim_input_message(item: Any) -> Optional[OpenAIResponseMessage]:
    """Render a recent conversation message item as an explicit input message.

    Only message items are rendered; non-message items (tool calls/results) are
    skipped — they remain in the conversation's items for audit, but the
    explicit LLM context for the recent buffer is built from message text. This
    keeps the input schema-valid without reconstructing tool-call sequences.
    """
    if not is_message_item(item):
        return None
    text = extract_message_text(item)
    if not text:
        return None
    role = getattr(item, "role", "user")
    if role not in ("system", "developer", "user", "assistant"):
        role = "user"
    # role validated above; cast satisfies the Literal-typed parameter.
    return OpenAIResponseMessage(role=cast(Any, role), content=text)


def _query_input_message(original_input: ResponseInput) -> list[Any]:
    """Render the new user query as explicit input items.

    A string query becomes a single typed user message. An item list (e.g. from
    the /v1/responses client) is already composed of typed ``ResponseItem``
    objects, so it is passed through unchanged.
    """
    if isinstance(original_input, str):
        return [OpenAIResponseMessage(role="user", content=original_input)]
    return list(original_input)


def _build_explicit_input(
    summaries: list[str],
    recent_items: list[Any],
    original_input: ResponseInput,
) -> list[Any]:
    """Assemble the explicit model input: summaries + recent turns + new query."""
    built: list[Any] = [_summary_input_message(text) for text in summaries]
    for item in recent_items:
        message = _verbatim_input_message(item)
        if message is not None:
            built.append(message)
    built.extend(_query_input_message(original_input))
    return built


async def _write_summary_marker(
    client: AsyncLlamaStackClient,
    conversation_id: str,
    summary_text: str,
) -> None:
    """Write the summary into the conversation as a recognizable marker message."""
    marker_item: dict[str, Any] = {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": f"{MARKER_SENTINEL} {summary_text}"}
        ],
    }
    await client.conversations.items.create(
        conversation_id,
        items=cast(list[Item], [marker_item]),
    )


def _read_cached_summaries(
    cache: Optional[Cache],
    user_id: str,
    conversation_id: str,
    skip_user_id_check: bool,
) -> list[ConversationSummary]:
    """Return persisted summary chunks for a conversation (best-effort).

    The cache is the preferred source of truth for summaries (and the only home
    for a persisted recursive fold). Returns an empty list when no cache is
    configured, the backend does not persist (in-memory/no-op), or a cache error
    occurs — callers then fall back to the Llama Stack marker texts, which remain
    authoritative.
    """
    if cache is None:
        return []
    try:
        return cache.get_summaries(user_id, conversation_id, skip_user_id_check)
    except CacheError as exc:  # markers remain a valid fallback
        logger.warning("compaction: cache get_summaries failed: %s", exc)
        return []


def _store_cached_summary(
    cache: Optional[Cache],
    user_id: str,
    conversation_id: str,
    summary: ConversationSummary,
    skip_user_id_check: bool,
) -> None:
    """Persist a new summary chunk to the cache (best-effort).

    The summary is also written as a Llama Stack marker by the caller, so a
    failed cache write does not lose it — it only forgoes cache-backed reads and
    folding for this conversation.
    """
    if cache is None:
        return
    try:
        cache.store_summary(user_id, conversation_id, summary, skip_user_id_check)
    except CacheError as exc:  # the marker write already preserved the summary
        logger.warning("compaction: cache store_summary failed: %s", exc)


def configured_conversation_cache() -> Optional[Cache]:
    """Return the conversation cache for compaction, or None when not applicable.

    Endpoints pass this to :func:`apply_compaction` / :func:`apply_compaction_blocking`.
    Returns None — without touching the cache — when compaction is disabled, since
    the cache is only used by compaction on this path and accessing it would
    needlessly initialize it (and could fail) on every request. Also returns None
    when no conversation cache is configured; compaction then runs in marker-only
    mode.
    """
    if not configuration.compaction.enabled:
        return None
    if configuration.conversation_cache_configuration.type is None:
        return None
    return configuration.conversation_cache


def _estimate_response_input_tokens(value: ResponseInput, encoding_name: str) -> int:
    """Estimate the token count of a request input (string or item list).

    The new query may arrive as a plain string or, on ``/v1/responses``, as a
    list of input items. Counting only the string form would undercount list
    inputs, which could let a request skip compaction and still hit HTTP 413.
    """
    if isinstance(value, str):
        return estimate_tokens(value, encoding_name)
    return estimate_conversation_tokens(list(value), encoding_name=encoding_name)


def _should_compact(
    estimated_tokens: int,
    context_window: int,
    config: CompactionConfiguration,
) -> bool:
    """Decide whether the estimated input warrants compaction.

    Triggers when the estimate exceeds ``threshold_ratio`` of the context
    window and also clears the absolute ``token_floor`` (which prevents
    over-eager compaction on very small windows).
    """
    threshold = context_window * config.threshold_ratio
    return estimated_tokens > threshold and estimated_tokens > config.token_floor


def _load_compaction_state(
    items: list[Any],
    cache: Optional[Cache],
    user_id: str,
    conversation_id: str,
    skip_user_id_check: bool,
) -> tuple[list[str], list[ConversationSummary], list[Any]]:
    """Read the current summary set and the recent-items buffer from the conversation.

    The cache is the preferred source of truth for summary text; the Llama Stack
    marker texts remain the authoritative fallback when no persisting cache is
    configured. The recent-verbatim boundary is always derived from marker
    position in the conversation items.

    Returns ``(summaries, cached_summaries, recent_items)``.
    """
    cached_summaries = _read_cached_summaries(
        cache, user_id, conversation_id, skip_user_id_check
    )
    summaries = (
        [s.summary_text for s in cached_summaries]
        if cached_summaries
        else _marker_summaries(items)
    )
    recent_items = _items_after_last_marker(items)
    return summaries, cached_summaries, recent_items


def _estimate_total_tokens(
    system_prompt: Optional[str],
    summaries: list[str],
    recent_items: list[Any],
    original_input: ResponseInput,
    encoding_name: str,
) -> int:
    """Estimate the total token count for the request as it would be sent."""
    estimated = estimate_tokens(system_prompt or "", encoding_name)
    estimated += sum(estimate_tokens(text, encoding_name) for text in summaries)
    estimated += estimate_conversation_tokens(recent_items, encoding_name=encoding_name)
    estimated += _estimate_response_input_tokens(original_input, encoding_name)
    return estimated


async def _persist_new_summary_chunk(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    conversation_id: str,
    summary: ConversationSummary,
    cache: Optional[Cache],
    user_id: str,
    skip_user_id_check: bool,
) -> None:
    """Persist a fresh summary chunk: write the Llama Stack marker + best-effort cache."""
    await _write_summary_marker(client, conversation_id, summary.summary_text)
    _store_cached_summary(cache, user_id, conversation_id, summary, skip_user_id_check)


async def _maybe_persist_fold(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    model: str,
    conversation_id: str,
    cache: Optional[Cache],
    user_id: str,
    skip_user_id_check: bool,
    cached_summaries: list[ConversationSummary],
    summaries: list[str],
    context_window: int,
    threshold_ratio: float,
    encoding_name: str,
) -> tuple[list[str], list[ConversationSummary]]:
    """Run the recursive fold (R3) if persisted summaries crossed the threshold.

    Requires a persisting cache (marker-only conversations keep additive chunks).
    Returns the (possibly updated) ``(summaries, cached_summaries)``; on a cache
    write failure the unfolded values are returned unchanged.
    """
    if cache is None or len(cached_summaries) < 2:
        return summaries, cached_summaries
    summaries_tokens = sum(s.token_count for s in cached_summaries)
    if summaries_tokens <= context_window * threshold_ratio:
        return summaries, cached_summaries
    logger.info(
        "Folding %d summaries (%d tokens) for conversation %s",
        len(cached_summaries),
        summaries_tokens,
        conversation_id,
    )
    folded = await recursively_resummarize(
        client, model, cached_summaries, encoding_name
    )
    try:
        cache.replace_summaries(user_id, conversation_id, folded, skip_user_id_check)
    except CacheError as exc:  # keep the unfolded summaries
        logger.warning("compaction: cache replace_summaries failed: %s", exc)
        return summaries, cached_summaries
    return [folded.summary_text], [folded]


def _compacted_result(
    params: ResponsesApiParams,
    summaries: list[str],
    recent_items: list[Any],
    original_input: ResponseInput,
) -> CompactionResult:
    """Build the CompactionResult for compacted mode (explicit input + omit_conversation)."""
    explicit_input = _build_explicit_input(summaries, recent_items, original_input)
    compacted_params = params.model_copy(
        update={"input": explicit_input, "omit_conversation": True}
    )
    return CompactionResult(
        compacted_params, compacted=True, original_input=original_input
    )


async def apply_compaction(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    client: AsyncLlamaStackClient,
    params: ResponsesApiParams,
    inference_config: InferenceConfiguration,
    compaction_config: CompactionConfiguration,
    emit_events: bool = False,
    encoding_name: str = DEFAULT_ENCODING_NAME,
    cache: Optional[Cache] = None,
    user_id: str = "",
    skip_user_id_check: bool = False,
) -> AsyncIterator[Any]:
    """Apply conversation compaction to a prepared request, yielding the result.

    This is an async generator. When ``emit_events`` is True it yields a
    :class:`CompactionStartedEvent` immediately before the summarization LLM
    call (so the streaming endpoint can surface progress). It always yields a
    single :class:`CompactionResult` as its final item.

    The whole evaluate-and-summarize section runs under the conversation's lock
    (R11). When compaction is disabled, the model has no registered context
    window, or the conversation is not yet near the limit, the result simply
    carries the unchanged params with ``compacted`` reflecting whether any
    prior summary marker already exists.

    Parameters:
        client: Llama Stack client.
        params: The base Responses API params from ``prepare_responses_params``.
        inference_config: Inference config (for the per-model context window).
        compaction_config: Compaction tuning (enabled, threshold, buffer, ...).
        emit_events: Whether to yield CompactionStartedEvent before summarizing.
        encoding_name: tiktoken encoding name for estimation/summarization.
        cache: Conversation cache, the preferred summary store and the home of
            the persisted recursive fold. ``None`` (or a non-persisting backend)
            falls back to marker-only summaries with no folding.
        user_id: User identifier for cache reads/writes.
        skip_user_id_check: Whether to bypass the cache's user_id validation.

    Yields:
        Zero or more CompactionStartedEvent, then exactly one CompactionResult.
    """
    if not compaction_config.enabled:
        # ``enabled: false`` is a full off-switch: the request passes through
        # unchanged (conversation parameter intact, full-history replay). Known
        # limitation: disabling compaction *after* a conversation was already
        # compacted reverts that conversation to full replay — which can re-hit
        # the 413 path and resend marker text through the model. Toggling the
        # flag mid-conversation on already-compacted conversations is therefore
        # unsupported; leave it enabled for the lifetime of such conversations.
        yield CompactionResult(params, compacted=False)
        return

    conversation_id = params.conversation
    model = params.model
    original_input = params.input

    async with _conversation_lock(conversation_id):
        items = await get_all_conversation_items(client, conversation_id)
        summaries, cached_summaries, recent_items = _load_compaction_state(
            items, cache, user_id, conversation_id, skip_user_id_check
        )

        context_window = get_context_window(model, inference_config)
        if context_window is not None:
            estimated = _estimate_total_tokens(
                params.instructions,
                summaries,
                recent_items,
                original_input,
                encoding_name,
            )
            if _should_compact(estimated, context_window, compaction_config):
                if emit_events:
                    yield CompactionStartedEvent(conversation_id=conversation_id)
                budget = int(context_window * compaction_config.buffer_max_ratio)
                old_items, keep_items = partition_conversation(
                    recent_items,
                    available_budget_tokens=budget,
                    buffer_turns=compaction_config.buffer_turns,
                    encoding_name=encoding_name,
                )
                if old_items:
                    already = len(items) - len(recent_items)
                    summary = await summarize_chunk(
                        client,
                        model,
                        old_items,
                        summarized_through_turn=already + len(old_items),
                        encoding_name=encoding_name,
                    )
                    await _persist_new_summary_chunk(
                        client,
                        conversation_id,
                        summary,
                        cache,
                        user_id,
                        skip_user_id_check,
                    )
                    summaries.append(summary.summary_text)
                    cached_summaries = [*cached_summaries, summary]
                    recent_items = keep_items
            summaries, cached_summaries = await _maybe_persist_fold(
                client,
                model,
                conversation_id,
                cache,
                user_id,
                skip_user_id_check,
                cached_summaries,
                summaries,
                context_window,
                compaction_config.threshold_ratio,
                encoding_name,
            )

        if not summaries:
            # No compaction has ever happened for this conversation: leave the
            # normal conversation-parameter flow untouched.
            yield CompactionResult(params, compacted=False)
            return

        # Compacted mode: lightspeed owns the context. Build explicit input and
        # stop passing the conversation parameter to inference.
        yield _compacted_result(params, summaries, recent_items, original_input)


async def apply_compaction_blocking(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    params: ResponsesApiParams,
    inference_config: InferenceConfiguration,
    compaction_config: CompactionConfiguration,
    encoding_name: str = DEFAULT_ENCODING_NAME,
    cache: Optional[Cache] = None,
    user_id: str = "",
    skip_user_id_check: bool = False,
) -> CompactionResult:
    """Non-streaming wrapper around :func:`apply_compaction`.

    Drains the generator with event emission disabled and returns the final
    :class:`CompactionResult`. See :func:`apply_compaction` for the ``cache`` /
    ``user_id`` / ``skip_user_id_check`` parameters.
    """
    result: Optional[CompactionResult] = None
    async for item in apply_compaction(
        client,
        params,
        inference_config,
        compaction_config,
        emit_events=False,
        encoding_name=encoding_name,
        cache=cache,
        user_id=user_id,
        skip_user_id_check=skip_user_id_check,
    ):
        if isinstance(item, CompactionResult):
            result = item
    if result is None:  # pragma: no cover - the generator always yields one result
        raise RuntimeError("apply_compaction did not yield a CompactionResult")
    return result


async def needs_compaction_path(
    client: AsyncLlamaStackClient,
    params: ResponsesApiParams,
    inference_config: InferenceConfiguration,
    compaction_config: CompactionConfiguration,
    encoding_name: str = DEFAULT_ENCODING_NAME,
) -> bool:
    """Return whether this request needs the compaction-aware path (cheap check).

    Returns True when the conversation already has a summary marker (so it must
    be served in compacted mode with explicit input) or when the estimated
    tokens would trigger a new compaction. Performs no LLM call and takes no
    lock — the authoritative evaluate-and-summarize work happens later under
    the lock in :func:`apply_compaction`. Streaming endpoints use this to keep
    non-compacting requests on their unchanged code path, so the in-stream
    flow (and its SSE-error semantics) only ever applies to conversations that
    are actually being compacted.

    Parameters:
        client: Llama Stack client.
        params: The base Responses API params.
        inference_config: Inference config (for the per-model context window).
        compaction_config: Compaction tuning.
        encoding_name: tiktoken encoding name for estimation.

    Returns:
        True if the compaction-aware streaming path should be used.
    """
    if not compaction_config.enabled:
        return False
    items = await get_all_conversation_items(client, params.conversation)
    if any(is_marker_item(item) for item in items):
        return True
    context_window = get_context_window(params.model, inference_config)
    if context_window is None:
        return False
    estimated = estimate_tokens(params.instructions or "", encoding_name)
    estimated += estimate_conversation_tokens(items, encoding_name=encoding_name)
    estimated += _estimate_response_input_tokens(params.input, encoding_name)
    return _should_compact(estimated, context_window, compaction_config)


async def store_compacted_turn(
    client: AsyncLlamaStackClient,
    conversation_id: str,
    original_input: ResponseInput,
    output_items: Sequence[Any],
) -> None:
    """Append a completed turn to the conversation when in compacted mode.

    In compacted mode the ``conversation`` parameter is not sent to inference,
    so Llama Stack does not auto-store the turn. lightspeed-stack appends the
    user query and the LLM output to the conversation items itself, keeping the
    full history (and the recent-turn buffer for the next request) intact.
    """
    await append_turn_items_to_conversation(
        client, conversation_id, original_input, output_items
    )
