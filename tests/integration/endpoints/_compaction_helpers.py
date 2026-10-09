"""Shared helpers for conversation compaction integration tests."""

# pylint: disable=import-outside-toplevel

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
)
from fastapi import Request
from ogx_api.openai_responses import OpenAIResponseMessage
from pydantic_ai import AgentRunResultEvent
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from configuration import AppConfig
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration
from models.database.conversations import UserConversation
from tests.integration.conftest import InMemoryConversationStore
from utils.conversation_compaction import MARKER_COVERS_PREFIX, MARKER_SENTINEL

EXISTING_CONV_ID = "22222222-2222-2222-2222-222222222222"
CONV_ID_LLAMA = f"conv_{EXISTING_CONV_ID}"
TEST_MODEL = "test-provider/test-model"
DEFAULT_SUMMARY_TEXT = "condensed earlier turns"
DEFAULT_MODEL_RESPONSE = "This is a test response about Ansible."
FOLDED_SUMMARY_TEXT = "folded summary of all earlier conversation"


def msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed conversation message item."""
    return OpenAIResponseMessage(role=cast(Any, role), content=text)


def marker(text: str, covers: int | None = None) -> OpenAIResponseMessage:
    """Build a compaction summary marker message.

    ``covers`` is the number of leading conversation items the summary covers,
    which the runtime records in every marker it writes (LCORE-4219). Omit it
    to build a pre-LCORE-4219 marker, the shape existing conversations still
    hold; :func:`verify_store_content` ignores the difference.
    """
    covers_part = "" if covers is None else f"{MARKER_COVERS_PREFIX}{covers}] "
    return OpenAIResponseMessage(
        role="user",
        content=f"{MARKER_SENTINEL} {covers_part}{text}",
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


def _without_covers(value: Any) -> Any:
    """Drop a marker's ``[covers:N]`` bookkeeping from message content.

    Markers record how many items their summary covers (LCORE-4219). The
    number depends on where a conversation stands, so comparisons here are on
    the summary text; tests that care about the number assert it directly.
    """
    if not isinstance(value, str) or not value.startswith(MARKER_SENTINEL):
        return value
    body = value[len(MARKER_SENTINEL) :].strip()
    if not body.startswith(MARKER_COVERS_PREFIX):
        return value
    return f"{MARKER_SENTINEL} {body[body.index(']') + 1 :].strip()}"


def verify_store_content(
    actual: list[OpenAIResponseMessage], expected: list[OpenAIResponseMessage]
) -> bool:
    """Compare two message lists by content, role, and type fields."""
    if len(actual) != len(expected):
        return False

    return all(
        _without_covers(getattr(a, field, None))
        == _without_covers(getattr(b, field, None))
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


FAKE_AGENT_CARD = AgentCard(
    name="Test Agent",
    description="Test",
    version="0.0.1",
    url="http://localhost:8080/a2a",
    provider=AgentProvider(organization="test", url="http://test"),
    skills=[],
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    protocol_version="0.3.0",
)


def build_a2a_request(user_input: str) -> Request:
    """Build a FastAPI Request with a JSON-RPC ``message/send`` body.

    Args:
        user_input: The user message text to include in the A2A request.

    Returns:
        A FastAPI Request object with the JSON-RPC body ready for consumption.
    """
    body_dict = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": user_input}],
                "messageId": f"msg-{uuid.uuid4()}",
                "contextId": f"ctx-{uuid.uuid4()}",
            }
        },
    }
    body_bytes = json.dumps(body_dict).encode()

    async def receive() -> dict[str, Any]:
        """Return the pre-built body as an ASGI receive event."""
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/a2a",
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
            ],
        },
        receive=receive,
    )


def mock_a2a_agent(mocker: MockerFixture) -> Any:
    """Build a mock pydantic-ai agent that yields a single result event.

    Args:
        mocker: pytest-mock fixture.

    Returns:
        A mock agent whose ``run_stream_events`` returns a single result event.
    """
    mock_run_result = mocker.MagicMock()
    mock_run_result.response.text = "Test A2A response"
    result_event = mocker.MagicMock(spec=AgentRunResultEvent)
    result_event.result = mock_run_result

    async def _event_stream() -> AsyncIterator[Any]:
        """Yield a single agent run result event."""
        yield result_event

    mock_stream_ctx = mocker.AsyncMock()
    mock_stream_ctx.__aenter__ = mocker.AsyncMock(return_value=_event_stream())
    mock_stream_ctx.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_agent = mocker.MagicMock()
    mock_agent.run_stream_events.return_value = mock_stream_ctx
    mock_agent.model.last_output_items = [
        OpenAIResponseMessage(role="assistant", content=DEFAULT_MODEL_RESPONSE)
    ]
    return mock_agent
