"""Conversation compaction — partitioning, summarization, additive fold-up.

Pure-logic core of the conversation-compaction feature. The module
exposes three units of work:

* ``partition_conversation`` — split an ordered list of conversation
  items into the older chunk that will be summarized and the buffer of
  recent turns kept verbatim. Applies the *degrading guard*: it starts
  with ``buffer_turns`` turn pairs and shrinks the buffer one turn at a
  time until the buffer fits inside ``available_budget_tokens``. This
  is decision 9 of the spike.

* ``summarize_chunk`` — call the LLM once to summarize a chunk of items
  and return a :class:`ConversationSummary`. This is the *additive*
  primitive of decision 2: each chunk is summarized once and kept.

* ``recursively_resummarize`` — fall back to a single-summary collapse
  when the cumulative size of existing summaries itself approaches the
  context window. Lives in a later commit.

This module deliberately does **not** touch conversation state. It does
not create new Llama Stack conversations, inject marker items, write
to the cache, or acquire locks. Those side-effecting concerns belong
to LCORE-1572 (request-flow integration) and LCORE-1571 (cache
extension). Keeping this layer pure makes it unit-testable without
mocking the whole stack and lets LCORE-1572 wire it in without having
to disentangle a tangle of side effects.
"""

from datetime import datetime, timezone
from typing import Any

from llama_stack_client import AsyncLlamaStackClient

from log import get_logger
from models.compaction import ConversationSummary

logger = get_logger(__name__)


SUMMARIZATION_PROMPT = (
    "Summarize this conversation history for an AI assistant that helps with\n"
    "Red Hat product support. Preserve:\n"
    "1. The user's original question and environment details.\n"
    "2. All error messages, commands run, and their outcomes.\n"
    "3. Key decisions and their rationale.\n"
    "4. What was resolved and what remains open.\n"
    "5. Clear attribution (what the user reported vs what the assistant"
    " suggested).\n"
    "\n"
    "Be concise but complete. The assistant will use this summary as its only\n"
    "memory of older conversation turns.\n"
)
"""Domain-specific summarization prompt.

Includes the five preservation directives required by the spec doc and
the JIRA acceptance criteria. Exposed as a module constant so tests can
assert directive presence and so future tuning is visible in one place.
"""


def is_message_item(item: Any) -> bool:
    """Return True when *item* is a chat-message-shaped conversation item.

    Accepts the Llama Stack duck-typed shape (``.type == "message"``)
    and the OpenAI-style ``{"role", "content"}`` dict.

    Parameters:
        item: Conversation item to classify.

    Returns:
        True when the item is a message; False otherwise (function
        calls, tool results, structured outputs, etc.).
    """
    if isinstance(item, dict):
        return "role" in item
    return getattr(item, "type", None) == "message"


def extract_message_text(item: Any) -> str:
    """Return the plain text of a chat-message item.

    Accepts both the Llama Stack object shape (``.content`` may be a
    string, a list of content-part objects with ``.text``, or a list
    of dicts with ``"text"`` keys) and the OpenAI-style dict shape
    (``content`` is a string or list of dicts).

    Parameters:
        item: A chat-message item.

    Returns:
        The textual content joined by spaces, or the empty string when
        no text can be extracted.
    """
    content: Any
    if isinstance(item, dict):
        content = item.get("content")
    else:
        content = getattr(item, "content", None)

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = None
            if hasattr(part, "text"):
                text = getattr(part, "text", None)
            elif isinstance(part, dict) and "text" in part:
                text = part["text"]
            if text:
                parts.append(text)
        return " ".join(parts)
    return str(content)


def format_conversation_for_summary(items: list[Any]) -> str:
    """Render conversation items as ``role: text`` lines for a summarization prompt.

    Non-message items are skipped — the summarization prompt is meant
    for the human-language transcript, not the tool-call control flow.

    Parameters:
        items: Ordered list of conversation items.

    Returns:
        Multi-line string. One line per message in the form
        ``"<role>: <text>"``. Empty when no message items contain text.
    """
    lines: list[str] = []
    for item in items:
        if not is_message_item(item):
            continue
        if isinstance(item, dict):
            role = item.get("role", "unknown")
        else:
            role = getattr(item, "role", "unknown")
        text = extract_message_text(item)
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _message_indices(items: list[Any]) -> list[int]:
    """Return positions in *items* that correspond to message items."""
    return [i for i, item in enumerate(items) if is_message_item(item)]


def partition_conversation(
    items: list[Any],
    available_budget_tokens: int,
    buffer_turns: int,
    encoding_name: str,
) -> tuple[list[Any], list[Any]]:
    """Split *items* into ``(old, recent)`` honoring the degrading guard.

    "Old" is the chunk that will be summarized; "recent" is the buffer
    of trailing turns kept verbatim. The buffer is sized in *turn
    pairs* (one user message + one assistant message). The function
    starts from ``buffer_turns`` pairs and shrinks one pair at a time
    until the recent chunk fits inside ``available_budget_tokens``.

    The shrink continues all the way down to zero — at which point all
    items are placed in the old chunk and the recent chunk is empty.
    This handles the pathological case described in the spec (a few
    very large tool-result turns that would themselves overflow the
    context window even after summarizing everything else).

    Non-message items (function calls, tool results) are kept attached
    to whichever chunk their bracketing messages land in. The split
    boundary is always the position of a user message — the leading
    boundary of a turn pair.

    Parameters:
        items: Ordered list of conversation items, oldest first.
        available_budget_tokens: How many tokens the buffer chunk is
            allowed to consume. The compaction runtime computes this
            as ``context_window - summary_token_budget - new_query_tokens``.
        buffer_turns: Initial buffer size in turn pairs. The degrading
            guard reduces this until the buffer fits.
        encoding_name: Tiktoken encoding name passed through to the
            token estimator so the budget computation matches whatever
            encoding the production caller already chose for the
            request.

    Returns:
        ``(old_items, recent_items)``. ``old_items`` may be empty (no
        compaction needed); ``recent_items`` may be empty (everything
        had to be summarized).
    """
    # Import locally to avoid a top-level circular import once the
    # request-flow integration in LCORE-1572 imports both modules.
    from utils.token_estimator import estimate_conversation_tokens

    msg_indices = _message_indices(items)
    if not msg_indices:
        return [], items

    # Try each candidate buffer size from buffer_turns down to 0. The
    # boundary is always the start of a user/assistant pair: we keep
    # the last `n * 2` message items in the buffer.
    for candidate_turns in range(buffer_turns, -1, -1):
        recent_msg_count = candidate_turns * 2
        if recent_msg_count == 0:
            # Buffer fully degraded — everything goes to old.
            return items, []
        if recent_msg_count > len(msg_indices):
            # Not enough messages to satisfy this candidate buffer
            # size; smaller candidates will be tried next iteration.
            continue
        split_at = msg_indices[-recent_msg_count]
        recent_items = items[split_at:]
        recent_tokens = estimate_conversation_tokens(
            recent_items, encoding_name=encoding_name
        )
        if recent_tokens <= available_budget_tokens:
            return items[:split_at], recent_items

    # Defensive fallback — the loop above always returns. Mirror
    # the buffer-fully-degraded branch so the function has a single
    # well-defined behavior in every reachable state.
    return items, []


def _build_summarization_prompt_body(items: list[Any]) -> str:
    """Render the full prompt body sent to the summarization LLM call.

    Concatenates the system-style summarization prompt with a
    ``role: text``-formatted transcript of the items being summarized.

    Parameters:
        items: The chunk to summarize.

    Returns:
        Full prompt body string.
    """
    transcript = format_conversation_for_summary(items)
    return f"{SUMMARIZATION_PROMPT}\nConversation:\n{transcript}"


def _extract_response_text(response: Any) -> str:
    """Pull the human-readable text out of a Responses-API result.

    Walks ``response.output`` and concatenates the ``.text`` field of
    every content part that has one. Mirrors the shape-handling done
    by :func:`utils.responses.extract_text_from_response_items` but is
    kept local here so the compaction module does not depend on the
    response-handling utility module that LCORE-1572 will eventually
    integrate with.

    Parameters:
        response: The result of ``client.responses.create``.

    Returns:
        Concatenated response text, or the empty string when nothing
        could be extracted.
    """
    parts: list[str] = []
    output = getattr(response, "output", None) or []
    for output_item in output:
        content = getattr(output_item, "content", None)
        if not content:
            continue
        for content_part in content:
            text = getattr(content_part, "text", None)
            if text:
                parts.append(text)
    return "".join(parts)


async def summarize_chunk(
    client: AsyncLlamaStackClient,
    model: str,
    old_items: list[Any],
    summarized_through_turn: int,
    encoding_name: str,
) -> ConversationSummary:
    """Summarize *old_items* via one LLM call and return a ConversationSummary.

    This is the additive primitive of compaction decision 2. The
    function:

    1. Renders the summarization prompt against the transcript of
       *old_items*.
    2. Calls ``client.responses.create`` once with ``store=False`` (the
       summarization call is a one-shot — its output is not stored as
       a conversation item by Llama Stack; the caller in LCORE-1572 is
       responsible for injecting the summary into the conversation
       under whatever marker scheme it chooses).
    3. Wraps the resulting text in a :class:`ConversationSummary` with
       a freshly-computed token count and a UTC ISO 8601 timestamp.

    The function does **not** mutate the caller's conversation, does
    not write to the cache, does not acquire any lock. Concurrency
    control and persistence belong to LCORE-1572 / LCORE-1571.

    Parameters:
        client: Llama Stack client to call.
        model: Fully-qualified model identifier (e.g.,
            ``"openai/gpt-4o-mini"``). The spec mandates the same
            model as the user's query (spike decision 3); the choice
            is the caller's, this function only records it.
        old_items: Conversation items to summarize. Non-message items
            are filtered out by the transcript renderer.
        summarized_through_turn: Running total of items the caller has
            already summarized at the moment this chunk completes —
            this value is stored on the returned ConversationSummary
            so the caller can advance the partition boundary on the
            next compaction. Caller-tracked; not derived from
            ``old_items`` alone because additive compaction can span
            multiple invocations whose chunk boundaries do not start
            at zero.
        encoding_name: Tiktoken encoding name used to count tokens in
            the produced summary. Should match the encoding used to
            decide the compaction trigger.

    Returns:
        A populated ConversationSummary.

    Raises:
        ValueError: When the LLM call returns no extractable text and
            the resulting summary would be empty. A zero-token summary
            cannot be persisted (PositiveInt) and is also useless as
            context, so propagating an error is the honest behavior.
    """
    from utils.token_estimator import estimate_tokens

    prompt = _build_summarization_prompt_body(old_items)
    logger.info(
        "Summarizing %d conversation items (%d messages) for model %s.",
        len(old_items),
        sum(1 for item in old_items if is_message_item(item)),
        model,
    )
    response = await client.responses.create(
        input=prompt,
        model=model,
        stream=False,
        store=False,
    )
    summary_text = _extract_response_text(response).strip()
    if not summary_text:
        raise ValueError(
            "Summarization LLM call returned no extractable text; "
            "cannot construct ConversationSummary."
        )
    token_count = estimate_tokens(summary_text, encoding_name=encoding_name)
    return ConversationSummary(
        summary_text=summary_text,
        summarized_through_turn=summarized_through_turn,
        token_count=token_count,
        created_at=datetime.now(timezone.utc).isoformat(),
        model_used=model,
    )
