"""Integration tests for the quota charge of the summarization calls (LCORE-3910).

Compaction makes an LLM call of its own to summarize older turns. The provider
bills it, so it is charged to the user's quota. It is charged when it is made,
so also when the turn that triggered it fails afterward.

The quota here is a real limiter on a SQLite database and the summarization
call is the real one, answered by the mocked OGX client. Every test reads what
the limiter holds after the request.
"""

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.successful.query import QueryResponse
from models.config import (
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    SQLiteDatabaseConfiguration,
)
from tests.integration.conftest import (
    InMemoryConversationStore,
    make_openai_response_object,
    set_query_agent_run,
)
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    EXISTING_CONV_ID,
    assert_marker_count,
    create_existing_conversation,
    enable_compaction,
    msg,
)

INITIAL_QUOTA = 100_000

# what the provider reports for the turn itself and for the summarization call
TURN_INPUT, TURN_OUTPUT = 100, 50
SUMMARY_INPUT, SUMMARY_OUTPUT = 640, 72
TURN = TURN_INPUT + TURN_OUTPUT
SUMMARY = SUMMARY_INPUT + SUMMARY_OUTPUT


@pytest.fixture(name="quota")
def quota_fixture(
    test_config: AppConfig, tmp_path: Path
) -> Generator[AppConfig, None, None]:
    """Give every user a quota, kept by a real limiter on a SQLite database."""
    # pylint: disable=protected-access
    assert test_config._configuration is not None
    test_config._configuration.quota_handlers = QuotaHandlersConfiguration(
        sqlite=SQLiteDatabaseConfiguration(db_path=str(tmp_path / "quota.db")),
        limiters=[
            QuotaLimiterConfiguration(
                type="user_limiter",
                name="user quota",
                initial_quota=INITIAL_QUOTA,
                quota_increase=0,
                period="1 day",
            )
        ],
    )
    test_config._quota_limiters = []
    yield test_config
    for limiter in test_config._quota_limiters:
        if limiter.connection is not None:
            limiter.connection.close()
    test_config._quota_limiters = []


@dataclass
class Scene:
    """A user with a quota, on a conversation the next request summarizes.

    Attributes:
        config: The configuration, with the quota limiter.
        store: The conversation store behind the mocked OGX client.
        agent: The mocked agent that answers the turn.
        request: The request object the handler gets.
        auth: The authenticated user.

    """

    config: AppConfig
    store: InMemoryConversationStore
    agent: AsyncMockType
    request: Request
    auth: AuthTuple

    async def query(self) -> QueryResponse:
        """Send a new query on the stored conversation."""
        return await query_endpoint_handler(
            request=self.request,
            query_request=QueryRequest(
                query="What else can you help with?", conversation_id=EXISTING_CONV_ID
            ),
            auth=self.auth,
            mcp_headers={},
        )

    def quota_left(self) -> int:
        """Read the quota the user has left, from the limiter."""
        (limiter,) = self.config.quota_limiters
        return limiter.available_quota(self.auth[0])


@pytest.fixture(name="scene")
async def scene_fixture(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    quota: AppConfig,
    mock_ogx_client: AsyncMockType,
    mock_conversation_store: InMemoryConversationStore,
    mock_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> Scene:
    """Set the scene: the quota, a long conversation, and what the two LLM calls report."""
    create_existing_conversation(patch_db_session, test_auth[0])
    enable_compaction(quota, context_window=200)
    await mock_conversation_store.create(
        conversation_id=CONV_ID_LLAMA,
        items=[
            msg("user", "question one " * 20),
            msg("assistant", "answer one " * 20),
            msg("user", "question two " * 20),
            msg("assistant", "answer two " * 20),
        ],
    )
    # The summarization call goes through client.responses.create, the turn
    # itself is answered by the agent.
    mock_ogx_client.responses.create = mocker.AsyncMock(
        return_value=make_openai_response_object(
            content="condensed earlier turns",
            input_tokens=SUMMARY_INPUT,
            output_tokens=SUMMARY_OUTPUT,
        )
    )
    set_query_agent_run(
        mock_query_agent, mocker, input_tokens=TURN_INPUT, output_tokens=TURN_OUTPUT
    )
    return Scene(
        quota, mock_conversation_store, mock_query_agent, test_request, test_auth
    )


@pytest.mark.asyncio
async def test_turn_that_summarizes_pays_for_the_summarization(scene: Scene) -> None:
    """The turn and the summarization call are charged, and the client is told both."""
    response = await scene.query()

    assert_marker_count(scene.store, CONV_ID_LLAMA, 1)
    assert response.context_status == "summarized"
    assert response.input_tokens == TURN_INPUT + SUMMARY_INPUT
    assert response.output_tokens == TURN_OUTPUT + SUMMARY_OUTPUT
    assert response.available_quotas == {
        "UserQuotaLimiter": INITIAL_QUOTA - TURN - SUMMARY
    }
    assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY


@pytest.mark.asyncio
async def test_failed_turn_that_summarized_pays_for_the_summarization(
    scene: Scene,
) -> None:
    """The summary is made and kept before the model call that then fails."""
    scene.agent.run.side_effect = RuntimeError("the model is down")

    with pytest.raises(HTTPException):
        await scene.query()

    assert_marker_count(scene.store, CONV_ID_LLAMA, 1)
    assert scene.quota_left() == INITIAL_QUOTA - SUMMARY
