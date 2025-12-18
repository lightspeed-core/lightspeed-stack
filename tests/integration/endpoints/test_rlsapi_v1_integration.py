"""Integration tests for the rlsapi v1 /infer endpoint.

Tests the stateless inference endpoint used by the RHEL Lightspeed Command Line
Assistant (CLA) for single-turn LLM queries without conversation persistence.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=protected-access
# pylint: disable=unused-argument

from typing import Any, NamedTuple

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError
from llama_stack_client.types.alpha.agents.turn import Turn
from pytest_mock import MockerFixture

import constants
from app.endpoints.rlsapi_v1 import infer_endpoint
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.rlsapi.requests import (
    RlsapiV1Attachment,
    RlsapiV1CLA,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)
from models.rlsapi.responses import RlsapiV1InferResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.suid import check_suid


class MockAgentFixture(NamedTuple):
    """Container for mocked Llama Stack agent components."""

    client: Any
    agent: Any
    holder_class: Any


# ==========================================
# Shared Fixtures
# ==========================================


@pytest.fixture(name="rlsapi_config")
def rlsapi_config_fixture(test_config: AppConfig, mocker: MockerFixture) -> AppConfig:
    """Extend test_config with inference defaults required by rlsapi v1.

    NOTE(major): The standard test configuration doesn't include inference
    settings (default_model, default_provider) which rlsapi v1 requires.
    """
    test_config.inference.default_model = "test-model"
    test_config.inference.default_provider = "test-provider"
    mocker.patch("app.endpoints.rlsapi_v1.configuration", test_config)
    return test_config


@pytest.fixture(name="mock_authorization")
def mock_authorization_fixture(mocker: MockerFixture) -> None:
    """Mock authorization resolvers for integration tests."""
    mock_authorization_resolvers(mocker)


def _create_mock_agent(
    mocker: MockerFixture,
    response_content: str = "Use the `ls` command to list files in a directory.",
    output_message: Any = "default",
) -> MockAgentFixture:
    """Create a mocked Llama Stack agent with configurable response.

    Args:
        mocker: pytest-mock fixture
        response_content: Text content for the LLM response
        output_message: Custom output_message Mock, or "default" to create one,
                       or None for no output_message

    Returns:
        MockAgentFixture with client, agent, and holder_class components
    """
    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_client = mocker.AsyncMock()

    # Configure output message
    if output_message == "default":
        mock_output_message = mocker.Mock()
        mock_output_message.content = response_content
    else:
        mock_output_message = output_message

    mock_turn = mocker.Mock(spec=Turn)
    mock_turn.output_message = mock_output_message
    mock_turn.steps = []

    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn = mocker.AsyncMock(return_value=mock_turn)
    mock_agent._agent_id = "test_agent_id"

    mocker.patch(
        "app.endpoints.rlsapi_v1.get_temp_agent",
        return_value=(mock_agent, "test_session_id", None),
    )

    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    return MockAgentFixture(mock_client, mock_agent, mock_holder_class)


@pytest.fixture(name="mock_llama_stack")
def mock_llama_stack_fixture(
    rlsapi_config: AppConfig, mocker: MockerFixture
) -> MockAgentFixture:
    """Mock Llama Stack client with successful response."""
    _ = rlsapi_config
    return _create_mock_agent(mocker)


# ==========================================
# Basic Response Tests
# ==========================================


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_minimal_request(
    mock_llama_stack: MockAgentFixture,
    mock_authorization: None,
    test_auth: AuthTuple,
) -> None:
    """Test /v1/infer endpoint with minimal request (question only)."""
    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        auth=test_auth,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text == "Use the `ls` command to list files in a directory."
    assert check_suid(response.data.request_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "test_id"),
    [
        pytest.param(
            RlsapiV1Context(stdin="Error: Connection refused"),
            "stdin_only",
            id="stdin_only",
        ),
        pytest.param(
            RlsapiV1Context(
                attachments=RlsapiV1Attachment(contents="[mysqld]\nmax=150")
            ),
            "attachment_only",
            id="attachment_only",
        ),
        pytest.param(
            RlsapiV1Context(terminal=RlsapiV1Terminal(output="Permission denied")),
            "terminal_only",
            id="terminal_only",
        ),
        pytest.param(
            RlsapiV1Context(
                stdin="dmesg output",
                attachments=RlsapiV1Attachment(contents="log content"),
                terminal=RlsapiV1Terminal(output="command not found"),
                systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64"),
                cla=RlsapiV1CLA(nevra="cla-0.4.0", version="0.4.0"),
            ),
            "full_context",
            id="full_context",
        ),
    ],
)
async def test_rlsapi_v1_infer_with_context(
    mock_llama_stack: MockAgentFixture,
    mock_authorization: None,
    test_auth: AuthTuple,
    context: RlsapiV1Context,
    test_id: str,
) -> None:
    """Test /v1/infer endpoint with various context configurations."""
    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="Help me?", context=context),
        auth=test_auth,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text is not None
    assert response.data.request_id is not None


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_generates_unique_request_ids(
    mock_llama_stack: MockAgentFixture,
    mock_authorization: None,
    test_auth: AuthTuple,
) -> None:
    """Test that each /v1/infer call generates a unique request_id."""
    request = RlsapiV1InferRequest(question="How do I list files?")

    responses = [
        await infer_endpoint(infer_request=request, auth=test_auth) for _ in range(3)
    ]
    request_ids = {r.data.request_id for r in responses}

    assert len(request_ids) == 3
    assert all(check_suid(rid) for rid in request_ids)


# ==========================================
# Error Handling Tests
# ==========================================


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_connection_error_returns_503(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test /v1/infer returns 503 when Llama Stack is unavailable."""
    _ = rlsapi_config

    # Create agent that raises APIConnectionError
    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_agent = mocker.AsyncMock()
    mock_agent.create_turn = mocker.AsyncMock(
        side_effect=APIConnectionError(request=mocker.Mock())
    )
    mocker.patch(
        "app.endpoints.rlsapi_v1.get_temp_agent",
        return_value=(mock_agent, "test_session_id", None),
    )
    mock_holder_class.return_value.get_client.return_value = mocker.AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="Test"),
            auth=test_auth,
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)
    assert "Llama Stack" in exc_info.value.detail["response"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_message",
    [
        pytest.param(None, id="none_output_message"),
        pytest.param("empty", id="empty_content"),
    ],
)
async def test_rlsapi_v1_infer_fallback_responses(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
    output_message: Any,
) -> None:
    """Test /v1/infer returns fallback for empty/None responses."""
    _ = rlsapi_config

    if output_message == "empty":
        mock_output = mocker.Mock()
        mock_output.content = ""
        _create_mock_agent(mocker, output_message=mock_output)
    else:
        _create_mock_agent(mocker, output_message=None)

    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="Test"),
        auth=test_auth,
    )

    assert response.data.text == constants.UNABLE_TO_PROCESS_RESPONSE


# ==========================================
# Input Source Combination Tests
# ==========================================


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_input_source_combination(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test that input sources are properly combined before sending to LLM."""
    _ = rlsapi_config
    mocks = _create_mock_agent(mocker)

    await infer_endpoint(
        infer_request=RlsapiV1InferRequest(
            question="My question",
            context=RlsapiV1Context(
                stdin="stdin content",
                attachments=RlsapiV1Attachment(contents="attachment content"),
                terminal=RlsapiV1Terminal(output="terminal output"),
            ),
        ),
        auth=test_auth,
    )

    # Verify all parts present in message sent to LLM
    call_args = mocks.agent.create_turn.call_args
    message_content = call_args.kwargs["messages"][0]["content"]

    for expected in ["My question", "stdin content", "attachment content", "terminal"]:
        assert expected in message_content


# ==========================================
# Skip RAG Tests
# ==========================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "skip_rag",
    [pytest.param(False, id="default_false"), pytest.param(True, id="explicit_true")],
)
async def test_rlsapi_v1_infer_skip_rag(
    mock_llama_stack: MockAgentFixture,
    mock_authorization: None,
    test_auth: AuthTuple,
    skip_rag: bool,
) -> None:
    """Test skip_rag parameter is accepted.

    NOTE(major): RAG is not implemented in lightspeed-stack rlsapi v1.
    """
    request = RlsapiV1InferRequest(question="How do I list files?", skip_rag=skip_rag)
    assert request.skip_rag == skip_rag

    response = await infer_endpoint(infer_request=request, auth=test_auth)
    assert isinstance(response, RlsapiV1InferResponse)
