"""Conversation compaction utilities for managing context window limits.

This module implements a proof-of-concept for conversation history
summarization (compaction). When a conversation exceeds a configurable
message threshold, older messages are summarized by the LLM and replaced
with a concise summary, while recent messages are preserved verbatim.

The compacted history is stored in a new Llama Stack conversation. The
original conversation is preserved as an audit trail.
"""

from typing import Any

from llama_stack_client import AsyncLlamaStackClient

from log import get_logger

logger = get_logger(__name__)

# PoC constants — will move to YAML config in production.
COMPACTION_TRIGGER_THRESHOLD = 10
"""Minimum number of user messages before compaction is considered."""

RECENT_MESSAGES_TO_KEEP = 4
"""Number of recent user+assistant turn pairs to keep verbatim."""

SUMMARIZATION_PROMPT = (
    "Summarize the following conversation history between a user and "
    "an AI assistant. Preserve:\n"
    "- The user's original question or goal\n"
    "- Key decisions and conclusions reached\n"
    "- Important entities (product names, versions, error messages)\n"
    "- Troubleshooting steps already attempted and their outcomes\n\n"
    "Be concise but complete. Write in third person.\n\n"
    "Conversation:\n{conversation_text}"
)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


def _is_message_item(item: Any) -> bool:
    """Return True when *item* is a conversation message (user or assistant)."""
    return getattr(item, "type", None) == "message"


def _extract_message_text(item: Any) -> str:
    """Extract plain text from a conversation message item."""
    content = getattr(item, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if hasattr(part, "text"):
                parts.append(part.text)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return " ".join(parts)
    return str(content)


def _format_conversation_for_summary(items: list[Any]) -> str:
    """Format conversation items into text suitable for the summarization prompt."""
    lines: list[str] = []
    for item in items:
        if _is_message_item(item):
            role = getattr(item, "role", "unknown")
            text = _extract_message_text(item)
            if text:
                lines.append(f"{role}: {text}")
    return "\n".join(lines)


def split_conversation_items(
    items: list[Any],
    recent_to_keep: int = RECENT_MESSAGES_TO_KEEP,
) -> tuple[list[Any], list[Any]]:
    """Split items into *old* (to summarize) and *recent* (to keep verbatim).

    Parameters:
        items: All conversation items ordered oldest-first.
        recent_to_keep: Number of recent user+assistant *pairs* to keep.

    Returns:
        ``(old_items, recent_items)`` where ``old_items`` may be empty.
    """
    message_indices = [i for i, item in enumerate(items) if _is_message_item(item)]

    # Need at least recent_to_keep pairs (each pair = 2 messages)
    # plus at least one old message to justify compaction.
    min_messages_for_compaction = recent_to_keep * 2 + 1
    if len(message_indices) <= min_messages_for_compaction:
        return [], items

    split_index = message_indices[-(recent_to_keep * 2)]
    return items[:split_index], items[split_index:]


# ---------------------------------------------------------------------------
# I/O layer
# ---------------------------------------------------------------------------


async def _summarize_conversation(
    client: AsyncLlamaStackClient,
    model: str,
    items: list[Any],
) -> str:
    """Use the LLM to produce a concise summary of *items*.

    Parameters:
        client: Llama Stack client.
        model: Full model ID (``provider/model``).
        items: Conversation items to summarize.

    Returns:
        Summary text produced by the LLM.
    """
    conversation_text = _format_conversation_for_summary(items)
    prompt = SUMMARIZATION_PROMPT.format(conversation_text=conversation_text)

    summary_conv = await client.conversations.create(metadata={})
    response = await client.responses.create(
        input=prompt,
        model=model,
        conversation=summary_conv.id,
        store=False,
    )

    summary_parts: list[str] = []
    for output_item in response.output:
        content = getattr(output_item, "content", None)
        if content is None:
            continue
        for content_part in content:
            text = getattr(content_part, "text", None)
            if text:
                summary_parts.append(text)

    return "".join(summary_parts) or "No summary generated."


async def _create_compacted_conversation(
    client: AsyncLlamaStackClient,
    summary: str,
    recent_items: list[Any],
) -> str:
    """Create a new conversation seeded with *summary* and *recent_items*.

    The summary is injected as a user→assistant exchange so the model
    receives it as part of the conversation context.

    Parameters:
        client: Llama Stack client.
        summary: Summary text of older conversation history.
        recent_items: Recent items to carry forward verbatim.

    Returns:
        The new Llama Stack conversation ID.
    """
    new_conv = await client.conversations.create(metadata={})

    # Seed with summary context as a user→assistant pair.
    seed_items: list[dict[str, str]] = [
        {
            "type": "message",
            "role": "user",
            "content": f"Here is a summary of our conversation so far:\n\n{summary}",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": (
                "Understood. I have the context from our previous conversation "
                "and will use it to continue helping you."
            ),
        },
    ]

    # Append recent messages.
    for item in recent_items:
        if _is_message_item(item):
            seed_items.append(
                {
                    "type": "message",
                    "role": getattr(item, "role", "user"),
                    "content": _extract_message_text(item),
                }
            )

    await client.conversations.items.create(
        new_conv.id, items=seed_items  # type: ignore[arg-type]
    )
    return new_conv.id


async def compact_conversation_if_needed(
    client: AsyncLlamaStackClient,
    llama_stack_conv_id: str,
    model: str,
    message_count: int,
) -> str:
    """Compact conversation history when it exceeds the trigger threshold.

    Parameters:
        client: Llama Stack client.
        llama_stack_conv_id: Current conversation ID in Llama Stack format.
        model: Full model ID (``provider/model``) for summarization.
        message_count: Number of user messages (from lightspeed DB).

    Returns:
        The (possibly new) Llama Stack conversation ID.  Unchanged when
        compaction was not triggered.
    """
    if message_count <= COMPACTION_TRIGGER_THRESHOLD:
        return llama_stack_conv_id

    logger.info(
        "Conversation %s has %d messages (threshold %d). Starting compaction.",
        llama_stack_conv_id,
        message_count,
        COMPACTION_TRIGGER_THRESHOLD,
    )

    items_response = await client.conversations.items.list(
        conversation_id=llama_stack_conv_id,
        after=None,
        include=None,
        limit=None,
        order="asc",
    )
    items = items_response.data

    if not items:
        logger.warning(
            "No items found for conversation %s, skipping compaction.",
            llama_stack_conv_id,
        )
        return llama_stack_conv_id

    old_items, recent_items = split_conversation_items(items)

    if not old_items:
        logger.debug(
            "Not enough old items to compact for conversation %s.",
            llama_stack_conv_id,
        )
        return llama_stack_conv_id

    summary = await _summarize_conversation(client, model, old_items)
    logger.info(
        "Generated summary for conversation %s (%d chars).",
        llama_stack_conv_id,
        len(summary),
    )

    new_conv_id = await _create_compacted_conversation(client, summary, recent_items)

    logger.info(
        "Compacted conversation %s → %s (summarized %d items, kept %d recent).",
        llama_stack_conv_id,
        new_conv_id,
        len(old_items),
        len(recent_items),
    )
    return new_conv_id
