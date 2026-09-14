"""Integration tests for conversation compaction in the responses endpoint."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=too-many-locals

import asyncio
from typing import Any

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import AsyncMockType, MockerFixture, MockType
from sqlalchemy.orm import Session

from app.endpoints.responses import (
    _append_previous_response_turn,
    responses_endpoint_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.responses.contexts import ResponsesContext
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
) -> MockType:
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

    mock_result = mocker.AsyncMock(spec=ResponsesResponse)

    output_item = OpenAIResponseMessage(
        role="assistant", content=DEFAULT_MODEL_RESPONSE
    )

    async def _handle_and_append(
        original_request: Any,
        api_params: Any,
        context: Any,
    ) -> Any:
        """Call the real turn-append logic, then return the mock response."""
        _ = original_request
        await _append_previous_response_turn(api_params, context, [output_item])
        return mock_result

    mock_handle_non_streaming_response = mocker.patch(
        "app.endpoints.responses.handle_non_streaming_response",
        side_effect=_handle_and_append,
    )

    return mock_handle_non_streaming_response


def _setup_responses_compaction_mocks(
    mocker: MockerFixture,
    items: list[Any],
    summary_text: str = DEFAULT_SUMMARY_TEXT,
) -> AsyncMockType:
    """Set up compaction-specific mocks for responses endpoint tests.

    Patches ``summarize_chunk`` for compaction integration tests.

    Args:
        mocker: pytest-mock fixture.
        items: Conversation items used to set summarized_through_turn.
        summary_text: Text returned by the fake summarize_chunk.

    Returns:
        The mock for ``summarize_chunk``.
    """
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


class TestResponsesConversationCompaction:
    """Tests for conversation compaction behaviour in the responses endpoint."""

    @pytest.mark.asyncio
    async def test_responses_compaction_triggers_summarization(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Compaction triggers summarization when tokens exceed threshold.

        Verifies:
        - summarize_chunk is called for the old items
        - _write_summary_marker is called to persist the marker
        - The response completes successfully
        """
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize = _setup_responses_compaction_mocks(mocker, items)

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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True

        input_texts = [getattr(m, "content", "") for m in api_params.input]
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
    async def test_responses_compaction_partition(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize = _setup_responses_compaction_mocks(mocker, items)

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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True

        input_texts = [getattr(m, "content", "") for m in api_params.input]
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
    async def test_responses_compaction_existing_marker_no_new_summarization(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Existing marker builds explicit input without new summarization.

        Verifies:
        - summarize_chunk is NOT called (under threshold)
        - The response completes successfully
        """
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize = _setup_responses_compaction_mocks(mocker, items)

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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
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
    async def test_responses_compaction_small_conversation_no_compaction(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Small conversation under threshold passes through without compaction.

        Verifies:
        - No summarization or marker write
        """
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize = _setup_responses_compaction_mocks(mocker, items)

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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 0)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is False
        assert isinstance(api_params.input, str)

    @pytest.mark.asyncio
    async def test_responses_compaction_disabled_passes_through(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Disabled compaction skips the pipeline entirely.

        Verifies:
        - The response completes without any compaction activity
        """
        _ = test_config
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

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
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Two successive requests produce additive summaries.

        Verifies:
        - Round 1 triggers summarization and writes a marker.
        - Round 2 sees the existing marker, triggers a second summarization,
          and writes a second marker.
        """
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_summarize = _setup_responses_compaction_mocks(mocker, items)

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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 1)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
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
        assert_marker_count(mock_conversation_store, CONV_ID_LLAMA, 2)

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
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
    async def test_responses_compaction_blocking_concurrent_request_with_same_id(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Concurrent requests on the same conversation are serialized by the lock.

        Verifies:
        - Task 2 cannot enter the compaction critical section while task 1
          holds the per-conversation lock.
        - Task 2 proceeds once task 1 releases the lock.
        """
        enable_compaction(test_config, context_window=200, threshold_ratio=0.1)
        user_id, _, _, _ = test_auth
        create_existing_conversation(patch_db_session, user_id)

        _setup_responses_base(mocker, mock_ogx_client)

        entered, release, task2_entered = patch_get_all_conversation_items(mocker)

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
    async def test_responses_compaction_recursive_fold(
        self,
        test_config: AppConfig,
        test_auth: AuthTuple,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """Recursive fold triggers when cached summaries exceed the threshold.

        Verifies:
        - summarize_chunk is called (new compaction triggered).
        - recursively_resummarize is called (fold triggered).
        - cache.replace_summaries is called to persist the fold.
        - The agent receives a single folded summary in its input.
        """
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

        mock_handle_non_streaming_response = _setup_responses_base(
            mocker, mock_ogx_client
        )

        mock_cache, mock_summarize, mock_resummarize = setup_fold_mocks(
            mocker,
            "app.endpoints.responses.configured_conversation_cache",
            items,
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
        mock_resummarize.assert_awaited_once()
        mock_cache.replace_summaries.assert_called_once()

        api_params = mock_handle_non_streaming_response.call_args[1]["api_params"]
        assert api_params.omit_conversation is True
        assert isinstance(api_params.input, list)

        input_texts = [getattr(m, "content", "") for m in api_params.input]
        assert sum(FOLDED_SUMMARY_TEXT in t for t in input_texts) == 1
        assert input_texts[-1] == "What else can you help with?"
