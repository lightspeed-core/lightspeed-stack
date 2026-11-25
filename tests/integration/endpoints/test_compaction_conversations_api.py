"""Integration tests for compaction and the v2 conversations API."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from collections.abc import Generator

import pytest
from fastapi import Request
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.conversations_v2 import (
    get_conversation_endpoint_handler as get_conversation_v2,
)
from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from cache.sqlite_cache import SQLiteCache
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.successful import ConversationResponse
from models.compaction import ConversationSummary
from models.config import SQLiteDatabaseConfiguration
from tests.integration.conftest import InMemoryConversationStore
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    DEFAULT_SUMMARY_TEXT,
    EXISTING_CONV_ID,
    TEST_MODEL,
    assert_marker_count,
    create_existing_conversation,
    enable_compaction,
    msg,
)

NEW_QUERY = "What else can you help with?"


@pytest.fixture(name="conversation_cache")
def conversation_cache_fixture(
    test_config: AppConfig,
    mocker: MockerFixture,
) -> Generator[SQLiteCache, None, None]:
    """Configure an in-memory SQLite conversation cache."""
    test_config.conversation_cache_configuration.type = "sqlite"
    cache = SQLiteCache(SQLiteDatabaseConfiguration(db_path=":memory:"))
    cache.connect()
    cache.initialize_cache()
    mocker.patch.object(
        type(test_config),
        "conversation_cache",
        new_callable=mocker.PropertyMock,
        return_value=cache,
    )
    yield cache


def _returned_messages(response: ConversationResponse) -> list[tuple[str, str]]:
    """Flatten a conversation response into ``(type, content)`` pairs."""
    return [
        (message.type, message.content)
        for turn in response.chat_history
        for message in turn.messages
    ]


def _stored_turns() -> list[OpenAIResponseMessage]:
    """Two turns long enough to cross the compaction threshold of the tests."""
    return [
        msg("user", "question one " * 20),
        msg("assistant", "answer one " * 20),
        msg("user", "question two " * 20),
        msg("assistant", "answer two " * 20),
    ]


def _fake_summarization(
    mocker: MockerFixture, mock_query_agent: AsyncMockType, covered_items: int
) -> None:
    """Replace the summarization LLM call and set the answer of the main turn."""
    mock_query_agent.model.last_output_items = [
        OpenAIResponseMessage(role="assistant", content=DEFAULT_MODEL_RESPONSE)
    ]
    mocker.patch(
        "utils.conversation_compaction.summarize_chunk",
        new_callable=mocker.AsyncMock,
        return_value=ConversationSummary(
            summary_text=DEFAULT_SUMMARY_TEXT,
            summarized_through_turn=covered_items,
            token_count=6,
            created_at="2026-08-10T00:00:00Z",
            model_used=TEST_MODEL,
        ),
    )


class TestConversationsApiCompaction:  # pylint: disable=too-few-public-methods
    """Compaction summaries stay in cache storage, not in the v2 chat history."""

    @pytest.mark.asyncio
    async def test_v2_history_holds_no_marker_after_a_compaction(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        conversation_cache: SQLiteCache,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The v2 endpoint reads the conversation cache, which never holds a marker.

        With a cache configured, a compaction keeps its summary there as well.
        The summary goes to the cache's own summary storage and the turn is
        cached with the query as the user sent it, so the v2 history holds the
        turn and nothing else.
        """
        _ = mock_ogx_client

        enable_compaction(test_config)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        stored_turns = _stored_turns()
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=stored_turns
        )
        _fake_summarization(mocker, mock_query_agent, len(stored_turns))

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query=NEW_QUERY, conversation_id=EXISTING_CONV_ID
            ),
            auth=test_auth,
            mcp_headers={},
        )
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)
        summaries = conversation_cache.get_summaries(user_id, CONV_ID_LLAMA, False)
        assert [summary.summary_text for summary in summaries] == [DEFAULT_SUMMARY_TEXT]

        response = await get_conversation_v2(
            request=test_request,
            conversation_id=EXISTING_CONV_ID,
            auth=test_auth,
        )

        assert _returned_messages(response) == [
            ("user", NEW_QUERY),
            ("assistant", DEFAULT_MODEL_RESPONSE),
        ]
