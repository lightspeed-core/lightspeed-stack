"""Integration tests for conversation compaction in the streaming_query endpoint."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=too-many-locals
# pylint: disable=too-many-statements

import asyncio
import json
from typing import Any

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.streaming_query import streaming_query_endpoint_handler
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
    FOLDED_SUMMARY_TEXT,
    TEST_MODEL,
    assert_marker_count,
    await_lock_contention,
    collect_items,
    create_existing_conversation,
    enable_compaction,
    marker,
    msg,
    patch_get_all_conversation_items,
    setup_fold_mocks,
    verify_store_content,
)


async def _collect_sse_events(response: Any) -> list[dict[str, Any]]:
    """Consume a StreamingResponse and parse its SSE events into dicts.

    Args:
        response: A FastAPI StreamingResponse.

    Returns:
        List of parsed JSON event dicts (one per ``data:`` line).
    """
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        for line in chunk.strip().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def _setup_streaming_compaction_mocks(
    mocker: MockerFixture,
    mock_streaming_query_agent: AsyncMockType,
    items: list[Any],
    summary_text: str = DEFAULT_SUMMARY_TEXT,
) -> AsyncMockType:
    """Set up compaction mocks for streaming_query tests.

    Args:
        mocker: pytest-mock fixture.
        mock_streaming_query_agent: The mock streaming query agent fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.

    Returns:
        The mock for ``summarize_chunk``.
    """
    mock_streaming_query_agent.model.last_output_items = [
        OpenAIResponseMessage(
            role="assistant", content="This is a test response about Ansible."
        )
    ]

    return mocker.patch(
        "utils.conversation_compaction.summarize_chunk",
        new_callable=mocker.AsyncMock,
        return_value=ConversationSummary(
            summary_text=summary_text,
            summarized_through_turn=len(items),
            token_count=6,
            created_at="2026-08-10T00:00:00Z",
            model_used=TEST_MODEL,
        ),
    )


class TestStreamingQueryConversationCompaction:
    """Tests for conversation compaction behaviour in the streaming_query endpoint."""

    @pytest.mark.asyncio
    async def test_streaming_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Compaction triggers summarization when tokens exceed threshold.

        Verifies:
        - summarize_chunk is called for the old items
        - _write_summary_marker is called to persist the marker
        - The agent receives compacted params (omit_conversation=True,
          explicit input with summary text and the new query)
        """
        _ = mock_ogx_client
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize = _setup_streaming_compaction_mocks(
            mocker, mock_streaming_query_agent, items
        )

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        _ = await _collect_sse_events(response)

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 2
        assert not any("question one" in t for t in input_texts)
        assert not any("answer one" in t for t in input_texts)
        assert not any("question two" in t for t in input_texts)
        assert not any("answer two" in t for t in input_texts)
        assert any(DEFAULT_SUMMARY_TEXT in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        items_from_store = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        assert len(items_from_store) == 7
        expected = items + [
            marker(DEFAULT_SUMMARY_TEXT),
            msg("user", "What else can you help with?"),
            msg("assistant", DEFAULT_MODEL_RESPONSE),
        ]
        assert verify_store_content(items_from_store, expected)

    @pytest.mark.asyncio
    async def test_streaming_compaction_partition(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Compaction triggers summarization when tokens exceed threshold.

        Verifies:
        - summarize_chunk is called for the old items
        - _write_summary_marker is called to persist the marker
        - The agent receives compacted params (omit_conversation=True,
          explicit input with summary text and the new query)
        """
        _ = mock_ogx_client
        enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize = _setup_streaming_compaction_mocks(
            mocker, mock_streaming_query_agent, items
        )

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        _ = await _collect_sse_events(response)

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 4
        assert not any("question one" in t for t in input_texts)
        assert not any("answer one" in t for t in input_texts)
        assert any("question two" in t for t in input_texts)
        assert any("answer two" in t for t in input_texts)
        assert any(DEFAULT_SUMMARY_TEXT in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        items_from_store = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        assert len(items_from_store) == 7
        expected = items + [
            marker(DEFAULT_SUMMARY_TEXT),
            msg("user", "What else can you help with?"),
            msg("assistant", DEFAULT_MODEL_RESPONSE),
        ]
        assert verify_store_content(items_from_store, expected)

    @pytest.mark.asyncio
    async def test_streaming_compaction_emits_start_and_compaction_sse_events(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Compaction-aware path emits ``start`` and ``compaction`` SSE events.

        Verifies:
        - The first SSE event is a ``start`` event with conversation_id and
          request_id.
        - A ``compaction`` event with ``status: started`` is emitted before the
          agent response events.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, mock_streaming_query_agent, items)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        event_types = [e.get("event") for e in events]
        assert len([t for t in event_types if t == "compaction"]) == 1
        assert len([t for t in event_types if t == "start"]) == 1
        start_index, compaction_index = (
            event_types.index("start"),
            event_types.index("compaction"),
        )
        assert start_index < compaction_index

        start_event = next(e for e in events if e.get("event") == "start")
        assert start_event["data"]["conversation_id"] == EXISTING_CONV_ID
        assert "request_id" in start_event["data"]

        compaction_event = next(e for e in events if e.get("event") == "compaction")
        assert compaction_event["data"]["status"] == "started"
        assert compaction_event["data"]["conversation_id"] == EXISTING_CONV_ID

    @pytest.mark.asyncio
    async def test_streaming_compaction_existing_marker_no_compaction_event(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Existing marker builds explicit input without emitting a compaction SSE event.

        Verifies:
        - summarize_chunk is NOT called (under threshold)
        - No ``compaction`` SSE event is emitted (no new summarization needed)
        - Agent receives compacted params with summary from the marker
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            marker("Summary of the earlier discussion about troubleshooting"),
            msg("user", "recent follow-up question"),
            msg("assistant", "recent follow-up answer"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize = _setup_streaming_compaction_mocks(
            mocker, mock_streaming_query_agent, items
        )

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="Any updates?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        mock_summarize.assert_not_called()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 0

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 4
        assert not any("question one" in t for t in input_texts)
        assert not any("answer one" in t for t in input_texts)
        assert any("Summary of the earlier discussion" in t for t in input_texts)
        assert any("recent follow-up question" in t for t in input_texts)
        assert any("recent follow-up answer" in t for t in input_texts)
        assert input_texts[-1] == "Any updates?"

        items_from_store = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        assert len(items_from_store) == 7
        expected = items + [
            msg("user", "Any updates?"),
            msg("assistant", DEFAULT_MODEL_RESPONSE),
        ]
        assert verify_store_content(items_from_store, expected)

    @pytest.mark.asyncio
    async def test_streaming_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Small conversation under threshold passes through without compaction.

        Verifies:
        - No summarization or marker write
        - No ``compaction`` SSE event is emitted
        - Agent receives normal (non-compacted) params
        """
        _ = mock_ogx_client
        enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "hi"),
            msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize = _setup_streaming_compaction_mocks(
            mocker, mock_streaming_query_agent, items
        )

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="short question",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        mock_summarize.assert_not_called()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 0)

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 0

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_streaming_compaction_disabled_passes_through(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        patch_db_session: Session,
        test_request,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Disabled compaction skips the pipeline entirely.

        Verifies:
        - Agent receives unchanged, non-compacted params
        - No ``compaction`` SSE event is emitted
        """
        _ = test_config
        _ = mock_ogx_client
        _ = mocker

        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What is Ansible?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 0

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_streaming_compaction_additive_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Two successive streaming queries produce additive summaries.

        Verifies:
        - Round 1 triggers summarization and writes a marker.
        - Round 2 sees the existing marker, triggers a second summarization,
          and delivers both summaries in the explicit input.
        - Both rounds emit a ``compaction`` SSE event.
        """
        _ = mock_ogx_client
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize = _setup_streaming_compaction_mocks(
            mocker, mock_streaming_query_agent, items
        )

        # --- Round 1: first compaction should summarize the old items ---
        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 1

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 2
        assert not any("question one" in t for t in input_texts)
        assert not any("answer one" in t for t in input_texts)
        assert not any("question two" in t for t in input_texts)
        assert not any("answer two" in t for t in input_texts)
        assert any(DEFAULT_SUMMARY_TEXT in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        items_from_store = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        assert len(items_from_store) == 7
        expected = items + [
            marker(DEFAULT_SUMMARY_TEXT),
            msg("user", "What else can you help with?"),
            msg("assistant", DEFAULT_MODEL_RESPONSE),
        ]
        assert verify_store_content(items_from_store, expected)

        # --- Round 2: new turns added after the marker ---
        new_items = [
            msg("user", "question three " * 20),
            msg("assistant", "answer three " * 20),
        ]
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=new_items
        )

        mock_summarize.reset_mock()

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="Follow-up question",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 2)

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 1

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 3
        assert not any("What else can you help with?" in t for t in input_texts)
        assert not any(DEFAULT_MODEL_RESPONSE in t for t in input_texts)
        assert not any("question three" in t for t in input_texts)
        assert not any("answer three" in t for t in input_texts)
        assert sum(DEFAULT_SUMMARY_TEXT in t for t in input_texts) == 2
        assert input_texts[-1] == "Follow-up question"

        items_from_store = await collect_items(mock_conversation_store, CONV_ID_LLAMA)
        assert len(items_from_store) == 12
        expected = (
            expected
            + new_items
            + [
                marker(DEFAULT_SUMMARY_TEXT),
                msg("user", "Follow-up question"),
                msg("assistant", DEFAULT_MODEL_RESPONSE),
            ]
        )
        assert verify_store_content(items_from_store, expected)

    @pytest.mark.asyncio
    async def test_streaming_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Concurrent streaming requests on the same conversation are serialized by the lock.

        The streaming endpoint calls ``needs_compaction_path`` (unlocked) before
        returning the ``StreamingResponse``, so this test patches it to True and
        exercises the per-conversation lock inside ``apply_compaction`` only.

        Verifies:
        - Task 2 cannot enter the compaction critical section while task 1
          holds the per-conversation lock.
        - Task 2 proceeds once task 1 releases the lock.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        _setup_streaming_compaction_mocks(mocker, mock_streaming_query_agent, [])

        mocker.patch(
            "app.endpoints.streaming_query.needs_compaction_path",
            new_callable=mocker.AsyncMock,
            return_value=True,
        )

        entered, release, task2_entered = patch_get_all_conversation_items(mocker)

        async def _run_and_drain(query: str) -> None:
            """Run streaming_query_endpoint_handler and drain the response."""
            resp = await streaming_query_endpoint_handler(
                request=test_request,
                query_request=QueryRequest(
                    query=query, conversation_id=EXISTING_CONV_ID
                ),
                auth=test_auth,
                mcp_headers={},
            )
            async for _ in resp.body_iterator:
                pass

        task1 = asyncio.create_task(_run_and_drain("What is Ansible?"))
        await entered.wait()

        task2 = asyncio.create_task(_run_and_drain("What is RHEL?"))

        try:
            await asyncio.wait_for(await_lock_contention(CONV_ID_LLAMA), 10)
        except TimeoutError:
            pytest.fail("Task 2 never started")

        assert not task2.done()
        assert not task2_entered.is_set()

        release.set()
        await asyncio.gather(task1, task2)

        assert task2_entered.is_set()

    @pytest.mark.asyncio
    async def test_streaming_compaction_sse_event_ordering(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """SSE events follow the expected order: start, compaction, agent events.

        Verifies:
        - The ``start`` event comes first.
        - The ``compaction`` event comes second, before any agent content events.
        - Agent content events (token, turn_complete) follow the compaction event.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, mock_streaming_query_agent, items)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)
        event_types = [e.get("event") for e in events]

        assert event_types[0] == "start"
        assert event_types[1] == "compaction"

        remaining_types = set(event_types[2:])
        assert remaining_types.issubset({"token", "turn_complete", "end"})

    @pytest.mark.asyncio
    async def test_streaming_no_compaction_no_start_event_duplication(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Non-compaction path emits exactly one ``start`` event and no ``compaction`` event.

        Verifies:
        - Exactly one ``start`` SSE event is emitted.
        - Zero ``compaction`` SSE events are emitted.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            msg("user", "hi"),
            msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, mock_streaming_query_agent, items)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="short question",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        start_events = [e for e in events if e.get("event") == "start"]
        assert len(start_events) == 1

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 0

    @pytest.mark.asyncio
    async def test_streaming_compaction_recursive_fold(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Recursive fold triggers when cached summaries exceed the threshold.

        Verifies:
        - summarize_chunk is called (new compaction triggered).
        - recursively_resummarize is called (fold triggered).
        - cache.replace_summaries is called to persist the fold.
        - The agent receives a single folded summary in its input.
        - A ``compaction`` SSE event is emitted.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        items = [
            marker("summary of turns 1-2"),
            marker("summary of turns 3-4"),
            msg("user", "question five " * 20),
            msg("assistant", "answer five " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_cache, mock_summarize, mock_resummarize = setup_fold_mocks(
            mocker,
            "app.endpoints.streaming_query.configured_conversation_cache",
            items,
        )

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        events = await _collect_sse_events(response)

        mock_summarize.assert_awaited_once()
        mock_resummarize.assert_awaited_once()
        mock_cache.replace_summaries.assert_called_once()

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 1

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 2
        assert sum(FOLDED_SUMMARY_TEXT in t for t in input_texts) == 1
        assert input_texts[-1] == "What else can you help with?"
