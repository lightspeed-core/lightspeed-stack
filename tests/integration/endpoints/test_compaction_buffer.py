"""Integration tests for the buffered turns across consecutive compactions.

Regression coverage for LCORE-4219: the turns a compaction keeps verbatim are
appended to the conversation *before* the summary marker, so a boundary taken
from the marker's position dropped them from every later request.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from typing import Any

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.compaction import ConversationSummary
from tests.integration.conftest import InMemoryConversationStore
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    DEFAULT_SUMMARY_TEXT,
    EXISTING_CONV_ID,
    TEST_MODEL,
    collect_items,
    create_existing_conversation,
    enable_compaction,
    msg,
)
from utils.conversation_compaction import MARKER_COVERS_PREFIX, is_marker_item


def _setup_mocks(
    mocker: MockerFixture, mock_query_agent: AsyncMockType
) -> AsyncMockType:
    """Patch summarize_chunk with a summary that names the turns it summarized."""
    mock_query_agent.model.last_output_items = [
        OpenAIResponseMessage(role="assistant", content=DEFAULT_MODEL_RESPONSE)
    ]

    async def fake_summarize(
        _client: Any, _model: Any, old_items: list[Any], **kwargs: Any
    ) -> ConversationSummary:
        return ConversationSummary(
            summary_text=f"{DEFAULT_SUMMARY_TEXT}: "
            + " | ".join(getattr(item, "content", "") for item in old_items),
            summarized_through_turn=kwargs["summarized_through_turn"],
            token_count=6,
            created_at="2026-09-23T00:00:00Z",
            model_used=TEST_MODEL,
        )

    return mocker.patch(
        "utils.conversation_compaction.summarize_chunk",
        new_callable=mocker.AsyncMock,
        side_effect=fake_summarize,
    )


WORDS = ["one", "two", "three", "four", "five", "six"]


def _turns(count: int = 2) -> list[OpenAIResponseMessage]:
    """Build a conversation of *count* turns, each big enough to matter."""
    items: list[OpenAIResponseMessage] = []
    for word in WORDS[:count]:
        items.append(msg("user", f"question {word} " * 20))
        items.append(msg("assistant", f"answer {word} " * 20))
    return items


def _two_turns() -> list[OpenAIResponseMessage]:
    """Build a two-turn conversation big enough to cross the threshold."""
    return _turns(2)


def _agent_input(mock_query_agent: AsyncMockType) -> list[str]:
    """Return the text of every item the agent was asked to run on."""
    params = mock_query_agent.build_agent_mock.call_args[0][1]
    return [getattr(item, "content", "") for item in params.input]


def _was_compacted(mock_query_agent: AsyncMockType) -> bool:
    """Whether the last request built its own input instead of passing the conversation."""
    params = mock_query_agent.build_agent_mock.call_args[0][1]
    return bool(params.omit_conversation) and isinstance(params.input, list)


async def _ask(test_request: Any, test_auth: AuthTuple, query: str) -> None:
    """Send one query to the existing conversation."""
    await query_endpoint_handler(
        request=test_request,
        query_request=QueryRequest(query=query, conversation_id=EXISTING_CONV_ID),
        auth=test_auth,
        mcp_headers={},
    )


class TestCompactionBufferAcrossRequests:
    """The buffer of one compaction is still context for the requests after it."""

    @pytest.mark.asyncio
    async def test_buffered_turn_is_still_context_on_the_next_request(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Any,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """A turn kept verbatim by one compaction is not lost by the next request.

        The first request summarizes turn one and keeps turn two verbatim
        (``buffer_turns=1``). The second request must still know turn two,
        either verbatim or through a summary; before LCORE-4219 it was in
        neither, because the marker was written after it.
        """
        _ = mock_ogx_client
        enable_compaction(test_config, buffer_turns=1, buffer_max_ratio=0.5)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=_two_turns()
        )
        _setup_mocks(mocker, mock_query_agent)

        await _ask(test_request, test_auth, "first follow-up")
        assert any("question two" in text for text in _agent_input(mock_query_agent))

        await _ask(test_request, test_auth, "second follow-up")
        second_input = _agent_input(mock_query_agent)
        assert any(
            "question two" in text for text in second_input
        ), f"the buffered turn reached neither a summary nor the input: {second_input}"

    @pytest.mark.asyncio
    async def test_nothing_is_lost_across_compactions_with_a_larger_buffer(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Any,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """With ``buffer_turns=2`` every turn stays reachable over repeated compactions.

        A marker then sits *between* turns that are still being kept, so the
        boundary cannot be derived by subtracting the kept turns from the total
        stored items: doing so points one turn too far and drops it.
        """
        _ = mock_ogx_client
        enable_compaction(test_config, buffer_turns=2, buffer_max_ratio=0.9)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)
        # Six turns: two fit the buffer, the rest are summarized on the first
        # request, so later requests have a marker among the kept turns.
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=_turns(6)
        )
        _setup_mocks(mocker, mock_query_agent)

        compacted_rounds = 0
        for round_number in range(1, 6):
            await _ask(test_request, test_auth, f"follow-up {round_number}")
            if not _was_compacted(mock_query_agent):
                # Nothing summarized yet: OGX still replays the conversation.
                continue
            compacted_rounds += 1
            seen = " ".join(_agent_input(mock_query_agent))
            for turn in (f"question {word}" for word in WORDS):
                assert turn in seen, (
                    f"{turn!r} reached neither a summary nor the input in round "
                    f"{round_number}"
                )
            for earlier in range(1, round_number):
                assert (
                    f"follow-up {earlier}" in seen
                ), f"follow-up {earlier} was lost in round {round_number}"
        assert compacted_rounds >= 2, "the test never reached a second compaction"

    @pytest.mark.asyncio
    async def test_marker_records_the_items_its_summary_covers(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Any,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The written marker carries the count that defines the boundary.

        Turn one (two items) is summarized while turn two stays in the buffer,
        so the marker covers exactly the first two items.
        """
        _ = mock_ogx_client
        enable_compaction(test_config, buffer_turns=1, buffer_max_ratio=0.5)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=_two_turns()
        )
        _setup_mocks(mocker, mock_query_agent)

        await _ask(test_request, test_auth, "first follow-up")

        stored = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        markers = [item for item in stored if is_marker_item(item)]
        assert len(markers) == 1
        assert f"{MARKER_COVERS_PREFIX}2]" in getattr(markers[0], "content", "")
