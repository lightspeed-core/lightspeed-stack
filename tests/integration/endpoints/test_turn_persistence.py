"""Integration tests for the turns lightspeed-stack stores itself (LCORE-3908).

OGX stores a turn only when it is handed the ``conversation`` parameter and
runs the inference. In every other case lightspeed-stack appends the turn to
the conversation: a conversation served in compacted mode, a request a shield
blocked, a stream the client interrupted, a continuation from
``previous_response_id``.

LCORE-3883 showed what happens when that write goes missing: nothing fails,
the conversation just stops growing. So every test here asserts on what the
conversation store holds after the request, item by item. That catches a write
that is missing, a write that happens twice, and a write of the wrong input.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=too-many-lines

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client import ApiException
from ogx_client.models.open_ai_response_object import OpenAIResponseObject
from ogx_client.models.open_ai_response_object_stream_response_completed import (
    OpenAIResponseObjectStreamResponseCompleted,
)
from ogx_client.models.open_ai_response_object_stream_response_created import (
    OpenAIResponseObjectStreamResponseCreated,
)
from ogx_client.models.open_ai_response_object_stream_response_failed import (
    OpenAIResponseObjectStreamResponseFailed,
)
from ogx_client.models.open_ai_response_object_stream_response_incomplete import (
    OpenAIResponseObjectStreamResponseIncomplete,
)
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.messages import ModelResponse, PartStartEvent, TextPart
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.a2a import handle_a2a_jsonrpc_post
from app.endpoints.query import query_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest, ResponsesRequest
from models.common.moderation import ShieldModerationBlocked
from models.common.responses.contexts import ResponsesContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import TurnSummary
from models.database.conversations import UserConversation, UserTurn
from tests.integration.conftest import (
    InMemoryConversationStore,
    create_agent_run_result,
    make_openai_response_object,
    mock_agent_run_stream,
)
from tests.integration.endpoints._compaction_helpers import (
    CONV_ID_LLAMA,
    DEFAULT_MODEL_RESPONSE,
    EXISTING_CONV_ID,
    FAKE_AGENT_CARD,
    TEST_MODEL,
    build_a2a_request,
    collect_items,
    create_existing_conversation,
    enable_compaction,
    marker,
    mock_a2a_agent,
    msg,
)
from utils.pending_turn import TurnNotStoredError
from utils.stream_interrupts import (
    CancelStreamResult,
    build_interrupted_response,
    get_stream_interrupt_registry,
)
from utils.token_estimator import extract_message_text

NEW_QUERY = "What else can you help with?"
REFUSAL = "Content blocked by safety shield"
PARTIAL_ANSWER = "Ansible is"
PREVIOUS_RESPONSE_ID = "resp_previous_turn"
LARGE_WINDOW = 100_000
"""Context window no test conversation comes near, so nothing is summarized."""


def _compacted_conversation() -> list[OpenAIResponseMessage]:
    """Return a stored conversation that has been compacted before.

    It holds a summary marker, which is what puts every later request on it in
    compacted mode: the ``conversation`` parameter is dropped and OGX does not
    store the turn.
    """
    return [
        msg("user", "earlier question"),
        msg("assistant", "earlier answer"),
        marker("summary of the earlier turn"),
    ]


def _plain_conversation() -> list[OpenAIResponseMessage]:
    """Return a stored conversation that has never been compacted."""
    return [
        msg("user", "earlier question"),
        msg("assistant", "earlier answer"),
    ]


def _turn(answer: str, query: str = NEW_QUERY) -> list[OpenAIResponseMessage]:
    """Return the two items one stored turn consists of."""
    return [msg("user", query), msg("assistant", answer)]


async def _seed(
    test_config: AppConfig,
    store: InMemoryConversationStore,
    items: list[OpenAIResponseMessage],
) -> None:
    """Enable compaction and store the conversation the request continues."""
    enable_compaction(test_config, context_window=LARGE_WINDOW)
    await store.create(conversation_id=CONV_ID_LLAMA, items=items)


def _role_and_text(item: Any) -> tuple[str, str]:
    """Reduce a stored item to who said it and what was said.

    The text is compared, not the content object: OGX returns the text of an
    answer as a list of content parts, a request carries it as a string.
    """
    return str(getattr(item, "role", "")), extract_message_text(item)


async def _assert_stored(
    store: InMemoryConversationStore, expected: list[OpenAIResponseMessage]
) -> None:
    """Assert the conversation holds exactly the expected items, in order."""
    stored = await collect_items(store, CONV_ID_LLAMA)
    assert [_role_and_text(item) for item in stored] == [
        _role_and_text(item) for item in expected
    ]


def _blocked() -> ShieldModerationBlocked:
    """Return the verdict of a shield that blocked the request."""
    return ShieldModerationBlocked(message=REFUSAL, moderation_id="modr_blocked_1")


def _agent_answer(agent: Any, text: str = DEFAULT_MODEL_RESPONSE) -> None:
    """Set the output items the agent's model captured for the turn."""
    agent.model.last_output_items = [
        OpenAIResponseMessage(role="assistant", content=text)
    ]


def _run_cut_short(mocker: MockerFixture) -> Any:
    """Return the result of an agent run the model ended for length, not success."""
    return create_agent_run_result(
        mocker,
        model_response=ModelResponse(
            parts=[TextPart(PARTIAL_ANSWER)],
            finish_reason="length",
            provider_response_id="response-cut-short",
        ),
    )


async def _drain(response: Any) -> list[str]:
    """Read a streaming response to its end and return the chunks."""
    assert isinstance(response, StreamingResponse)
    return [str(chunk) async for chunk in response.body_iterator]


# ==========================================
# /v1/query
# ==========================================


async def _send_query(test_request: Request, test_auth: AuthTuple) -> Any:
    """Send the new query on the stored conversation."""
    return await query_endpoint_handler(
        request=test_request,
        query_request=QueryRequest(query=NEW_QUERY, conversation_id=EXISTING_CONV_ID),
        auth=test_auth,
        mcp_headers={},
    )


class TestQueryTurnPersistence:
    """What /v1/query leaves in the conversation."""

    @pytest.mark.asyncio
    async def test_completed_turn_in_compacted_mode_is_stored_once(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """The conversation gains the query as it arrived and the answer, once."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_query_agent)

        await _send_query(test_request, test_auth)

        params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert params.omit_conversation is True
        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation() + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    async def test_two_requests_store_two_turns(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """Each request adds its own turn and nothing else."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_query_agent)

        await _send_query(test_request, test_auth)
        await _send_query(test_request, test_auth)

        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation()
            + _turn(DEFAULT_MODEL_RESPONSE)
            + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    async def test_completed_turn_outside_compacted_mode_is_left_to_ogx(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """With the conversation parameter sent, OGX stores the turn, not we."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        _agent_answer(mock_query_agent)

        await _send_query(test_request, test_auth)

        params = mock_query_agent.build_agent_mock.call_args[0][1]
        assert params.omit_conversation is False
        await _assert_stored(mock_conversation_store, _plain_conversation())

    @pytest.mark.asyncio
    async def test_blocked_turn_outside_compacted_mode_is_stored_once(
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
        """A blocked request never reaches OGX, so the refusal turn is ours."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        await _send_query(test_request, test_auth)

        mock_query_agent.run.assert_not_awaited()
        await _assert_stored(
            mock_conversation_store, _plain_conversation() + _turn(REFUSAL)
        )

    @pytest.mark.asyncio
    async def test_blocked_turn_in_compacted_mode_is_not_stored(
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
        """A blocked request on a compacted conversation leaves no turn behind.

        This is the behaviour as it is, recorded so that a change to it is a
        decision: /v1/streaming_query and /v1/responses do store this turn,
        and LCORE-3788 settles what all of them should do.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        await _send_query(test_request, test_auth)

        mock_query_agent.run.assert_not_awaited()
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    async def test_failed_turn_in_compacted_mode_is_not_stored(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """A request that fails in the model call stores nothing."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_query_agent)
        mock_query_agent.run.side_effect = RuntimeError("the model call failed")

        with pytest.raises(HTTPException):
            await _send_query(test_request, test_auth)

        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    async def test_turn_the_model_cut_short_is_not_stored(
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
        """A run that did not finish with success is an error here, and stores nothing.

        /v1/streaming_query treats the same run differently: see
        ``test_turn_the_model_cut_short_is_stored_once`` there.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_query_agent)
        mock_query_agent.run.return_value = _run_cut_short(mocker)

        with pytest.raises(HTTPException):
            await _send_query(test_request, test_auth)

        await _assert_stored(mock_conversation_store, _compacted_conversation())


# ==========================================
# /v1/streaming_query
# ==========================================


def _stream_that_stalls(release: asyncio.Event) -> Any:
    """Build an agent stream that sends one token and then waits.

    The wait ends only when the consuming task is cancelled, which is what an
    interrupt does.
    """

    async def _events() -> AsyncIterator[Any]:
        yield PartStartEvent(index=0, part=TextPart(content=PARTIAL_ANSWER))
        await release.wait()

    class _RunStreamCtx:
        """Async context manager matching ``agent.run_stream_events``."""

        async def __aenter__(self) -> AsyncIterator[Any]:
            return _events()

        async def __aexit__(self, *_args: object) -> None:
            return None

    return _RunStreamCtx()


def _request_id_of(chunks: list[str]) -> str:
    """Return the request id the stream announced in its start event."""
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event.get("event") == "start":
                return event["data"]["request_id"]
    raise AssertionError(f"no start event in {chunks!r}")


async def _send_streaming_query(test_request: Request, test_auth: AuthTuple) -> Any:
    """Send the new query on the stored conversation."""
    return await streaming_query_endpoint_handler(
        request=test_request,
        query_request=QueryRequest(query=NEW_QUERY, conversation_id=EXISTING_CONV_ID),
        auth=test_auth,
        mcp_headers={},
    )


async def _interrupt_stream(test_request: Request, test_auth: AuthTuple) -> list[str]:
    """Start a stream, interrupt it after its first token, read it to the end."""
    response = await _send_streaming_query(test_request, test_auth)
    assert isinstance(response, StreamingResponse)
    chunks: list[str] = []
    first_token = asyncio.Event()

    async def _consume() -> None:
        async for chunk in response.body_iterator:
            chunks.append(str(chunk))
            if '"event": "token"' in str(chunk):
                first_token.set()

    consumer = asyncio.create_task(_consume())
    await asyncio.wait_for(first_token.wait(), timeout=5)
    result = get_stream_interrupt_registry().cancel_stream(
        _request_id_of(chunks), test_auth[0]
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
    return chunks


class TestStreamingQueryTurnPersistence:
    """What /v1/streaming_query leaves in the conversation."""

    @pytest.mark.asyncio
    async def test_completed_turn_in_compacted_mode_is_stored_once(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """The conversation gains the query as it arrived and the answer, once."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent)

        await _drain(await _send_streaming_query(test_request, test_auth))

        params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert params.omit_conversation is True
        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation() + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    async def test_completed_turn_outside_compacted_mode_is_left_to_ogx(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """With the conversation parameter sent, OGX stores the turn, not we."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        _agent_answer(mock_streaming_query_agent)

        await _drain(await _send_streaming_query(test_request, test_auth))

        params = mock_streaming_query_agent.build_agent_mock.call_args[0][1]
        assert params.omit_conversation is False
        await _assert_stored(mock_conversation_store, _plain_conversation())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stored_conversation",
        [_compacted_conversation, _plain_conversation],
        ids=["compacted", "not-compacted"],
    )
    async def test_blocked_turn_is_stored_once(
        self,
        stored_conversation: Any,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The refusal turn is stored once, whichever mode the conversation is in.

        Outside compacted mode it is written before the stream starts, in
        compacted mode when the stream ends. Neither may also do the other's.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, stored_conversation())
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        await _drain(await _send_streaming_query(test_request, test_auth))

        mock_streaming_query_agent.build_agent_mock.assert_not_called()
        await _assert_stored(
            mock_conversation_store, stored_conversation() + _turn(REFUSAL)
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stored_conversation",
        [_compacted_conversation, _plain_conversation],
        ids=["compacted", "not-compacted"],
    )
    async def test_interrupted_turn_is_stored_once(
        self,
        stored_conversation: Any,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """An interrupt stores what was received so far, once.

        Two things react to an interrupt: the generator, where the
        cancellation lands, and the callback the interrupt endpoint schedules.
        Both want to store the turn; only one of them may.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, stored_conversation())
        _agent_answer(mock_streaming_query_agent)
        mock_streaming_query_agent.run_stream_events.return_value = _stream_that_stalls(
            asyncio.Event()
        )

        chunks = await _interrupt_stream(test_request, test_auth)

        assert any('"event": "interrupted"' in chunk for chunk in chunks)
        interrupted_answer, _ = build_interrupted_response([PARTIAL_ANSWER])
        await _assert_stored(
            mock_conversation_store,
            stored_conversation() + _turn(interrupted_answer),
        )
        recorded_turns = (
            patch_db_session.query(UserTurn)
            .filter_by(conversation_id=EXISTING_CONV_ID)
            .count()
        )
        assert recorded_turns == 1

    @pytest.mark.asyncio
    async def test_turn_the_model_cut_short_is_stored_once(
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
        """A run that did not finish with success still ran to its end, and is stored.

        The stream reports the error as an event and ends normally, so the
        turn is stored with the output received. /v1/query stores nothing
        for the same run.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent, PARTIAL_ANSWER)
        mock_streaming_query_agent.run_stream_events.return_value = (
            mock_agent_run_stream(
                [
                    PartStartEvent(index=0, part=TextPart(content=PARTIAL_ANSWER)),
                    AgentRunResultEvent(result=_run_cut_short(mocker)),
                ]
            )
        )

        chunks = await _drain(await _send_streaming_query(test_request, test_auth))

        assert any('"event": "error"' in chunk for chunk in chunks)
        await _assert_stored(
            mock_conversation_store, _compacted_conversation() + _turn(PARTIAL_ANSWER)
        )

    @pytest.mark.asyncio
    async def test_stream_the_client_stopped_reading_stores_nothing(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_streaming_query_agent: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """A stream closed before its end leaves no turn behind.

        The turn is stored after the last event of the stream. A client that
        goes away before that closes the generator, and the write never runs.
        This is the behaviour as it is, recorded here, not a goal.
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent)

        response = await _send_streaming_query(test_request, test_auth)
        assert isinstance(response, StreamingResponse)
        body: Any = response.body_iterator
        async for chunk in body:
            if '"event": "token"' in str(chunk):
                break
        await body.aclose()

        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    async def test_blocked_turn_is_not_stored_again_by_an_interrupt(
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
        """A refusal that was stored is the turn; an interrupt adds no second one.

        Outside compacted mode the refusal turn is stored before the stream
        starts. An interrupt while the refusal is streamed used to store the
        turn again, with the interruption notice for an answer. The turn has
        one owner now, so it is stored once; the interrupt still records the
        turn in the database, as before.
        """
        _ = mock_ogx_client
        _ = mock_streaming_query_agent
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )

        async def _refusal_that_stalls(*_args: Any, **_kwargs: Any) -> Any:
            yield 'data: {"event": "token", "data": {"id": 0, "token": "Content"}}\n\n'
            await asyncio.Event().wait()

        mocker.patch(
            "utils.agents.streaming.shield_violation_generator",
            side_effect=_refusal_that_stalls,
        )

        chunks = await _interrupt_stream(test_request, test_auth)

        assert any('"event": "interrupted"' in chunk for chunk in chunks)
        await _assert_stored(
            mock_conversation_store, _plain_conversation() + _turn(REFUSAL)
        )
        recorded_turns = (
            patch_db_session.query(UserTurn)
            .filter_by(conversation_id=EXISTING_CONV_ID)
            .count()
        )
        assert recorded_turns == 1


# ==========================================
# /v1/responses
# ==========================================


def _link_previous_response(db_session: Session) -> None:
    """Make the stored conversation end with a response a request can continue."""
    conversation = (
        db_session.query(UserConversation).filter_by(id=EXISTING_CONV_ID).one()
    )
    conversation.last_response_id = PREVIOUS_RESPONSE_ID
    now = datetime.now(UTC)
    db_session.add(
        UserTurn(
            conversation_id=EXISTING_CONV_ID,
            turn_number=1,
            started_at=now,
            completed_at=now,
            provider="test-provider",
            model="test-model",
            response_id=PREVIOUS_RESPONSE_ID,
        )
    )
    db_session.commit()


def _response_that_ended_with(terminal_event: Optional[str]) -> Any:
    """Build the response object a stream carries in its terminal event.

    A completed response holds the answer, an incomplete one the part of it
    that was produced, a failed one an error and no output.
    """
    if terminal_event == "response.failed":
        failed = OpenAIResponseObject.from_dict(
            {
                "id": "response-failed",
                "object": "response",
                "created_at": 1_700_000_000,
                "status": "failed",
                "model": TEST_MODEL,
                "store": False,
                "output": [],
                "error": {"code": "server_error", "message": "the model failed"},
            }
        )
        assert failed is not None
        return failed
    if terminal_event == "response.incomplete":
        return make_openai_response_object(content=PARTIAL_ANSWER)
    return make_openai_response_object(content=DEFAULT_MODEL_RESPONSE)


TERMINAL_EVENTS: dict[str, Any] = {
    "response.completed": OpenAIResponseObjectStreamResponseCompleted,
    "response.incomplete": OpenAIResponseObjectStreamResponseIncomplete,
    "response.failed": OpenAIResponseObjectStreamResponseFailed,
}


async def _one_chunk_stream(
    response_object: Any,
    terminal_event: Optional[str] = "response.completed",
) -> AsyncIterator[Any]:
    """Yield the events of a streamed response, ending with the terminal one.

    Without a terminal event the stream consists of the opening event alone,
    which is what a response that never finished looks like.
    """
    yield OpenAIResponseObjectStreamResponseCreated(
        response=response_object,
        sequence_number=0,
        type="response.created",
    )
    if terminal_event is not None:
        yield TERMINAL_EVENTS[terminal_event](
            response=response_object,
            sequence_number=1,
            type=terminal_event,
        )


@pytest.fixture(name="ogx_stream")
def ogx_stream_fixture(
    mock_ogx_client: AsyncMockType,
    mocker: MockerFixture,
) -> SimpleNamespace:
    """Let the real handlers run against the mocked OGX client.

    Returns:
        The settings of the mocked stream; ``terminal_event`` is the event
        a streamed response ends with, ``None`` for a stream without one.
    """
    ogx_stream = SimpleNamespace(terminal_event="response.completed")
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

    async def _create(**kwargs: Any) -> Any:
        """Answer like OGX: a response object, or a stream of events."""
        if kwargs.get("stream"):
            return _one_chunk_stream(
                _response_that_ended_with(ogx_stream.terminal_event),
                ogx_stream.terminal_event,
            )
        return make_openai_response_object(content=DEFAULT_MODEL_RESPONSE)

    mock_ogx_client.responses.create = mocker.AsyncMock(side_effect=_create)
    return ogx_stream


async def _send_response_request(
    test_request: Request,
    test_auth: AuthTuple,
    stream: bool,
    store: bool = True,
    previous_response_id: Optional[str] = None,
) -> Any:
    """Send the new input on the stored conversation and read the answer."""
    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=ResponsesRequest(
            input=NEW_QUERY,
            model=TEST_MODEL,
            conversation=None if previous_response_id else EXISTING_CONV_ID,
            previous_response_id=previous_response_id,
            stream=stream,
            store=store,
            generate_topic_summary=False,
        ),
        auth=test_auth,
        mcp_headers={},
    )
    if stream:
        return await _drain(response)
    return response


@pytest.mark.usefixtures("ogx_stream")
class TestResponsesTurnPersistence:
    """What /v1/responses leaves in the conversation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    async def test_completed_turn_in_compacted_mode_is_stored_once(
        self,
        stream: bool,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """The conversation gains the input as it arrived and the output, once."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())

        await _send_response_request(test_request, test_auth, stream)

        sent = mock_ogx_client.responses.create.await_args.kwargs
        assert "conversation" not in sent
        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation() + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    async def test_completed_turn_outside_compacted_mode_is_left_to_ogx(
        self,
        stream: bool,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """With the conversation parameter sent, OGX stores the turn, not we."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())

        await _send_response_request(test_request, test_auth, stream)

        sent = mock_ogx_client.responses.create.await_args.kwargs
        assert sent["conversation"] == CONV_ID_LLAMA
        await _assert_stored(mock_conversation_store, _plain_conversation())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    @pytest.mark.parametrize(
        "stored_conversation",
        [_compacted_conversation, _plain_conversation],
        ids=["compacted", "not-compacted"],
    )
    async def test_blocked_turn_is_stored_once(
        self,
        stored_conversation: Any,
        stream: bool,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The refusal turn is stored once, against the input as it arrived."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, stored_conversation())
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation_v2",
            return_value=_blocked(),
        )

        await _send_response_request(test_request, test_auth, stream)

        mock_ogx_client.responses.create.assert_not_awaited()
        await _assert_stored(
            mock_conversation_store, stored_conversation() + _turn(REFUSAL)
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    @pytest.mark.parametrize(
        "stored_conversation",
        [_compacted_conversation, _plain_conversation],
        ids=["compacted", "not-compacted"],
    )
    async def test_continuation_from_a_previous_response_is_stored_once(
        self,
        stored_conversation: Any,
        stream: bool,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """OGX does not store a turn that continues from a previous response.

        Such a request is never compacted, so the turn is stored against its
        input whichever state the conversation is in.
        """
        create_existing_conversation(patch_db_session, test_auth[0])
        _link_previous_response(patch_db_session)
        await _seed(test_config, mock_conversation_store, stored_conversation())

        await _send_response_request(
            test_request, test_auth, stream, previous_response_id=PREVIOUS_RESPONSE_ID
        )

        sent = mock_ogx_client.responses.create.await_args.kwargs
        assert sent["previous_response_id"] == PREVIOUS_RESPONSE_ID
        assert "conversation" not in sent
        await _assert_stored(
            mock_conversation_store,
            stored_conversation() + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("terminal_event", "stored_output"),
        [
            ("response.incomplete", [msg("assistant", PARTIAL_ANSWER)]),
            ("response.failed", []),
        ],
        ids=["incomplete", "failed"],
    )
    async def test_stream_that_did_not_complete_is_stored_once(
        self,
        terminal_event: str,
        stored_output: list[OpenAIResponseMessage],
        test_config: AppConfig,
        ogx_stream: SimpleNamespace,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """A stream that ends incomplete or failed is stored with the output it has.

        That is the part of the answer an incomplete response produced, and
        nothing for a failed one: the conversation gains the input alone.
        """
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        ogx_stream.terminal_event = terminal_event

        chunks = await _send_response_request(test_request, test_auth, stream=True)

        assert any(f"event: {terminal_event}" in chunk for chunk in chunks)
        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation() + [msg("user", NEW_QUERY)] + stored_output,
        )

    @pytest.mark.asyncio
    async def test_stream_without_a_terminal_event_stores_nothing(
        self,
        test_config: AppConfig,
        ogx_stream: SimpleNamespace,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
    ) -> None:
        """A stream that ends without a final response has no output to store."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        ogx_stream.terminal_event = None

        chunks = await _send_response_request(test_request, test_auth, stream=True)

        assert chunks[-1] == "data: [DONE]\n\n"
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    @pytest.mark.parametrize("turn_of_ours", ["blocked", "continuation"])
    async def test_turn_is_not_stored_when_the_request_says_so(
        self,
        turn_of_ours: str,
        stream: bool,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """A request with ``store`` off leaves the conversation as it was.

        Both turns would be ours to store: a request a shield blocked, and a
        continuation from a previous response. (A request with ``store`` off
        is never compacted, so there is no third case.)
        """
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        previous_response_id = None
        if turn_of_ours == "blocked":
            mocker.patch(
                "app.endpoints.responses.run_shield_moderation_v2",
                return_value=_blocked(),
            )
        else:
            _link_previous_response(patch_db_session)
            previous_response_id = PREVIOUS_RESPONSE_ID

        await _send_response_request(
            test_request,
            test_auth,
            stream,
            store=False,
            previous_response_id=previous_response_id,
        )

        await _assert_stored(mock_conversation_store, _plain_conversation())


# ==========================================
# /a2a
# ==========================================


def _put_a2a_on_the_conversation(mocker: MockerFixture) -> Any:
    """Put the A2A endpoint on the stored conversation with a mocked agent."""
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
    agent = mock_a2a_agent(mocker)
    mocker.patch("app.endpoints.a2a.build_agent", return_value=agent)
    return agent


class TestA2ATurnPersistence:
    """What the A2A endpoint leaves in the conversation."""

    @pytest.mark.asyncio
    async def test_completed_turn_in_compacted_mode_is_stored_once(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """The conversation gains the message as it arrived and the answer, once."""
        _ = mock_ogx_client
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _put_a2a_on_the_conversation(mocker)

        await handle_a2a_jsonrpc_post(
            request=build_a2a_request(NEW_QUERY), auth=test_auth, mcp_headers={}
        )

        await _assert_stored(
            mock_conversation_store,
            _compacted_conversation() + _turn(DEFAULT_MODEL_RESPONSE),
        )

    @pytest.mark.asyncio
    async def test_completed_turn_outside_compacted_mode_is_left_to_ogx(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """With the conversation parameter sent, OGX stores the turn, not we."""
        _ = mock_ogx_client
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        _put_a2a_on_the_conversation(mocker)

        await handle_a2a_jsonrpc_post(
            request=build_a2a_request(NEW_QUERY), auth=test_auth, mcp_headers={}
        )

        await _assert_stored(mock_conversation_store, _plain_conversation())

    @pytest.mark.asyncio
    async def test_failed_turn_in_compacted_mode_is_not_stored(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """A turn that fails in the model call stores nothing."""
        _ = mock_ogx_client
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        agent = _put_a2a_on_the_conversation(mocker)
        agent.run_stream_events.side_effect = RuntimeError("the model call failed")

        await handle_a2a_jsonrpc_post(
            request=build_a2a_request(NEW_QUERY), auth=test_auth, mcp_headers={}
        )

        await _assert_stored(mock_conversation_store, _compacted_conversation())


# ==========================================
# A write that fails
# ==========================================


def _break_the_store(mock_ogx_client: AsyncMockType, mocker: MockerFixture) -> None:
    """Make every write to the conversation fail; reads keep working."""
    mock_ogx_client.items.create = mocker.AsyncMock(
        side_effect=ApiException(status=500, reason="the store is down")
    )


class TestFailedWrite:
    """What a failed write does to the request, which differs by endpoint.

    /v1/query and /v1/responses answer with an error: the turn is part of
    what they deliver. The streaming paths and A2A have delivered the answer
    by the time they store the turn, so they log the failure and go on.
    In every case the write is tried once.
    """

    @pytest.mark.asyncio
    async def test_query_fails(
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
        """/v1/query answers with an error when the turn cannot be stored."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_query_agent)
        _break_the_store(mock_ogx_client, mocker)

        with pytest.raises(HTTPException) as error:
            await _send_query(test_request, test_auth)

        assert error.value.status_code == 500
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    async def test_streaming_query_delivers_the_answer(
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
        """/v1/streaming_query ends the stream normally and logs the failure."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent)
        _break_the_store(mock_ogx_client, mocker)

        chunks = await _drain(await _send_streaming_query(test_request, test_auth))

        assert any('"event": "end"' in chunk for chunk in chunks)
        assert not any('"event": "error"' in chunk for chunk in chunks)
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    async def test_blocked_streaming_query_fails_before_the_stream(
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
        """Outside compacted mode a refusal that cannot be stored is an error."""
        _ = mock_streaming_query_agent
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _plain_conversation())
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=_blocked()),
        )
        _break_the_store(mock_ogx_client, mocker)

        with pytest.raises(HTTPException) as error:
            await _send_streaming_query(test_request, test_auth)

        assert error.value.status_code == 500
        assert mock_ogx_client.items.create.await_count == 1

    @pytest.mark.asyncio
    async def test_interrupted_streaming_query_still_records_the_turn(
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
        """An interrupt logs the failed write and records the turn in the database."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent)
        mock_streaming_query_agent.run_stream_events.return_value = _stream_that_stalls(
            asyncio.Event()
        )
        _break_the_store(mock_ogx_client, mocker)

        chunks = await _interrupt_stream(test_request, test_auth)

        assert any('"event": "interrupted"' in chunk for chunk in chunks)
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())
        recorded_turns = (
            patch_db_session.query(UserTurn)
            .filter_by(conversation_id=EXISTING_CONV_ID)
            .count()
        )
        assert recorded_turns == 1

    @pytest.mark.asyncio
    async def test_a2a_delivers_the_answer(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """A2A completes the task and logs the failure."""
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _put_a2a_on_the_conversation(mocker)
        _break_the_store(mock_ogx_client, mocker)

        response = await handle_a2a_jsonrpc_post(
            request=build_a2a_request(NEW_QUERY), auth=test_auth, mcp_headers={}
        )

        assert response.status_code == 200
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("ogx_stream")
    async def test_responses_request_fails(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The request answers with an error when the turn cannot be stored."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _break_the_store(mock_ogx_client, mocker)

        with pytest.raises(HTTPException) as error:
            await _send_response_request(test_request, test_auth, stream=False)

        assert error.value.status_code == 500
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("ogx_stream")
    async def test_responses_stream_ends_before_done(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The stream has sent its terminal event and breaks off before ``[DONE]``."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _break_the_store(mock_ogx_client, mocker)

        response = await responses_endpoint_handler(
            request=test_request,
            responses_request=ResponsesRequest(
                input=NEW_QUERY,
                model=TEST_MODEL,
                conversation=EXISTING_CONV_ID,
                stream=True,
                store=True,
                generate_topic_summary=False,
            ),
            auth=test_auth,
            mcp_headers={},
        )
        assert isinstance(response, StreamingResponse)
        chunks: list[str] = []
        with pytest.raises(HTTPException) as error:
            async for chunk in response.body_iterator:
                chunks.append(str(chunk))

        assert error.value.status_code == 500
        assert any("event: response.completed" in chunk for chunk in chunks)
        assert "data: [DONE]\n\n" not in chunks
        assert mock_ogx_client.items.create.await_count == 1
        await _assert_stored(mock_conversation_store, _compacted_conversation())


# ==========================================
# A turn nobody stored
# ==========================================


class TestTurnNobodyStored:
    """What happens when an endpoint is changed and stops storing the turn.

    This is LCORE-3883 replayed: the step that stores the turn is taken out of
    each endpoint, the way a cleanup would. The request then does not end as
    if nothing had happened.
    """

    @pytest.mark.asyncio
    async def test_query_fails(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The scope around the model call reports the turn nobody stored."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
            new=mocker.AsyncMock(return_value=TurnSummary(llm_response="An answer")),
        )

        with pytest.raises(TurnNotStoredError, match=CONV_ID_LLAMA):
            await _send_query(test_request, test_auth)

    @pytest.mark.asyncio
    async def test_streaming_query_fails(
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
        """The stream breaks off before its end event."""
        _ = mock_ogx_client
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _agent_answer(mock_streaming_query_agent)
        mocker.patch(
            "utils.agents.streaming._persist_compacted_turn", new=mocker.AsyncMock()
        )

        response = await _send_streaming_query(test_request, test_auth)
        assert isinstance(response, StreamingResponse)
        chunks: list[str] = []
        with pytest.raises(TurnNotStoredError, match=CONV_ID_LLAMA):
            async for chunk in response.body_iterator:
                chunks.append(str(chunk))

        assert not any('"event": "end"' in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_a2a_fails_the_task(
        self,
        test_config: AppConfig,
        mock_ogx_client: AsyncMockType,
        mock_conversation_store: InMemoryConversationStore,
        test_auth: AuthTuple,
        mocker: MockerFixture,
    ) -> None:
        """The task ends as failed, with the reason in its status message."""
        _ = mock_ogx_client
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        _put_a2a_on_the_conversation(mocker)
        mocker.patch(
            "app.endpoints.a2a._persist_compacted_a2a_turn", new=mocker.AsyncMock()
        )

        response = await handle_a2a_jsonrpc_post(
            request=build_a2a_request(NEW_QUERY), auth=test_auth, mcp_headers={}
        )

        status = json.loads(bytes(response.body))["result"]["status"]
        assert status["state"] == "failed"
        assert CONV_ID_LLAMA in status["message"]["parts"][0]["text"]
        assert "nobody tried to store it" in status["message"]["parts"][0]["text"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("ogx_stream")
    @pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
    async def test_responses_request_fails(
        self,
        stream: bool,
        test_config: AppConfig,
        mock_conversation_store: InMemoryConversationStore,
        test_request: Request,
        test_auth: AuthTuple,
        patch_db_session: Session,
        mocker: MockerFixture,
    ) -> None:
        """The handler reports the turn nobody stored, in both modes."""
        create_existing_conversation(patch_db_session, test_auth[0])
        await _seed(test_config, mock_conversation_store, _compacted_conversation())
        mocker.patch(
            "app.endpoints.responses._append_previous_response_turn",
            new=mocker.AsyncMock(),
        )

        with pytest.raises(TurnNotStoredError, match=CONV_ID_LLAMA):
            await _send_response_request(test_request, test_auth, stream)
