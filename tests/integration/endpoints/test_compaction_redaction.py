"""Integration tests for PII redaction on compacted conversations (LCORE-4593)."""

from collections.abc import Awaitable, Callable
from typing import Any, Optional

import pytest
from a2a.server.agent_execution import RequestContext
from fastapi import Request
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.a2a import A2AAgentExecutor
from app.endpoints.query import query_endpoint_handler
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.common.responses.responses_api_params import ResponsesApiParams
from models.config import RedactionConfig, RedactionRule, RedactionShieldConfiguration
from tests.integration.conftest import InMemoryConversationStore
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    EXISTING_CONV_ID,
    TEST_MODEL,
    create_existing_conversation,
    enable_compaction,
    marker,
    msg,
)

RAW_QUERY = "Mail the report to jane@example.com"
REDACTED_QUERY = "Mail the report to [EMAIL]"


@pytest.fixture(name="store")
def store_fixture(
    test_config: AppConfig,
    mock_conversation_store: InMemoryConversationStore,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> InMemoryConversationStore:
    """Configure a redaction shield and store an already compacted conversation.

    The context window is far larger than the conversation, so no summarization
    runs: the stored marker alone puts the conversation into compacted mode.
    """
    enable_compaction(test_config, context_window=100_000)
    test_config.configuration.shields = [
        RedactionShieldConfiguration(
            name="pii-redaction",
            provider_id="redaction",
            config=RedactionConfig(
                rules=[RedactionRule(pattern=r"\S+@\S+", replacement="[EMAIL]")]
            ),
        )
    ]
    create_existing_conversation(patch_db_session, test_auth[0])
    mock_conversation_store.store[CONV_ID_LLAMA] = [
        msg("user", "old question"),
        msg("assistant", "old answer"),
        marker("earlier summary", covers=2),
    ]
    return mock_conversation_store


@pytest.fixture(name="ask")
def ask_fixture(
    mock_query_agent: Any,
    mock_streaming_query_agent: Any,
    test_request: Request,
    test_auth: AuthTuple,
) -> Callable[..., Awaitable[Any]]:
    """Return a function that sends RAW_QUERY and returns the params the agent got."""

    async def ask(streaming: bool, shield_ids: Optional[list[str]] = None) -> Any:
        """Send RAW_QUERY to /v1/streaming_query or to /v1/query."""
        agent = mock_streaming_query_agent if streaming else mock_query_agent
        agent.model.last_output_items = [
            OpenAIResponseMessage(role="assistant", content=DEFAULT_MODEL_RESPONSE)
        ]
        query_request = QueryRequest(
            query=RAW_QUERY, conversation_id=EXISTING_CONV_ID, shield_ids=shield_ids
        )
        if streaming:
            response = await streaming_query_endpoint_handler(
                test_request, query_request, auth=test_auth, mcp_headers={}
            )
            async for _ in response.body_iterator:
                pass
        else:
            await query_endpoint_handler(
                test_request, query_request, auth=test_auth, mcp_headers={}
            )
        return agent.build_agent_mock.call_args[0][1]

    return ask


def _stored_texts(store: InMemoryConversationStore) -> list[str]:
    """Return the text of every item stored for the conversation."""
    return [str(item.content) for item in store.store[CONV_ID_LLAMA]]


@pytest.mark.parametrize("streaming", [False, True], ids=["query", "streaming_query"])
async def test_compacted_turn_is_redacted(
    store: InMemoryConversationStore,
    ask: Callable[..., Awaitable[Any]],
    streaming: bool,
) -> None:
    """The model input and the stored turn carry the redacted query."""
    params = await ask(streaming)

    assert params.omit_conversation is True
    assert params.input[-1].content == REDACTED_QUERY
    assert _stored_texts(store)[3:] == [REDACTED_QUERY, DEFAULT_MODEL_RESPONSE]


@pytest.mark.parametrize("streaming", [False, True], ids=["query", "streaming_query"])
async def test_compacted_turn_honours_shield_ids(
    store: InMemoryConversationStore,
    ask: Callable[..., Awaitable[Any]],
    streaming: bool,
) -> None:
    """A request that deselects the shield sends and stores the query as it arrived."""
    params = await ask(streaming, shield_ids=[])

    assert params.input[-1].content == RAW_QUERY
    assert _stored_texts(store)[3:] == [RAW_QUERY, DEFAULT_MODEL_RESPONSE]


@pytest.mark.parametrize("streaming", [False, True], ids=["query", "streaming_query"])
async def test_not_compacted_turn_is_unchanged(
    store: InMemoryConversationStore,
    ask: Callable[..., Awaitable[Any]],
    streaming: bool,
) -> None:
    """Without a summary the agent gets the raw query and its capability redacts it."""
    store.store[CONV_ID_LLAMA] = [msg("user", "hi"), msg("assistant", "hello")]

    params = await ask(streaming)

    assert params.omit_conversation is False
    assert params.input == RAW_QUERY
    assert _stored_texts(store) == ["hi", "hello"]  # OGX stores this turn


async def test_a2a_compacted_turn_is_redacted(
    store: InMemoryConversationStore, mocker: MockerFixture
) -> None:
    """A2A, which runs every configured shield, sends and stores the redacted query."""
    mocker.patch(
        "app.endpoints.a2a.prepare_responses_params",
        new=mocker.AsyncMock(
            return_value=ResponsesApiParams(
                input=RAW_QUERY,
                model=TEST_MODEL,
                conversation=CONV_ID_LLAMA,
                store=True,
                stream=True,
            )
        ),
    )
    build_agent = mocker.patch("app.endpoints.a2a.build_agent")
    context = mocker.MagicMock(spec=RequestContext)
    context.get_user_input.return_value = RAW_QUERY
    context.message = None
    executor = A2AAgentExecutor(auth_token="test-token")

    await executor._process_task_streaming(  # pylint: disable=protected-access
        context, mocker.AsyncMock(), "task-4593", "ctx-4593"
    )

    assert build_agent.call_args[0][1].input[-1].content == REDACTED_QUERY
    # The mocked agent captures no output items, so only the query is stored.
    assert _stored_texts(store)[3:] == [REDACTED_QUERY]
