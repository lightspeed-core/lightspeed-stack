"""Shared helpers for conversation compaction integration tests."""

# pylint: disable=import-outside-toplevel

import asyncio
from typing import Any, cast

from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from configuration import AppConfig
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration
from models.database.conversations import UserConversation
from tests.integration.conftest import InMemoryConversationStore
from utils.conversation_compaction import MARKER_SENTINEL

EXISTING_CONV_ID = "22222222-2222-2222-2222-222222222222"
CONV_ID_LLAMA = f"conv_{EXISTING_CONV_ID}"
TEST_MODEL = "test-provider/test-model"
DEFAULT_SUMMARY_TEXT = "condensed earlier turns"
DEFAULT_MODEL_RESPONSE = "This is a test response about Ansible."
FOLDED_SUMMARY_TEXT = "folded summary of all earlier conversation"


def msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed conversation message item."""
    return OpenAIResponseMessage(role=cast(Any, role), content=text)


def marker(text: str) -> OpenAIResponseMessage:
    """Build a compaction summary marker message."""
    return OpenAIResponseMessage(
        role="user",
        content=f"{MARKER_SENTINEL} {text}",
    )


def enable_compaction(
    config: AppConfig,
    context_window: int = 200,
    threshold_ratio: float = 0.1,
    buffer_turns: int = 0,
    buffer_max_ratio: float = 0.3,
) -> None:
    """Override compaction and inference config to trigger compaction easily.

    Args:
        config: The application configuration singleton.
        context_window: Context window size for the test model.
        threshold_ratio: Ratio of context window that triggers compaction.
        buffer_turns: Number of recent turns to keep uncompacted.
        buffer_max_ratio: Maximum ratio of context window for buffered turns.
    """
    # pylint: disable=protected-access
    assert config._configuration is not None
    config._configuration.compaction = CompactionConfiguration(
        enabled=True,
        threshold_ratio=threshold_ratio,
        token_floor=0,
        buffer_turns=buffer_turns,
        buffer_max_ratio=buffer_max_ratio,
    )
    config._configuration.inference.context_windows = {TEST_MODEL: context_window}


async def collect_items(
    store: InMemoryConversationStore, conv_id: str
) -> list[OpenAIResponseMessage]:
    """Retrieve all conversation items from the in-memory store."""
    paginator = store.list(conv_id)
    page = await paginator
    items = list(page.data)
    while page.has_next_page():
        page = await page.get_next_page()
        items.extend(page.data)
    return items


def verify_store_content(
    actual: list[OpenAIResponseMessage], expected: list[OpenAIResponseMessage]
) -> bool:
    """Compare two message lists by content, role, and type fields."""
    if len(actual) != len(expected):
        return False

    return all(
        getattr(a, field, None) == getattr(b, field, None)
        for a, b in zip(actual, expected)
        for field in ("content", "role", "type")
    )


def assert_marker_count(
    store: InMemoryConversationStore,
    conv_id: str,
    expected: int,
) -> None:
    """Assert the number of compaction summary markers in the store.

    Args:
        store: The in-memory conversation store to inspect.
        conv_id: Conversation ID to look up.
        expected: Expected number of markers.
    """
    markers = [
        item
        for item in store.store.get(conv_id, [])
        if MARKER_SENTINEL in getattr(item, "content", "")
    ]
    assert (
        len(markers) == expected
    ), f"Expected {expected} marker(s) in store, found {len(markers)}"


def patch_get_all_conversation_items(mocker: MockerFixture):
    """Patch ``get_all_conversation_items`` with a slow fake for concurrency tests.

    The first call blocks until ``release`` is set; the second call signals
    ``task2_entered`` and returns immediately.

    Args:
        mocker: pytest-mock fixture.

    Returns:
        Tuple of (entered, release, task2_entered) asyncio Events.
    """
    entered = asyncio.Event()
    release = asyncio.Event()
    task2_entered = asyncio.Event()

    async def slow_get_items(client, conv_id):
        """First call holds the lock; second call signals and returns."""
        _ = client
        _ = conv_id

        if not entered.is_set():
            entered.set()
            await release.wait()
        else:
            task2_entered.set()
        return []

    mocker.patch(
        "utils.conversation_compaction.get_all_conversation_items",
        side_effect=slow_get_items,
    )

    return entered, release, task2_entered


async def await_lock_contention(conv_id: str, expected_waiters: int = 2) -> None:
    """Wait until the per-conversation lock has the expected number of waiters."""
    from utils.conversation_compaction import (
        _conversation_locks,
    )  # pylint: disable=import-outside-toplevel

    while True:
        entry = _conversation_locks.get(conv_id)
        if entry is not None and entry.waiters >= expected_waiters:
            return
        await asyncio.sleep(0)  # yield to event loop


def setup_fold_mocks(
    mocker: MockerFixture,
    cache_patch_target: str,
    items: list[Any],
) -> tuple[Any, AsyncMockType, AsyncMockType]:
    """Set up mocks for recursive fold tests.

    Creates a mock cache pre-loaded with two existing summaries whose combined
    token count, when a third summary is added by compaction, exceeds the
    compaction threshold -- triggering ``_maybe_persist_fold``.

    Each existing summary has ``token_count=1`` (total 2). The new summary
    from ``summarize_chunk`` adds ``token_count=1000`` (total 1002), which
    exceeds ``context_window(200) * threshold_ratio(0.1) = 20``.

    Args:
        mocker: pytest-mock fixture.
        cache_patch_target: Import path of ``configured_conversation_cache``.
        items: Conversation items used to set ``summarized_through_turn``.

    Returns:
        Tuple of (mock_cache, mock_summarize, mock_resummarize).
    """
    existing_summaries = [
        ConversationSummary(
            summary_text="summary of turns 1-2",
            summarized_through_turn=2,
            token_count=1,
            created_at="2026-08-09T00:00:00Z",
            model_used=TEST_MODEL,
        ),
        ConversationSummary(
            summary_text="summary of turns 3-4",
            summarized_through_turn=4,
            token_count=1,
            created_at="2026-08-09T12:00:00Z",
            model_used=TEST_MODEL,
        ),
    ]

    mock_cache = mocker.MagicMock()
    mock_cache.get_summaries.return_value = existing_summaries

    mocker.patch(cache_patch_target, return_value=mock_cache)

    mock_summarize = mocker.patch(
        "utils.conversation_compaction.summarize_chunk",
        new_callable=mocker.AsyncMock,
        return_value=ConversationSummary(
            summary_text="summary of turns 5-6",
            summarized_through_turn=len(items),
            token_count=1000,  # to trigger the persist fold
            created_at="2026-08-10T00:00:00Z",
            model_used=TEST_MODEL,
        ),
    )

    mock_resummarize = mocker.patch(
        "utils.conversation_compaction.recursively_resummarize",
        new_callable=mocker.AsyncMock,
        return_value=ConversationSummary(
            summary_text=FOLDED_SUMMARY_TEXT,
            summarized_through_turn=len(items),
            token_count=1,
            created_at="2026-08-10T00:00:00Z",
            model_used=TEST_MODEL,
        ),
    )

    return mock_cache, mock_summarize, mock_resummarize


def create_existing_conversation(
    db_session: Session,
    user_id: str,
) -> None:
    """Insert an existing conversation row into the test DB.

    Args:
        db_session: SQLAlchemy session bound to the test database.
        user_id: Owner user ID for the conversation row.
    """
    conv = UserConversation(
        id=EXISTING_CONV_ID,
        user_id=user_id,
        last_used_model="test-model",
        last_used_provider="test-provider",
        topic_summary="Support question",
        message_count=4,
    )
    db_session.add(conv)
    db_session.commit()
