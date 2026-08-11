"""Integration tests for conversation compaction in query, A2A, streaming, and responses."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=too-many-lines
# pylint: disable=too-many-locals
# pylint: disable=protected-access

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

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
from sqlalchemy.orm import Session

from app.endpoints.a2a import handle_a2a_jsonrpc_post
from app.endpoints.query import query_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest, ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.responses.contexts import ResponsesContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import CompactionConfiguration
from models.database.conversations import UserConversation
from tests.integration.conftest import InMemoryConversationStore
from utils.conversation_compaction import MARKER_SENTINEL

EXISTING_CONV_ID = "22222222-2222-2222-2222-222222222222"
CONV_ID_LLAMA = f"conv_{EXISTING_CONV_ID}"
TEST_MODEL = "test-provider/test-model"


def _msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed conversation message item."""
    return OpenAIResponseMessage(role=cast(Any, role), content=text)


def _marker(text: str) -> OpenAIResponseMessage:
    """Build a compaction summary marker message."""
    return OpenAIResponseMessage(
        role="user",
        content=f"{MARKER_SENTINEL} {text}",
    )


def _enable_compaction(
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


def _patch_write_summary_marker(
    mocker: MockerFixture,
    conversation_store: "InMemoryConversationStore | None" = None,
) -> AsyncMockType:
    """Patch ``_write_summary_marker`` with a fake or silent mock.

    Args:
        mocker: pytest-mock fixture.
        conversation_store: When provided, the patch writes a real marker
            into this store; otherwise it is a silent no-op AsyncMock.

    Returns:
        The mock object for ``_write_summary_marker``.
    """
    if conversation_store is not None:

        async def _fake_write_marker(
            client: Any, conversation_id: str, text: str
        ) -> None:
            _ = client
            marker_item = {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"{MARKER_SENTINEL} {text}"}
                ],
            }
            await conversation_store.create(
                conversation_id=conversation_id, items=[marker_item]
            )

        return mocker.patch(
            "utils.conversation_compaction._write_summary_marker",
            side_effect=_fake_write_marker,
        )

    return mocker.patch(
        "utils.conversation_compaction._write_summary_marker",
        new_callable=mocker.AsyncMock,
    )


def _patch_get_all_conversation_items(mocker: MockerFixture):
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


def _setup_query_compaction_mocks(
    mocker: MockerFixture,
    items: list[Any],
    summary_text: str = "condensed earlier turns",
    conversation_store: "InMemoryConversationStore | None" = None,
) -> tuple[AsyncMockType, AsyncMockType]:
    """Set up the common compaction mocks.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.
        conversation_store: When provided, _write_summary_marker writes the
            marker into this store instead of being a silent no-op.  This is
            needed for multi-round tests that rely on markers being present
            on subsequent queries.

    Returns:
        Tuple of (mock_summarize, mock_write_marker).
    """
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

    mock_write_marker = _patch_write_summary_marker(mocker, conversation_store)

    return mock_summarize, mock_write_marker


def _create_existing_conversation(
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


class TestQueryConversationCompation:
    """Tests for conversation compaction behaviour in the query endpoint."""

    @pytest.mark.asyncio
    async def test_query_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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

        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]

        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_query_compaction_mocks(mocker, items)

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_query_compaction_partition(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
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

        _enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]

        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_query_compaction_mocks(mocker, items)

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 4
        assert any("question two" in t for t in input_texts)
        assert any("answer two" in t for t in input_texts)
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_query_compaction_existing_marker_no_new_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Existing marker builds explicit input without new summarization.

        Verifies:
        - summarize_chunk is NOT called (under threshold)
        - Agent receives compacted params with summary from the marker,
          recent messages, and the new query
        """
        _ = mock_ogx_client

        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _marker("Summary of the earlier discussion about troubleshooting"),
            _msg("user", "recent follow-up question"),
            _msg("assistant", "recent follow-up answer"),
        ]

        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_query_compaction_mocks(mocker, items)

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="Any updates?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("Summary of the earlier discussion" in t for t in input_texts)
        assert any("recent follow-up question" in t for t in input_texts)
        assert any("recent follow-up answer" in t for t in input_texts)
        assert input_texts[-1] == "Any updates?"

    @pytest.mark.asyncio
    async def test_query_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Small conversation under threshold passes through without compaction.

        Verifies:
        - No summarization or marker write
        - Agent receives normal (non-compacted) params
        """
        _ = mock_ogx_client

        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "hi"),
            _msg("assistant", "hello"),
        ]

        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_query_compaction_mocks(mocker, items)

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="short question",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_query_compaction_disabled_passes_through(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        patch_db_session: Session,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Disabled compaction skips the pipeline entirely.

        Verifies:
        - Agent receives unchanged, non-compacted params
        """
        _ = test_config
        _ = mock_ogx_client

        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What is Ansible?", conversation_id=EXISTING_CONV_ID
            ),
            auth=test_auth,
            mcp_headers={},
        )

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is False
        assert isinstance(agent_params.input, str)

    @pytest.mark.asyncio
    async def test_query_conversation_compaction_additive_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ):
        """Two successive queries produce additive summaries.

        Verifies:
        - Round 1 triggers summarization and writes a marker.
        - Round 2 sees the existing marker, triggers a second summarization,
          and delivers both summaries in the explicit input.
        """
        _ = mock_ogx_client

        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]

        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_query_compaction_mocks(
            mocker, items, conversation_store=mock_conversation_store
        )

        # --- Round 1: first compaction should summarize the old items ---
        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="What else can you help with?",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        # --- Round 2: new turns added after the marker ---
        new_items = [
            _msg("user", "question three " * 20),
            _msg("assistant", "answer three " * 20),
        ]
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=new_items
        )

        mock_summarize.reset_mock()
        mock_write_marker.reset_mock()

        await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(
                query="Follow-up question",
                conversation_id=EXISTING_CONV_ID,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert sum("condensed earlier turns" in t for t in input_texts) == 2
        assert input_texts[-1] == "Follow-up question"

    @pytest.mark.asyncio
    async def test_query_conversation_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ):
        """Concurrent requests on the same conversation are serialized by the lock.

        Verifies:
        - Task 2 cannot enter the compaction critical section while task 1
          holds the per-conversation lock.
        - Task 2 proceeds once task 1 releases the lock.
        """
        _ = mock_ogx_client
        _ = mock_query_agent
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)

        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        entered, release, task2_entered = _patch_get_all_conversation_items(mocker)

        task1 = asyncio.create_task(
            query_endpoint_handler(
                request=test_request,
                query_request=QueryRequest(
                    query="What is Ansible?", conversation_id=EXISTING_CONV_ID
                ),
                auth=test_auth,
                mcp_headers={},
            )
        )
        await entered.wait()

        task2 = asyncio.create_task(
            query_endpoint_handler(
                request=test_request,
                query_request=QueryRequest(
                    query="What is RHEL?", conversation_id=EXISTING_CONV_ID
                ),
                auth=test_auth,
                mcp_headers={},
            )
        )
        await asyncio.sleep(0.05)

        assert not task2.done()

        # This proves that the second call is blocked by _conversation_locks so it does
        # not even reach to slow_get_items
        assert not task2_entered.is_set()

        release.set()
        await asyncio.gather(task1, task2)

        assert task2_entered.is_set()


# ---------------------------------------------------------------------------
# A2A endpoint helpers
# ---------------------------------------------------------------------------

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
    return mock_agent


def _setup_a2a_compaction_mocks(
    mocker: MockerFixture,
    items: list[Any],
    summary_text: str = "condensed earlier turns",
    conversation_store: "InMemoryConversationStore | None" = None,
) -> tuple[Any, Any, Any]:
    """Set up mocks shared by A2A compaction tests.

    Patches the agent card, prepare_responses_params, and build_agent so
    that ``handle_a2a_jsonrpc_post`` reaches the real
    ``apply_compaction_blocking`` code path.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.
        conversation_store: When provided, _write_summary_marker writes the
            marker into this store instead of being a silent no-op.

    Returns:
        Tuple of (mock_summarize, mock_write_marker, mock_build_agent).
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

    mock_write_marker = _patch_write_summary_marker(mocker, conversation_store)

    return mock_summarize, mock_write_marker, mock_build_agent


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

        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker, mock_build_agent = (
            _setup_a2a_compaction_mocks(mocker, items)
        )

        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

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

        _enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker, mock_build_agent = (
            _setup_a2a_compaction_mocks(mocker, items)
        )

        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 4
        assert any("question two" in t for t in input_texts)
        assert any("answer two" in t for t in input_texts)
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

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

        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )

        items = [
            _marker("Summary of the earlier discussion about troubleshooting"),
            _msg("user", "recent follow-up question"),
            _msg("assistant", "recent follow-up answer"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker, mock_build_agent = (
            _setup_a2a_compaction_mocks(mocker, items)
        )

        request = _build_a2a_request("Any updates?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("Summary of the earlier discussion" in t for t in input_texts)
        assert any("recent follow-up question" in t for t in input_texts)
        assert any("recent follow-up answer" in t for t in input_texts)
        assert input_texts[-1] == "Any updates?"

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

        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )

        items = [
            _msg("user", "hi"),
            _msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker, mock_build_agent = (
            _setup_a2a_compaction_mocks(mocker, items)
        )

        request = _build_a2a_request("short question")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

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

        _, _, mock_build_agent = _setup_a2a_compaction_mocks(mocker, [])

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

        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker, mock_build_agent = (
            _setup_a2a_compaction_mocks(
                mocker, items, conversation_store=mock_conversation_store
            )
        )

        # --- Round 1 ---
        request = _build_a2a_request("What else can you help with?")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        # --- Round 2: new turns added after the marker ---
        new_items = [
            _msg("user", "question three " * 20),
            _msg("assistant", "answer three " * 20),
        ]
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=new_items
        )

        mock_summarize.reset_mock()
        mock_write_marker.reset_mock()

        request = _build_a2a_request("Follow-up question")
        await handle_a2a_jsonrpc_post(request=request, auth=test_auth, mcp_headers={})

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        agent_params = mock_build_agent.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert sum("condensed earlier turns" in t for t in input_texts) == 2
        assert input_texts[-1] == "Follow-up question"

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

        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        _setup_a2a_compaction_mocks(mocker, [])

        entered, release, task2_entered = _patch_get_all_conversation_items(mocker)

        request1 = _build_a2a_request("What is Ansible?")
        task1 = asyncio.create_task(
            handle_a2a_jsonrpc_post(request=request1, auth=test_auth, mcp_headers={})
        )
        await entered.wait()

        request2 = _build_a2a_request("What is RHEL?")
        task2 = asyncio.create_task(
            handle_a2a_jsonrpc_post(request=request2, auth=test_auth, mcp_headers={})
        )
        await asyncio.sleep(0.05)

        assert not task2.done()
        assert not task2_entered.is_set()

        release.set()
        await asyncio.gather(task1, task2)

        assert task2_entered.is_set()


# ---------------------------------------------------------------------------
# Responses endpoint helpers
# ---------------------------------------------------------------------------

_RESPONSE_DUMP: dict[str, Any] = {
    "id": "resp_compaction_test",
    "object": "response",
    "created_at": 1700000000,
    "status": "completed",
    "model": TEST_MODEL,
    "output": [
        {
            "type": "message",
            "id": "msg-1",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "Test compaction response.",
                    "annotations": [],
                }
            ],
        }
    ],
    "usage": {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    },
}


def _setup_responses_base(
    mocker: MockerFixture,
    mock_ogx_client: Any,
) -> Any:
    """Set up the base mocks shared by all responses compaction tests.

    Configures the mock Llama Stack client (from the ``mock_ogx_client``
    fixture) with a ``responses.create`` return value that includes
    ``model_dump``, and bypasses ResponsesContext validation.

    Args:
        mocker: pytest-mock fixture.
        mock_ogx_client: The mock Llama Stack client from the fixture.

    Returns:
        The mock ``handle_non_streaming_response`` function.
    """
    mock_response = mocker.MagicMock()
    mock_response.id = "resp_compaction_test"
    mock_output = mocker.MagicMock()
    mock_output.type = "message"
    mock_output.role = "assistant"
    mock_output.content = "Test compaction response."
    mock_output.refusal = None
    mock_response.output = [mock_output]
    mock_response.usage = mocker.MagicMock()
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5
    mock_response.status = "completed"
    mock_response.model = TEST_MODEL
    mock_response.model_dump.return_value = _RESPONSE_DUMP.copy()
    mock_ogx_client.responses.create = mocker.AsyncMock(return_value=mock_response)

    original_ctx_cls = ResponsesContext

    def _skip_validation(**kwargs: Any) -> ResponsesContext:
        """Bypass Pydantic validation for ResponsesContext."""
        return original_ctx_cls.model_construct(**kwargs)

    mocker.patch(
        "app.endpoints.responses.ResponsesContext", side_effect=_skip_validation
    )

    mock_response = mocker.AsyncMock(spec=ResponsesResponse)
    mock_handle_non_streaming_response = mocker.patch(
        "app.endpoints.responses.handle_non_streaming_response",
        return_value=mock_response,
    )

    return mock_handle_non_streaming_response


def _setup_responses_compaction_mocks(
    mocker: MockerFixture,
    items: list[Any],
    summary_text: str = "condensed earlier turns",
    conversation_store: "InMemoryConversationStore | None" = None,
) -> tuple[Any, Any]:
    """Set up compaction-specific mocks for responses endpoint tests.

    Patches ``summarize_chunk`` and ``_write_summary_marker`` for compaction
    integration tests.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.
        conversation_store: When provided, _write_summary_marker writes the
            marker into this store instead of being a silent no-op.

    Returns:
        Tuple of (mock_summarize, mock_write_marker).
    """
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

    mock_write_marker = _patch_write_summary_marker(mocker, conversation_store)

    return mock_summarize, mock_write_marker


class TestResponsesConversationCompaction:
    """Tests for conversation compaction behaviour in the responses endpoint."""

    @pytest.mark.asyncio
    async def test_responses_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Compaction triggers summarization when tokens exceed threshold.

        Verifies:
        - summarize_chunk is called for the old items
        - _write_summary_marker is called to persist the marker
        - The response completes successfully
        """
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize, mock_write_marker = _setup_responses_compaction_mocks(
            mocker, items
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="What else can you help with?",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_responses_compaction_partition(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        patch_db_session: Session,
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
        _enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize, mock_write_marker = _setup_responses_compaction_mocks(
            mocker, items
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="What else can you help with?",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert len(input_texts) == 4
        assert any("question two" in t for t in input_texts)
        assert any("answer two" in t for t in input_texts)
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_responses_compaction_existing_marker_no_new_summarization(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Existing marker builds explicit input without new summarization.

        Verifies:
        - summarize_chunk is NOT called (under threshold)
        - The response completes successfully
        """
        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _marker("Summary of the earlier discussion about troubleshooting"),
            _msg("user", "recent follow-up question"),
            _msg("assistant", "recent follow-up answer"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize, mock_write_marker = _setup_responses_compaction_mocks(
            mocker, items
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="Any updates?",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert any("Summary of the earlier discussion" in t for t in input_texts)
        assert any("recent follow-up question" in t for t in input_texts)
        assert any("recent follow-up answer" in t for t in input_texts)
        assert input_texts[-1] == "Any updates?"

    @pytest.mark.asyncio
    async def test_responses_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Small conversation under threshold passes through without compaction.

        Verifies:
        - No summarization or marker write
        """
        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "hi"),
            _msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize, mock_write_marker = _setup_responses_compaction_mocks(
            mocker, items
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="short question",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_not_called()
        mock_write_marker.assert_not_called()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is False
        assert isinstance(api_params.input, str)

    @pytest.mark.asyncio
    async def test_responses_compaction_disabled_passes_through(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Disabled compaction skips the pipeline entirely.

        Verifies:
        - The response completes without any compaction activity
        """
        _ = test_config
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="What is Ansible?",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is False
        assert isinstance(api_params.input, str)

    @pytest.mark.asyncio
    async def test_responses_compaction_additive_summarization(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Two successive requests produce additive summaries.

        Verifies:
        - Round 1 triggers summarization and writes a marker.
        - Round 2 sees the existing marker, triggers a second summarization,
          and writes a second marker.
        """
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize, mock_write_marker = _setup_responses_compaction_mocks(
            mocker, items, conversation_store=mock_conversation_store
        )

        # --- Round 1 ---
        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="What else can you help with?",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        # --- Round 2: new turns added after the marker ---
        new_items = [
            _msg("user", "question three " * 20),
            _msg("assistant", "answer three " * 20),
        ]
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=new_items
        )

        mock_summarize.reset_mock()
        mock_write_marker.reset_mock()

        await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input="Follow-up question",
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=False,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )

        mock_summarize.assert_awaited_once()
        mock_write_marker.assert_awaited_once()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert sum("condensed earlier turns" in t for t in input_texts) == 2
        assert input_texts[-1] == "Follow-up question"

    @pytest.mark.asyncio
    async def test_responses_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        test_request: Request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Concurrent requests on the same conversation are serialized by the lock.

        Verifies:
        - Task 2 cannot enter the compaction critical section while task 1
          holds the per-conversation lock.
        - Task 2 proceeds once task 1 releases the lock.
        """
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        _setup_responses_base(mocker, mock_ogx_client)

        entered, release, task2_entered = _patch_get_all_conversation_items(mocker)

        task1 = asyncio.create_task(
            responses_endpoint_handler(
                request=test_request,
                responses_request=ResponsesRequest(
                    input="What is Ansible?",
                    model=TEST_MODEL,
                    conversation=EXISTING_CONV_ID,
                    stream=False,
                    store=True,
                    generate_topic_summary=False,
                ),
                auth=test_auth,
                mcp_headers={},
            )
        )
        await entered.wait()

        task2 = asyncio.create_task(
            responses_endpoint_handler(
                request=test_request,
                responses_request=ResponsesRequest(
                    input="What is RHEL?",
                    model=TEST_MODEL,
                    conversation=EXISTING_CONV_ID,
                    stream=False,
                    store=True,
                    generate_topic_summary=False,
                ),
                auth=test_auth,
                mcp_headers={},
            )
        )
        await asyncio.sleep(0.05)

        assert not task2.done()
        assert not task2_entered.is_set()

        release.set()
        await asyncio.gather(task1, task2)

        assert task2_entered.is_set()


# ---------------------------------------------------------------------------
# Streaming query endpoint helpers
# ---------------------------------------------------------------------------


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
    items: list[Any],
    summary_text: str = "condensed earlier turns",
    conversation_store: "InMemoryConversationStore | None" = None,
) -> tuple[AsyncMockType, AsyncMockType]:
    """Set up compaction mocks for streaming_query tests.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.
        conversation_store: When provided, _write_summary_marker writes the
            marker into this store instead of being a silent no-op.

    Returns:
        Tuple of (mock_summarize, mock_write_marker).
    """
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

    mock_write_marker = _patch_write_summary_marker(mocker, conversation_store)

    return mock_summarize, mock_write_marker


class TestStreamingQueryConversationCompaction:
    """Tests for conversation compaction behaviour in the streaming_query endpoint."""

    @pytest.mark.asyncio
    async def test_streaming_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_streaming_compaction_mocks(
            mocker, items
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
        mock_write_marker.assert_awaited_once()

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_streaming_compaction_partition(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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
        _enable_compaction(
            test_config,
            context_window=200,
            threshold_ratio=0.1,
            buffer_turns=1,
            buffer_max_ratio=0.5,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_streaming_compaction_mocks(
            mocker, items
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
        mock_write_marker.assert_awaited_once()

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert len(input_texts) == 4
        assert any("question two" in t for t in input_texts)
        assert any("answer two" in t for t in input_texts)
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

    @pytest.mark.asyncio
    async def test_streaming_compaction_emits_start_and_compaction_sse_events(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, items)

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
        test_request: Request,
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
        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=1,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _marker("Summary of the earlier discussion about troubleshooting"),
            _msg("user", "recent follow-up question"),
            _msg("assistant", "recent follow-up answer"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_streaming_compaction_mocks(
            mocker, items
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
        mock_write_marker.assert_not_called()

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 0

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("Summary of the earlier discussion" in t for t in input_texts)
        assert input_texts[-1] == "Any updates?"

    @pytest.mark.asyncio
    async def test_streaming_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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
        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "hi"),
            _msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_streaming_compaction_mocks(
            mocker, items
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
        mock_write_marker.assert_not_called()

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
        test_request: Request,
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
        _create_existing_conversation(patch_db_session, user_id)

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
        test_request: Request,
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
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        mock_summarize, mock_write_marker = _setup_streaming_compaction_mocks(
            mocker, items, conversation_store=mock_conversation_store
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
        mock_write_marker.assert_awaited_once()

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 1

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert any("condensed earlier turns" in t for t in input_texts)
        assert input_texts[-1] == "What else can you help with?"

        # --- Round 2: new turns added after the marker ---
        new_items = [
            _msg("user", "question three " * 20),
            _msg("assistant", "answer three " * 20),
        ]
        await mock_conversation_store.create(
            conversation_id=CONV_ID_LLAMA, items=new_items
        )

        mock_summarize.reset_mock()
        mock_write_marker.reset_mock()

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
        mock_write_marker.assert_awaited_once()

        compaction_events = [e for e in events if e.get("event") == "compaction"]
        assert len(compaction_events) == 1

        agent_params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert agent_params.omit_conversation is True
        assert isinstance(agent_params.input, list)

        input_texts = [getattr(m, "content", "") for m in agent_params.input]
        assert sum("condensed earlier turns" in t for t in input_texts) == 2
        assert input_texts[-1] == "Follow-up question"

    @pytest.mark.asyncio
    async def test_streaming_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        test_request: Request,
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
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        _setup_streaming_compaction_mocks(mocker, [])

        mocker.patch(
            "app.endpoints.streaming_query.needs_compaction_path",
            new_callable=mocker.AsyncMock,
            return_value=True,
        )

        entered, release, task2_entered = _patch_get_all_conversation_items(mocker)

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
        await asyncio.sleep(0.05)

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
        test_request: Request,
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
        _enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "question one " * 20),
            _msg("assistant", "answer one " * 20),
            _msg("user", "question two " * 20),
            _msg("assistant", "answer two " * 20),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, items)

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
        assert remaining_types.issubset({"token", "turn_complete", "end", "error"})

    @pytest.mark.asyncio
    async def test_streaming_no_compaction_no_start_event_duplication(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
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
        _enable_compaction(
            test_config,
            context_window=1_000_000,
            threshold_ratio=0.5,
            buffer_turns=4,
        )
        user_id, _, _, _ = test_auth
        _create_existing_conversation(patch_db_session, user_id)

        items = [
            _msg("user", "hi"),
            _msg("assistant", "hello"),
        ]
        await mock_conversation_store.create(conversation_id=CONV_ID_LLAMA, items=items)

        _setup_streaming_compaction_mocks(mocker, items)

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
