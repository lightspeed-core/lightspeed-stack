"""Load saved agent messages from the step store."""

from __future__ import annotations

from typing import Optional

from pydantic_ai.messages import ModelMessage
from pydantic_ai_harness.step_persistence import (
    ContinuableSnapshot,
    StepStore,
    continue_run,
)

from conversations.agent_history.ids import strip_conversation_prefix
from log import get_logger

logger = get_logger(__name__)

INCLUDE_INTERRUPTED = True


async def _latest_continuable_snapshot_for_conversation(
    store: StepStore,
    conversation_id: str,
) -> Optional[ContinuableSnapshot]:
    """Return the newest continuable snapshot for a conversation, if any.

    Registered runs without a snapshot are skipped (newest to oldest).

    Args:
        store: Agent step store.
        conversation_id: Conversation to look up (prefix is stripped).

    Returns:
        The newest continuable snapshot, or None when none exists.

    """
    normalized = strip_conversation_prefix(conversation_id)
    runs = await store.list_runs(conversation_id=normalized)
    for run in reversed(runs):
        snapshot = await store.latest_snapshot(
            run_id=run.run_id,
            include_interrupted=INCLUDE_INTERRUPTED,
        )
        if snapshot is not None:
            return snapshot
    return None


async def load_run_history(
    store: Optional[StepStore],
    run_id: str,
) -> list[ModelMessage]:
    """Load messages from a prior response.

    Args:
        store: Step store, or None when persistence is off.
        run_id: Response to load from.

    Returns:
        Prior messages, or an empty list when nothing is stored.

    """
    if store is None:
        return []
    try:
        return await continue_run(
            store, run_id=run_id, include_interrupted=INCLUDE_INTERRUPTED
        )
    except LookupError:
        logger.debug("No continuable snapshot for run_id=%s", run_id)
        return []


async def load_conversation_history(
    store: Optional[StepStore],
    conversation_id: str,
) -> list[ModelMessage]:
    """Load messages from the newest continuable response in a conversation.

    Args:
        store: Step store, or None when persistence is off.
        conversation_id: Conversation to continue.

    Returns:
        Prior messages, or an empty list when nothing is stored.

    """
    if store is None:
        return []
    snapshot = await _latest_continuable_snapshot_for_conversation(
        store, conversation_id
    )
    if snapshot is None:
        return []
    return list(snapshot.messages)
