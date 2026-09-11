"""Integration tests for conversation compaction in the A2A endpoint."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
)
from fastapi import Request
from ogx_api.openai_responses import OpenAIResponseMessage
from pydantic_ai import AgentRunResultEvent
from pytest_mock import AsyncMockType, MockerFixture

from app.endpoints.a2a import handle_a2a_jsonrpc_post
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from tests.integration.conftest import InMemoryConversationStore
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    DEFAULT_SUMMARY_TEXT,
    TEST_MODEL,
    assert_marker_count,
    await_lock_contention,
    collect_items,
    enable_compaction,
    marker,
    msg,
    patch_get_all_conversation_items,
    verify_store_content,
)

_FAKE_AGENT_CARD = AgentCard(
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


def _build_a2a_request(user_input: str) -> Request:
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


def _mock_a2a_agent(mocker: MockerFixture) -> Any:
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


def _setup_a2a_compaction_mocks(
    mocker: MockerFixture,
    items: list[Any],
    summary_text: str = DEFAULT_SUMMARY_TEXT,
) -> tuple[AsyncMockType, Any]:
    """Set up mocks shared by A2A compaction tests.

    Patches the agent card, prepare_responses_params, and build_agent so
    that ``handle_a2a_jsonrpc_post`` reaches the real
    ``apply_compaction_blocking`` code path.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.

    Returns:
        Tuple of (mock_summarize, mock_build_agent).
    """
    mocker.patch(
        "app.endpoints.a2a.get_lightspeed_agent_card",
        return_value=_FAKE_AGENT_CARD,
    )

    async def _fake_prepare(client, query_request, *args, **kwargs):
        """Return ResponsesApiParams with the real query as input."""
        _ = client, args, kwargs
        return ResponsesApiParams(
            input=query_request.query,
            model=TEST_MODEL,
            conversation=CONV_ID_LLAMA,
            store=True,
            stream=True,
        )

    mocker.patch(
        "app.endpoints.a2a.prepare_responses_params",
        side_effect=_fake_prepare,
    )

    mock_agent = _mock_a2a_agent(mocker)
    mock_build_agent = mocker.patch(
        "app.endpoints.a2a.build_agent",
        return_value=mock_agent,
    )

    mock_summarize = mocker.patch(
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

    return mock_summarize, mock_build_agent


class TestA2AConversationCompaction:
    """Tests for conversation compaction behaviour in the A2A endpoint."""

    @pytest.mark.asyncio
    async def test_a2a_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
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

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_build_agent = _setup_a2a_compaction_mocks(mocker, items)

        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_build_agent.call_args[0][1]
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
    async def test_a2a_compaction_partition(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Buffer turns are preserved alongside the summary in compacted input.

        With ``buffer_turns=1``, the most recent user/assistant turn pair is
        kept verbatim while older turns are summarized.

        Verifies:
        - summarize_chunk and _write_summary_marker are called.
        - The agent receives compacted params with the summary, the buffered
          recent turn pair, and the new query (4 items total).
        """
        _ = mock_ogx_client

        enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_build_agent = _setup_a2a_compaction_mocks(mocker, items)

        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_build_agent.call_args[0][1]
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
    async def test_a2a_compaction_existing_marker_no_new_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Existing marker builds explicit input without new summarization.

        Verifies:
        - summarize_chunk is NOT called (under threshold)
        - Agent receives compacted params with summary from the marker,
          recent messages, and the new query
        """
        _ = mock_ogx_client

        enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            marker("Summary of the earlier discussion about troubleshooting"),
            msg("user", "recent follow-up question"),
            msg("assistant", "recent follow-up answer"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_build_agent = _setup_a2a_compaction_mocks(mocker, items)

        request = _build_a2a_request("Any updates?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_not_called()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_build_agent.call_args[0][1]
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
    async def test_a2a_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Small conversation under threshold passes through without compaction.

        Verifies:
        - No summarization or marker write
        - Agent receives normal (non-compacted) params
        """
        _ = mock_ogx_client

        enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )

        items = [
            msg("user", "hi"),
            msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_build_agent = _setup_a2a_compaction_mocks(mocker, items)

        request = _build_a2a_request("short question")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_not_called()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 0)

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_a2a_compaction_disabled_passes_through(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Disabled compaction skips the pipeline entirely.

        Verifies:
        - Agent receives unchanged, non-compacted params
        """
        _ = test_config
        _ = mock_ogx_client

        _, mock_build_agent = _setup_a2a_compaction_mocks(mocker, [])

        request = _build_a2a_request("What is Ansible?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_a2a_compaction_additive_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Two successive A2A requests produce additive summaries.

        Verifies:
        - Round 1 triggers summarization and writes a marker.
        - Round 2 sees the existing marker, triggers a second summarization,
          and delivers both summaries in the explicit input.
        """
        _ = mock_ogx_client

        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)

        items = [
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_build_agent = _setup_a2a_compaction_mocks(mocker, items)

        # --- Round 1 ---
        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        agent_params = mock_build_agent.call_args[0][1]
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

        request = _build_a2a_request("Follow-up question")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 2)

        agent_params = mock_build_agent.call_args[0][1]
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
    async def test_a2a_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """Concurrent A2A requests on the same conversation are serialized by the lock.

        Verifies:
        - Task 2 cannot enter the compaction critical section while task 1
          holds the per-conversation lock.
        - Task 2 proceeds once task 1 releases the lock.
        """
        _ = mock_ogx_client

        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        _setup_a2a_compaction_mocks(mocker, [])

        entered, release, task2_entered = patch_get_all_conversation_items(mocker)

        request1 = _build_a2a_request("What is Ansible?")
        task1 = asyncio.create_task(
            handle_a2a_jsonrpc_post(request=request1, auth=test_auth, mcp_headers={})
        )
        await entered.wait()

        request2 = _build_a2a_request("What is RHEL?")
        task2 = asyncio.create_task(
            handle_a2a_jsonrpc_post(request=request2, auth=test_auth, mcp_headers={})
        )

        try:
            await asyncio.wait_for(await_lock_contention(CONV_ID_LLAMA), 10)
        except TimeoutError:
            pytest.fail("Task 2 never started")

        assert not task2.done()
        assert not task2_entered.is_set()

        release.set()
        await asyncio.gather(task1, task2)

        assert task2_entered.is_set()
