"""Integration tests for the token usage of the summarization calls (LCORE-3910).

Compaction makes an LLM call of its own to summarize older turns. The provider
bills it, so it is charged to the user's quota and shows in the token counts
of the turn that triggered it.

The summarization call is charged when it is made, so it is charged also when
the turn that triggered it is blocked, fails or is interrupted.

The quota here is a real limiter on a SQLite database and the summarization
call is the real one, answered by the mocked OGX client. Every test reads what
the limiter holds after the request.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client.models.open_ai_response_object_stream_response_completed import (
    OpenAIResponseObjectStreamResponseCompleted,
)
from prometheus_client import REGISTRY
from pydantic_ai.messages import PartStartEvent, TextPart
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.a2a import handle_a2a_jsonrpc_post
from app.endpoints.query import query_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from cache.sqlite_cache import SQLiteCache
from configuration import AppConfig
from constants import (
    ENDPOINT_PATH_A2A,
    ENDPOINT_PATH_QUERY,
    ENDPOINT_PATH_RESPONSES,
    ENDPOINT_PATH_STREAMING_QUERY,
)
from models.api.requests import QueryRequest, ResponsesRequest
from models.common.moderation import ShieldModerationBlocked
from models.common.responses.contexts import ResponsesContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import (
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    SQLiteDatabaseConfiguration,
)
from tests.integration.conftest import (
    TEST_MODEL_NAME,
    TEST_PROVIDER,
    InMemoryConversationStore,
    make_openai_response_object,
    set_query_agent_run,
    set_streaming_query_agent_run,
)
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    EXISTING_CONV_ID,
    FAKE_AGENT_CARD,
    TEST_MODEL,
    assert_marker_count,
    build_a2a_request,
    create_existing_conversation,
    enable_compaction,
    marker,
    mock_a2a_agent,
    msg,
)
from utils.compaction import RECURSIVE_RESUMMARIZATION_PROMPT, SUMMARIZATION_PROMPT
from utils.stream_interrupts import CancelStreamResult, get_stream_interrupt_registry

INITIAL_QUOTA = 100_000
QUOTA = "UserQuotaLimiter"
NEW_QUERY = "What else can you help with?"

# what the provider reports for the turn itself, for the summarization call and
# for the call that folds the summaries
TURN_INPUT, TURN_OUTPUT = 100, 50
SUMMARY_INPUT, SUMMARY_OUTPUT = 640, 72
FOLD_INPUT, FOLD_OUTPUT = 310, 45
TURN = TURN_INPUT + TURN_OUTPUT
SUMMARY = SUMMARY_INPUT + SUMMARY_OUTPUT
FOLD = FOLD_INPUT + FOLD_OUTPUT


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


@pytest.fixture(name="conversation_cache")
def conversation_cache_fixture(
    test_config: AppConfig, mocker: MockerFixture
) -> Generator[SQLiteCache, None, None]:
    """Configure a conversation cache, where compaction keeps and folds its summaries."""
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


def _metrics_added(endpoint: str) -> Callable[[], tuple[float, ...]]:
    """Start watching the LLM metrics of the test model under one endpoint.

    Parameters:
        endpoint: The endpoint label of the metrics.

    Returns:
        A function that reads what was added since: the tokens sent, the
        tokens received and the number of LLM calls.
    """
    labels = {"provider": TEST_PROVIDER, "model": TEST_MODEL_NAME, "endpoint": endpoint}

    def _read() -> tuple[float, ...]:
        """Read the three metrics."""
        return tuple(
            REGISTRY.get_sample_value(name, labels) or 0.0
            for name in (
                "ls_llm_token_sent_total",
                "ls_llm_token_received_total",
                "ls_llm_calls_total",
            )
        )

    before = _read()
    return lambda: tuple(now - then for now, then in zip(_read(), before))


def _long_conversation() -> list[OpenAIResponseMessage]:
    """Two stored turns, long enough for the next request to summarize them."""
    return [
        msg("user", "question one " * 20),
        msg("assistant", "answer one " * 20),
        msg("user", "question two " * 20),
        msg("assistant", "answer two " * 20),
    ]


EARLIER_SUMMARIES = ("the first summary", "the second summary")


def _store_two_summaries(cache: SQLiteCache, user_id: str) -> None:
    """Store two summaries that grow too large to keep once a third is added."""
    for number, text in enumerate(EARLIER_SUMMARIES, 1):
        cache.store_summary(
            user_id,
            CONV_ID_LLAMA,
            ConversationSummary(
                summary_text=text,
                summarized_through_turn=2 * number,
                token_count=15,
                created_at=f"2026-09-28T00:00:0{number}Z",
                model_used=TEST_MODEL,
            ),
        )


def _compacted_conversation() -> list[OpenAIResponseMessage]:
    """A conversation that was summarized before and has nothing to summarize now."""
    return [marker("summary of the earlier turns")]


def _answer_like_ogx(
    mock_ogx_client: AsyncMockType,
    mocker: MockerFixture,
    turn_error: Optional[Exception] = None,
) -> None:
    """Let the mocked OGX answer the calls made through ``client.responses.create``.

    Those are the summarization call and the fold call, told apart by their
    instructions, and on ``/v1/responses`` the turn itself. On ``/v1/query``
    and ``/v1/streaming_query`` the turn is answered by the mocked agent. With
    *turn_error* the calls of compaction are answered and the turn fails.
    """

    async def _create(**kwargs: Any) -> Any:
        """Answer one call."""
        if kwargs.get("instructions") == SUMMARIZATION_PROMPT:
            return make_openai_response_object(
                content="condensed earlier turns",
                input_tokens=SUMMARY_INPUT,
                output_tokens=SUMMARY_OUTPUT,
            )
        if kwargs.get("instructions") == RECURSIVE_RESUMMARIZATION_PROMPT:
            return make_openai_response_object(
                content="all earlier turns in one summary",
                input_tokens=FOLD_INPUT,
                output_tokens=FOLD_OUTPUT,
            )
        if turn_error is not None:
            raise turn_error
        response = make_openai_response_object(
            content=DEFAULT_MODEL_RESPONSE,
            input_tokens=TURN_INPUT,
            output_tokens=TURN_OUTPUT,
        )
        if kwargs.get("stream"):
            return _one_chunk_stream(response)
        return response

    mock_ogx_client.responses.create = mocker.AsyncMock(side_effect=_create)


async def _one_chunk_stream(response: Any) -> Any:
    """Yield the terminal event of a streamed response."""
    yield OpenAIResponseObjectStreamResponseCompleted(
        response=response, sequence_number=1, type="response.completed"
    )


def _events(chunks: list[str]) -> list[dict[str, Any]]:
    """Parse the ``data:`` lines of a stream."""
    events = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[len("data: ") :]))
    return events


async def _drain(response: Any) -> list[dict[str, Any]]:
    """Read a streaming response to its end and return its events."""
    assert isinstance(response, StreamingResponse)
    return _events([str(chunk) async for chunk in response.body_iterator])


def _blocked() -> ShieldModerationBlocked:
    """Return the verdict of a shield that blocked the request."""
    return ShieldModerationBlocked(
        message="Content blocked by safety shield", moderation_id="modr_blocked_1"
    )


def _stream_that_stalls() -> Any:
    """Build an agent stream that sends one token and then waits to be interrupted."""

    async def _agent_events() -> AsyncIterator[Any]:
        """Send one token and wait."""
        yield PartStartEvent(index=0, part=TextPart(content="Ansible is"))
        await asyncio.Event().wait()

    class _RunStreamCtx:
        """Async context manager matching ``agent.run_stream_events``."""

        async def __aenter__(self) -> AsyncIterator[Any]:
            return _agent_events()

        async def __aexit__(self, *_args: object) -> None:
            return None

    return _RunStreamCtx()


async def _interrupt_stream(response: Any, user_id: str) -> list[dict[str, Any]]:
    """Interrupt a stream after its first token and return its events."""
    assert isinstance(response, StreamingResponse)
    chunks: list[str] = []
    first_token = asyncio.Event()

    async def _consume() -> None:
        """Read the stream until it ends."""
        async for chunk in response.body_iterator:
            chunks.append(str(chunk))
            if '"event": "token"' in str(chunk):
                first_token.set()

    consumer = asyncio.create_task(_consume())
    await asyncio.wait_for(first_token.wait(), timeout=5)
    (start,) = [e for e in _events(chunks) if e.get("event") == "start"]
    result = get_stream_interrupt_registry().cancel_stream(
        start["data"]["request_id"], user_id
    )
    assert result == CancelStreamResult.CANCELLED
    await asyncio.wait_for(consumer, timeout=5)
    # The interrupt callback runs as a task of its own; let it finish.
    pending = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done()
    ]
    if pending:
        await asyncio.wait(pending, timeout=5)
    return _events(chunks)


@dataclass
class Scene:
    """A user with a quota, a stored conversation, and what a request on it needs.

    Attributes:
        config: The configuration, with the quota limiter.
        store: The conversation store behind the mocked OGX client.
        ogx: The mocked OGX client, which answers the calls of compaction.
        request: The request object the handlers get.
        auth: The authenticated user.
    """

    config: AppConfig
    store: InMemoryConversationStore
    ogx: AsyncMockType
    request: Request
    auth: AuthTuple

    async def holds(
        self, items: list[OpenAIResponseMessage], context_window: int = 200
    ) -> None:
        """Enable compaction and store the conversation the request continues."""
        enable_compaction(self.config, context_window=context_window)
        await self.store.create(conversation_id=CONV_ID_LLAMA, items=items)

    def quota_left(self) -> int:
        """Read the quota the user has left, from the limiter."""
        (limiter,) = self.config.quota_limiters
        return limiter.available_quota(self.auth[0])

    def quotas(self, consumed: int) -> dict[str, int]:
        """Return what the client is told after *consumed* tokens were charged."""
        return {QUOTA: INITIAL_QUOTA - consumed}

    def summarized_once(self) -> None:
        """Check that the request stored one summary marker in the conversation."""
        assert_marker_count(self.store, CONV_ID_LLAMA, 1)


@pytest.fixture(name="scene")
def scene_fixture(
    quota: AppConfig,
    mock_ogx_client: AsyncMockType,
    mock_conversation_store: InMemoryConversationStore,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
    mocker: MockerFixture,
) -> Scene:
    """Set the scene: the user, the quota, and an OGX that answers compaction."""
    create_existing_conversation(patch_db_session, test_auth[0])
    _answer_like_ogx(mock_ogx_client, mocker)
    return Scene(
        quota, mock_conversation_store, mock_ogx_client, test_request, test_auth
    )


# ==========================================
# /v1/query
# ==========================================


@pytest.fixture(name="query_agent")
def query_agent_fixture(
    mock_query_agent: AsyncMockType, mocker: MockerFixture
) -> AsyncMockType:
    """Let the agent answer the turn, with the usage the provider reports for it."""
    set_query_agent_run(
        mock_query_agent, mocker, input_tokens=TURN_INPUT, output_tokens=TURN_OUTPUT
    )
    return mock_query_agent


async def _query(scene: Scene) -> Any:
    """Send the new query on the stored conversation."""
    return await query_endpoint_handler(
        request=scene.request,
        query_request=QueryRequest(query=NEW_QUERY, conversation_id=EXISTING_CONV_ID),
        auth=scene.auth,
        mcp_headers={},
    )


@pytest.mark.usefixtures("query_agent")
class TestQueryTokenUsage:
    """Token counts and quota on /v1/query."""

    @pytest.mark.asyncio
    async def test_turn_that_summarizes_pays_for_the_summarization(
        self, scene: Scene
    ) -> None:
        """The counts of the turn include the summarization call, and so does the quota."""
        await scene.holds(_long_conversation())
        added = _metrics_added(ENDPOINT_PATH_QUERY)

        response = await _query(scene)

        scene.summarized_once()
        assert response.context_status == "summarized"
        assert response.input_tokens == TURN_INPUT + SUMMARY_INPUT
        assert response.output_tokens == TURN_OUTPUT + SUMMARY_OUTPUT
        assert response.available_quotas == scene.quotas(TURN + SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY
        assert added() == (
            TURN_INPUT + SUMMARY_INPUT,
            TURN_OUTPUT + SUMMARY_OUTPUT,
            2,
        )

    @pytest.mark.asyncio
    async def test_turn_that_summarizes_and_folds_pays_for_both_calls(
        self, scene: Scene, conversation_cache: SQLiteCache
    ) -> None:
        """The summaries grow too large with the new one, so they are folded as well."""
        _store_two_summaries(conversation_cache, scene.auth[0])
        await scene.holds(
            [marker(text) for text in EARLIER_SUMMARIES] + _long_conversation()
        )
        added = _metrics_added(ENDPOINT_PATH_QUERY)

        response = await _query(scene)

        (folded,) = conversation_cache.get_summaries(
            scene.auth[0], CONV_ID_LLAMA, False
        )
        assert folded.summary_text == "all earlier turns in one summary"
        assert response.input_tokens == TURN_INPUT + SUMMARY_INPUT + FOLD_INPUT
        assert response.output_tokens == TURN_OUTPUT + SUMMARY_OUTPUT + FOLD_OUTPUT
        assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY - FOLD
        assert added()[2] == 3

    @pytest.mark.asyncio
    async def test_turn_served_from_a_summary_pays_for_itself_only(
        self, scene: Scene
    ) -> None:
        """A compacted conversation costs nothing extra while nothing is summarized."""
        await scene.holds(_compacted_conversation(), context_window=100_000)

        response = await _query(scene)

        scene.ogx.responses.create.assert_not_awaited()
        assert response.context_status == "summarized"
        assert (response.input_tokens, response.output_tokens) == (
            TURN_INPUT,
            TURN_OUTPUT,
        )
        assert scene.quota_left() == INITIAL_QUOTA - TURN

    @pytest.mark.asyncio
    async def test_turn_on_a_short_conversation_pays_for_itself_only(
        self, scene: Scene
    ) -> None:
        """A conversation that is not compacted costs what it cost before."""
        await scene.holds(
            [msg("user", "hi"), msg("assistant", "hello")], context_window=100_000
        )

        response = await _query(scene)

        scene.ogx.responses.create.assert_not_awaited()
        assert response.context_status == "full"
        assert (response.input_tokens, response.output_tokens) == (
            TURN_INPUT,
            TURN_OUTPUT,
        )
        assert scene.quota_left() == INITIAL_QUOTA - TURN

    @pytest.mark.asyncio
    async def test_blocked_turn_that_summarized_pays_for_the_summarization(
        self, scene: Scene, query_agent: AsyncMockType, mocker: MockerFixture
    ) -> None:
        """Compaction runs before the model call, so its call is made and billed."""
        await scene.holds(_long_conversation())
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        response = await _query(scene)

        query_agent.run.assert_not_awaited()
        assert (response.input_tokens, response.output_tokens) == (
            SUMMARY_INPUT,
            SUMMARY_OUTPUT,
        )
        assert response.available_quotas == scene.quotas(SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY

    @pytest.mark.asyncio
    async def test_failed_turn_that_summarized_pays_for_the_summarization(
        self, scene: Scene, query_agent: AsyncMockType
    ) -> None:
        """The summary is made and kept before the model call that then fails."""
        await scene.holds(_long_conversation())
        query_agent.run.side_effect = RuntimeError("the model is down")

        with pytest.raises(HTTPException):
            await _query(scene)

        scene.summarized_once()
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY


# ==========================================
# /v1/streaming_query
# ==========================================


@pytest.fixture(name="streaming_agent")
def streaming_agent_fixture(
    mock_streaming_query_agent: AsyncMockType, mocker: MockerFixture
) -> AsyncMockType:
    """Let the agent answer the turn, with the usage the provider reports for it."""
    set_streaming_query_agent_run(
        mock_streaming_query_agent,
        mocker,
        input_tokens=TURN_INPUT,
        output_tokens=TURN_OUTPUT,
    )
    return mock_streaming_query_agent


async def _streaming_query(scene: Scene) -> Any:
    """Send the new query on the stored conversation, to be answered in a stream."""
    return await streaming_query_endpoint_handler(
        request=scene.request,
        query_request=QueryRequest(query=NEW_QUERY, conversation_id=EXISTING_CONV_ID),
        auth=scene.auth,
        mcp_headers={},
    )


def _only(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the one event of the given name in a stream."""
    (event,) = [event for event in events if event.get("event") == name]
    return event


class TestStreamingQueryTokenUsage:
    """Token counts and quota on /v1/streaming_query."""

    @pytest.mark.asyncio
    async def test_turn_that_summarizes_pays_for_the_summarization(
        self, scene: Scene, streaming_agent: AsyncMockType
    ) -> None:
        """The end event reports the turn with the summarization call included."""
        _ = streaming_agent
        await scene.holds(_long_conversation())
        added = _metrics_added(ENDPOINT_PATH_STREAMING_QUERY)

        end = _only(await _drain(await _streaming_query(scene)), "end")

        assert end["data"]["context_status"] == "summarized"
        assert end["data"]["input_tokens"] == TURN_INPUT + SUMMARY_INPUT
        assert end["data"]["output_tokens"] == TURN_OUTPUT + SUMMARY_OUTPUT
        assert end["available_quotas"] == scene.quotas(TURN + SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY
        # The number of calls is left out: this endpoint counts the call of
        # the turn twice, with or without compaction.
        assert added()[:2] == (
            TURN_INPUT + SUMMARY_INPUT,
            TURN_OUTPUT + SUMMARY_OUTPUT,
        )

    @pytest.mark.asyncio
    async def test_blocked_stream_that_summarized_pays_for_the_summarization(
        self, scene: Scene, streaming_agent: AsyncMockType, mocker: MockerFixture
    ) -> None:
        """Compaction runs before the model call, so its call is made and billed."""
        await scene.holds(_long_conversation())
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        end = _only(await _drain(await _streaming_query(scene)), "end")

        streaming_agent.run_stream_events.assert_not_called()
        assert end["data"]["input_tokens"] == SUMMARY_INPUT
        assert end["data"]["output_tokens"] == SUMMARY_OUTPUT
        assert end["available_quotas"] == scene.quotas(SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY

    @pytest.mark.asyncio
    async def test_failed_stream_that_summarized_pays_for_the_summarization(
        self, scene: Scene, streaming_agent: AsyncMockType
    ) -> None:
        """A stream that ends in an error reports no counts, and the call is charged."""
        await scene.holds(_long_conversation())
        streaming_agent.run_stream_events.side_effect = RuntimeError(
            "the model is down"
        )

        events = await _drain(await _streaming_query(scene))

        assert _only(events, "error")
        assert not [event for event in events if event.get("event") == "end"]
        scene.summarized_once()
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY

    @pytest.mark.asyncio
    async def test_interrupted_stream_that_summarized_pays_for_the_summarization(
        self, scene: Scene, streaming_agent: AsyncMockType
    ) -> None:
        """An interrupted answer is not charged; the summary made before it is."""
        await scene.holds(_long_conversation())
        streaming_agent.run_stream_events.return_value = _stream_that_stalls()

        events = await _interrupt_stream(await _streaming_query(scene), scene.auth[0])

        assert _only(events, "interrupted")
        assert not [event for event in events if event.get("event") == "end"]
        scene.summarized_once()
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY


# ==========================================
# /v1/responses
# ==========================================


@pytest.fixture(name="responses_handlers")
def responses_handlers_fixture(mocker: MockerFixture) -> None:
    """Let the real /v1/responses handlers run against the mocked OGX client."""
    original_context = ResponsesContext

    def _skip_validation(**kwargs: Any) -> ResponsesContext:
        """Build the context without validating the mocked client."""
        return original_context.model_construct(**kwargs)

    mocker.patch(
        "app.endpoints.responses.ResponsesContext", side_effect=_skip_validation
    )
    mocker.patch(
        "app.endpoints.responses.maybe_get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )


async def _respond(scene: Scene, stream: bool) -> Any:
    """Send the new input on the stored conversation."""
    return await responses_endpoint_handler(
        request=scene.request,
        responses_request=ResponsesRequest(
            input=NEW_QUERY,
            model=TEST_MODEL,
            conversation=EXISTING_CONV_ID,
            stream=stream,
            store=True,
            generate_topic_summary=False,
        ),
        auth=scene.auth,
        mcp_headers={},
    )


def _block_responses(mocker: MockerFixture) -> None:
    """Let the shield block the request."""
    mocker.patch(
        "app.endpoints.responses.run_shield_moderation_v2", return_value=_blocked()
    )


@pytest.mark.usefixtures("responses_handlers")
class TestResponsesTokenUsage:
    """Usage and quota on /v1/responses."""

    @pytest.mark.asyncio
    async def test_request_that_summarizes_pays_for_the_summarization(
        self, scene: Scene
    ) -> None:
        """The quota is charged for both calls; the usage stays as the provider reported it.

        The endpoint passes the usage object of the response through, so that
        it stays a drop-in for clients of the OpenAI Responses API.
        """
        await scene.holds(_long_conversation())
        added = _metrics_added(ENDPOINT_PATH_RESPONSES)

        response = await _respond(scene, stream=False)

        scene.summarized_once()
        assert response.usage is not None
        assert response.usage.input_tokens == TURN_INPUT
        assert response.usage.output_tokens == TURN_OUTPUT
        assert response.available_quotas == scene.quotas(TURN + SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY
        # At least, and not exactly: without a stream this endpoint records the
        # tokens of the answer twice, with or without compaction. What the
        # summarization adds is pinned by the failed request below.
        assert added()[0] >= TURN_INPUT + SUMMARY_INPUT

    @pytest.mark.asyncio
    async def test_stream_that_summarizes_pays_for_the_summarization(
        self, scene: Scene
    ) -> None:
        """The terminal event reports the quota left after both calls."""
        await scene.holds(_long_conversation())
        added = _metrics_added(ENDPOINT_PATH_RESPONSES)

        events = await _drain(await _respond(scene, stream=True))

        (completed,) = [e for e in events if e.get("type") == "response.completed"]
        assert completed["response"]["usage"]["input_tokens"] == TURN_INPUT
        assert completed["response"]["usage"]["output_tokens"] == TURN_OUTPUT
        assert completed["response"]["available_quotas"] == scene.quotas(TURN + SUMMARY)
        assert scene.quota_left() == INITIAL_QUOTA - TURN - SUMMARY
        assert added() == (
            TURN_INPUT + SUMMARY_INPUT,
            TURN_OUTPUT + SUMMARY_OUTPUT,
            2,
        )

    @pytest.mark.asyncio
    async def test_failed_request_that_summarized_pays_for_the_summarization(
        self, scene: Scene, mocker: MockerFixture
    ) -> None:
        """The summary is made and kept before the model call that then fails."""
        await scene.holds(_long_conversation())
        _answer_like_ogx(
            scene.ogx, mocker, turn_error=RuntimeError("the model is down")
        )
        added = _metrics_added(ENDPOINT_PATH_RESPONSES)

        with pytest.raises(RuntimeError, match="the model is down"):
            await _respond(scene, stream=False)

        scene.summarized_once()
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY
        assert added() == (SUMMARY_INPUT, SUMMARY_OUTPUT, 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    async def test_blocked_request_that_summarized_pays_for_the_summarization(
        self, stream: bool, scene: Scene, mocker: MockerFixture
    ) -> None:
        """Compaction runs before the model call, so its call is made and billed."""
        await scene.holds(_long_conversation())
        _block_responses(mocker)

        response = await _respond(scene, stream)
        if stream:
            await _drain(response)

        scene.summarized_once()
        assert scene.quota_left() == INITIAL_QUOTA - SUMMARY

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    async def test_blocked_request_that_did_not_summarize_pays_nothing(
        self, stream: bool, scene: Scene, mocker: MockerFixture
    ) -> None:
        """A blocked request made no LLM call at all, as before."""
        await scene.holds(_compacted_conversation(), context_window=100_000)
        _block_responses(mocker)

        response = await _respond(scene, stream)
        if stream:
            await _drain(response)

        assert scene.quota_left() == INITIAL_QUOTA


# ==========================================
# /a2a
# ==========================================


async def _send_a2a_message(scene: Scene, mocker: MockerFixture) -> None:
    """Send the new query to the A2A endpoint, on the stored conversation."""
    mocker.patch(
        "app.endpoints.a2a.get_lightspeed_agent_card",
        return_value=FAKE_AGENT_CARD,
    )

    async def _prepare(
        client: Any, query_request: Any, *args: Any, **kwargs: Any
    ) -> ResponsesApiParams:
        """Return params that carry the query as it arrived."""
        _ = client, args, kwargs
        return ResponsesApiParams(
            input=query_request.query,
            model=TEST_MODEL,
            conversation=CONV_ID_LLAMA,
            store=True,
            stream=True,
        )

    mocker.patch("app.endpoints.a2a.prepare_responses_params", side_effect=_prepare)
    mocker.patch("app.endpoints.a2a.build_agent", return_value=mock_a2a_agent(mocker))
    await handle_a2a_jsonrpc_post(
        request=build_a2a_request(NEW_QUERY), auth=scene.auth, mcp_headers={}
    )


class TestA2ATokenUsage:
    """The A2A endpoint has no quota; the summarization call shows in the metrics."""

    @pytest.mark.asyncio
    async def test_summarization_is_recorded_and_charged_to_nobody(
        self, scene: Scene, mocker: MockerFixture
    ) -> None:
        """The tokens of the summarization call are counted under the endpoint."""
        await scene.holds(_long_conversation())
        # Reading the quota creates the user's row; a charge would change it.
        assert scene.quota_left() == INITIAL_QUOTA
        added = _metrics_added(ENDPOINT_PATH_A2A)

        await _send_a2a_message(scene, mocker)

        scene.summarized_once()
        assert added() == (SUMMARY_INPUT, SUMMARY_OUTPUT, 1)
        assert scene.quota_left() == INITIAL_QUOTA

    @pytest.mark.asyncio
    async def test_message_served_from_a_summary_records_nothing(
        self, scene: Scene, mocker: MockerFixture
    ) -> None:
        """Without a summarization call there is nothing to count."""
        await scene.holds(_compacted_conversation(), context_window=100_000)
        added = _metrics_added(ENDPOINT_PATH_A2A)

        await _send_a2a_message(scene, mocker)

        scene.ogx.responses.create.assert_not_awaited()
        assert added() == (0, 0, 0)
