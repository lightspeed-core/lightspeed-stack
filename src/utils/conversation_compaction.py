"""Runtime integration of conversation compaction into the request flow.

This module wires the pure compaction primitives (``utils.compaction``,
LCORE-1570) and the token estimator (``utils.token_estimator``, LCORE-1569)
into the actual request path (LCORE-1572). Unlike ``utils.compaction`` — which
is deliberately side-effect free — this module *does* touch conversation state:
it fetches conversation items from Llama Stack, calls the summarization LLM,
writes summary marker items, persists summaries to the cache (best-effort), and
holds a per-conversation lock.

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

The cache (LCORE-1571) is a *best-effort* secondary store here: summaries are
written to it for fast/queryable persistence, but the runtime boundary and
summary text are read back from the Llama Stack marker items, so this module
does not depend on the cache being functional.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Optional, cast

from llama_stack_api.openai_responses import OpenAIResponseMessage
from llama_stack_client import AsyncLlamaStackClient
from llama_stack_client.types.conversations.item_create_params import Item

from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.config import CompactionConfiguration, InferenceConfiguration
from utils.compaction import partition_conversation, summarize_chunk
from utils.conversations import (
    append_turn_items_to_conversation,
    get_all_conversation_items,
)
from utils.token_estimator import (
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
# appending a turn mid-compaction).
_conversation_locks: dict[str, asyncio.Lock] = {}


def _get_lock(conversation_id: str) -> asyncio.Lock:
    """Return the (process-wide) asyncio lock for a conversation, creating it lazily."""
    lock = _conversation_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _conversation_locks[conversation_id] = lock
    return lock


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
            ``summarized`` is True, ``params.input`` is an explicit item list
            (summaries + recent turns + new query) and the ``conversation``
            parameter is omitted from the request body.
        summarized: Whether the conversation is in compacted mode (it has at
            least one summary marker). Drives ``context_status``.
        original_input: The new user query exactly as it arrived (before the
            explicit-input rewrite). Populated only in compacted mode (where
            ``summarized`` is True); ``None`` otherwise. In compacted mode the
            caller must append this plus the LLM output to the conversation
            items itself, since the ``conversation`` parameter is no longer
            passed to Llama Stack.
    """

    params: ResponsesApiParams
    summarized: bool
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
    role = item.get("role") if isinstance(item, dict) else getattr(item, "role", "user")
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


async def apply_compaction(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    client: AsyncLlamaStackClient,
    params: ResponsesApiParams,
    inference_config: InferenceConfiguration,
    compaction_config: CompactionConfiguration,
    emit_events: bool = False,
    encoding_name: str = DEFAULT_ENCODING_NAME,
) -> AsyncIterator[Any]:
    """Apply conversation compaction to a prepared request, yielding the result.

    This is an async generator. When ``emit_events`` is True it yields a
    :class:`CompactionStartedEvent` immediately before the summarization LLM
    call (so the streaming endpoint can surface progress). It always yields a
    single :class:`CompactionResult` as its final item.

    The whole evaluate-and-summarize section runs under the conversation's lock
    (R11). When compaction is disabled, the model has no registered context
    window, or the conversation is not yet near the limit, the result simply
    carries the unchanged params with ``summarized`` reflecting whether any
    prior summary marker already exists.

    Parameters:
        client: Llama Stack client.
        params: The base Responses API params from ``prepare_responses_params``.
        inference_config: Inference config (for the per-model context window).
        compaction_config: Compaction tuning (enabled, threshold, buffer, ...).
        emit_events: Whether to yield CompactionStartedEvent before summarizing.
        encoding_name: tiktoken encoding name for estimation/summarization.

    Yields:
        Zero or more CompactionStartedEvent, then exactly one CompactionResult.
    """
    if not compaction_config.enabled:
        yield CompactionResult(params, summarized=False)
        return

    conversation_id = params.conversation
    model = params.model
    system_prompt = params.instructions
    original_input = params.input

    async with _get_lock(conversation_id):
        items = await get_all_conversation_items(client, conversation_id)
        summaries = _marker_summaries(items)
        recent_items = _items_after_last_marker(items)

        context_window = get_context_window(model, inference_config)
        if context_window is not None:
            estimated = estimate_tokens(system_prompt or "", encoding_name)
            estimated += sum(estimate_tokens(text, encoding_name) for text in summaries)
            estimated += estimate_conversation_tokens(
                recent_items, encoding_name=encoding_name
            )
            if isinstance(original_input, str):
                estimated += estimate_tokens(original_input, encoding_name)

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
                    await _write_summary_marker(
                        client, conversation_id, summary.summary_text
                    )
                    summaries.append(summary.summary_text)
                    recent_items = keep_items

        if not summaries:
            # No compaction has ever happened for this conversation: leave the
            # normal conversation-parameter flow untouched.
            yield CompactionResult(params, summarized=False)
            return

        # Compacted mode: lightspeed owns the context. Build explicit input and
        # stop passing the conversation parameter to inference.
        explicit_input = _build_explicit_input(summaries, recent_items, original_input)
        compacted_params = params.model_copy(
            update={"input": explicit_input, "omit_conversation": True}
        )
        yield CompactionResult(
            compacted_params, summarized=True, original_input=original_input
        )


async def apply_compaction_blocking(
    client: AsyncLlamaStackClient,
    params: ResponsesApiParams,
    inference_config: InferenceConfiguration,
    compaction_config: CompactionConfiguration,
    encoding_name: str = DEFAULT_ENCODING_NAME,
) -> CompactionResult:
    """Non-streaming wrapper around :func:`apply_compaction`.

    Drains the generator with event emission disabled and returns the final
    :class:`CompactionResult`.
    """
    result: Optional[CompactionResult] = None
    async for item in apply_compaction(
        client,
        params,
        inference_config,
        compaction_config,
        emit_events=False,
        encoding_name=encoding_name,
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
    if isinstance(params.input, str):
        estimated += estimate_tokens(params.input, encoding_name)
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
