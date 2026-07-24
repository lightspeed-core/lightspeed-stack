"""Integration tests for the /v1/responses endpoint.

These tests exercise the handler → DB persistence path with real configuration
and an in-memory SQLite database. The Llama Stack client is mocked (no real LLM),
but all internal subsystems (config, DB, shield moderation, conversation storage)
run with real code.
"""

from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client.types import ListModelsResponse
from ogx_client.types.model import Model
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.responses import responses_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.moderation import ShieldModerationBlocked
from models.common.responses.contexts import ResponsesContext
from models.database.conversations import UserConversation, UserTurn

MOCK_AUTH: AuthTuple = (
    "00000000-0000-0000-0000-000",
    "lightspeed-user",
    True,
    "",
)

MOCK_CONV_ID = "conv_" + "a" * 48
NORMALIZED_CONV_ID = "a" * 48

_RESPONSE_DUMP: dict[str, Any] = {
    "id": "resp_integ_test",
    "object": "response",
    "created_at": 1700000000,
    "status": "completed",
    "model": "test-provider/test-model",
    "output": [
        {
            "type": "message",
            "id": "msg-1",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "Ansible is an automation tool.",
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


def _build_mock_client(mocker: MockerFixture) -> Any:
    """Build a mock Llama Stack client for responses integration tests.

    Returns a fully-configured AsyncMock client with sensible defaults for
    responses.create, models.list, shields.list, vector_stores.list, and
    conversations.create.
    """
    mock_client = mocker.AsyncMock()

    mock_response = mocker.MagicMock()
    mock_response.id = "resp_integ_test"
    mock_output = mocker.MagicMock()
    mock_output.type = "message"
    mock_output.role = "assistant"
    mock_output.content = "Ansible is an automation tool."
    mock_output.refusal = None
    mock_response.output = [mock_output]
    mock_response.usage = mocker.MagicMock()
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5
    mock_response.status = "completed"
    mock_response.model = "test-provider/test-model"
    mock_response.model_dump.return_value = _RESPONSE_DUMP.copy()
    mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client.models.list.return_value = ListModelsResponse.model_construct(
        data=[
            Model.model_construct(
                id="test-provider/test-model",
                created=0,
                owned_by="test",
                object="model",
                custom_metadata={
                    "provider_id": "test-provider",
                    "model_type": "llm",
                },
            )
        ]
    )

    mock_client.shields.list.return_value = []

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_conv = mocker.MagicMock()
    mock_conv.id = MOCK_CONV_ID
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conv)

    return mock_client


def _patch_client_holders(mocker: MockerFixture, mock_client: Any) -> None:
    """Patch AsyncOgxClientHolder in all modules used by the responses endpoint.

    Patches three import locations (responses endpoint, utils.endpoints,
    utils.responses) and bypasses ResponsesContext Pydantic validation.
    """
    for module in (
        "app.endpoints.responses",
        "utils.endpoints",
        "utils.responses",
    ):
        holder = mocker.patch(f"{module}.AsyncOgxClientHolder")
        holder.return_value.get_client.return_value = mock_client

    original_cls = ResponsesContext

    def _skip_validation(**kwargs: Any) -> ResponsesContext:
        return original_cls.model_construct(**kwargs)

    mocker.patch(
        "app.endpoints.responses.ResponsesContext", side_effect=_skip_validation
    )


def _setup_test(mocker: MockerFixture) -> Any:
    """Set up mock client and patch all holders for a responses integration test.

    Returns:
        The mock Llama Stack client for further test-specific configuration.
    """
    mock_client = _build_mock_client(mocker)
    _patch_client_holders(mocker, mock_client)
    mocker.patch(
        "app.endpoints.responses.maybe_get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )
    return mock_client


def _configure_shield_blocked(
    mocker: MockerFixture,
    moderation_id: str,
) -> None:
    """Configure stub moderation to return a blocked result.

    Args:
        mocker: pytest-mock fixture.
        moderation_id: The moderation ID for the blocked response.
    """
    blocked = ShieldModerationBlocked(
        message="Content blocked by safety shield",
        moderation_id=moderation_id,
        refusal_response=OpenAIResponseMessage(
            role="assistant",
            content="Content blocked by safety shield",
        ),
    )
    mocker.patch(
        "app.endpoints.responses.run_shield_moderation",
        return_value=blocked,
    )


@pytest.mark.asyncio
async def test_non_streaming_success_persists_conversation_and_turn(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_db_session: Session,
) -> None:
    """Test that a successful non-streaming response persists UserConversation and UserTurn."""
    _ = test_config
    _ = _setup_test(mocker)

    request = ResponsesRequest(
        input="What is Ansible?",
        model="test-provider/test-model",
        stream=False,
        store=True,
        generate_topic_summary=False,
    )

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)
    assert response.id == "resp_integ_test"
    assert response.conversation == NORMALIZED_CONV_ID

    conversation = (
        test_db_session.query(UserConversation).filter_by(id=NORMALIZED_CONV_ID).first()
    )
    assert conversation is not None
    assert conversation.user_id == MOCK_AUTH[0]
    assert conversation.last_used_model == "test-model"
    assert conversation.last_used_provider == "test-provider"
    assert conversation.message_count == 1
    assert conversation.last_response_id == "resp_integ_test"

    turns = (
        test_db_session.query(UserTurn)
        .filter_by(conversation_id=NORMALIZED_CONV_ID)
        .all()
    )
    assert len(turns) == 1
    assert turns[0].turn_number == 1
    assert turns[0].response_id == "resp_integ_test"
    assert turns[0].model == "test-model"
    assert turns[0].provider == "test-provider"


@pytest.mark.asyncio
async def test_shield_blocked_persists_moderation_turn(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_db_session: Session,
) -> None:
    """Test shield-blocked response persists moderation ID and skips last_response_id."""
    _ = test_config
    mock_client = _setup_test(mocker)
    _configure_shield_blocked(mocker, "modr_blocked_integ_123")

    request = ResponsesRequest(
        input="Some blocked content",
        model="test-provider/test-model",
        stream=False,
        store=True,
        generate_topic_summary=False,
    )

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)
    assert response.id == "modr_blocked_integ_123"
    assert "Content blocked by safety shield" in (response.output_text or "")

    mock_client.responses.create.assert_not_called()

    conversation = (
        test_db_session.query(UserConversation).filter_by(id=NORMALIZED_CONV_ID).first()
    )
    assert conversation is not None
    assert conversation.last_response_id is None

    turns = (
        test_db_session.query(UserTurn)
        .filter_by(conversation_id=NORMALIZED_CONV_ID)
        .all()
    )
    assert len(turns) == 1
    assert turns[0].response_id == "modr_blocked_integ_123"


@pytest.mark.asyncio
async def test_store_false_skips_db_persistence(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_db_session: Session,
) -> None:
    """Test that store=False prevents UserConversation and UserTurn from being created."""
    _ = test_config
    _ = _setup_test(mocker)

    request = ResponsesRequest(
        input="What is Ansible?",
        model="test-provider/test-model",
        stream=False,
        store=False,
        generate_topic_summary=False,
    )

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    conversations = test_db_session.query(UserConversation).all()
    assert len(conversations) == 0

    turns = test_db_session.query(UserTurn).all()
    assert len(turns) == 0


@pytest.mark.asyncio
async def test_streaming_blocked_returns_sse_and_persists_turn(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_db_session: Session,
) -> None:
    """Test that shield-blocked streaming returns valid SSE events and persists to DB."""
    _ = test_config
    mock_client = _setup_test(mocker)
    _configure_shield_blocked(mocker, "modr_stream_blocked_123")

    request = ResponsesRequest(
        input="Some blocked content",
        model="test-provider/test-model",
        stream=True,
        store=True,
        generate_topic_summary=False,
    )

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"

    body = b""
    async for part in response.body_iterator:
        if isinstance(part, str):
            body += part.encode()
        else:
            body += bytes(part)
    body_str = body.decode()

    created_idx = body_str.find("event: response.created")
    completed_idx = body_str.find("event: response.completed")
    done_idx = body_str.find("data: [DONE]")
    assert created_idx != -1
    assert completed_idx != -1
    assert done_idx != -1
    assert created_idx < completed_idx < done_idx
    assert "Content blocked by safety shield" in body_str

    mock_client.responses.create.assert_not_called()

    conversation = (
        test_db_session.query(UserConversation).filter_by(id=NORMALIZED_CONV_ID).first()
    )
    assert conversation is not None
    assert conversation.last_response_id is None

    turns = (
        test_db_session.query(UserTurn)
        .filter_by(conversation_id=NORMALIZED_CONV_ID)
        .all()
    )
    assert len(turns) == 1
    assert turns[0].response_id == "modr_stream_blocked_123"
