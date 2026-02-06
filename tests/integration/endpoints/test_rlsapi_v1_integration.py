"""Integration tests for the rlsapi v1 /infer endpoint.

Tests the stateless inference endpoint used by the RHEL Lightspeed Command Line
Assistant (CLA) for single-turn LLM queries without conversation persistence.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments
# pylint: disable=protected-access
# pylint: disable=unused-argument

from typing import Any

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError
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

# ==========================================
# Shared Fixtures
# ==========================================


def _create_mock_request(mocker: MockerFixture) -> Any:
    """Create a mock FastAPI Request with minimal state."""
    mock_request = mocker.Mock()
    # Use spec=[] to create a Mock with no attributes, simulating absent rh_identity_data
    mock_request.state = mocker.Mock(spec=[])
    mock_request.headers = {"User-Agent": "CLA/0.4.1"}
    return mock_request


def _create_mock_background_tasks(mocker: MockerFixture) -> Any:
    """Create a mock BackgroundTasks object."""
    return mocker.Mock()


@pytest.fixture(name="mock_request")
def mock_request_fixture(mocker: MockerFixture) -> Any:
    """Fixture for mock FastAPI Request."""
    return _create_mock_request(mocker)


@pytest.fixture(name="mock_background_tasks")
def mock_background_tasks_fixture(mocker: MockerFixture) -> Any:
    """Fixture for mock BackgroundTasks."""
    return _create_mock_background_tasks(mocker)


@pytest.fixture(name="rlsapi_config")
def rlsapi_config_fixture(test_config: AppConfig, mocker: MockerFixture) -> AppConfig:
    """Extend test_config with inference defaults required by rlsapi v1."""
    test_config.inference.default_model = "test-model"
    test_config.inference.default_provider = "test-provider"
    mocker.patch("app.endpoints.rlsapi_v1.configuration", test_config)
    return test_config


@pytest.fixture(name="mock_authorization")
def mock_authorization_fixture(mocker: MockerFixture) -> None:
    """Mock authorization resolvers for integration tests."""
    mock_authorization_resolvers(mocker)


def _create_mock_response_output(mocker: MockerFixture, text: str) -> Any:
    """Create a mock Responses API output item with assistant message."""
    mock_output_item = mocker.Mock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = text
    return mock_output_item


def _setup_responses_mock(
    mocker: MockerFixture,
    response_text: str = "Use the `ls` command to list files in a directory.",
) -> Any:
    """Set up responses.create mock with the given response text."""
    mock_response = mocker.Mock()
    mock_response.output = [_create_mock_response_output(mocker, response_text)]

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    return mock_client


@pytest.fixture(name="mock_llama_stack")
def mock_llama_stack_fixture(rlsapi_config: AppConfig, mocker: MockerFixture) -> Any:
    """Mock Llama Stack client with successful response."""
    _ = rlsapi_config
    return _setup_responses_mock(mocker)


# ==========================================
# Basic Response Tests
# ==========================================


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_minimal_request(
    mock_llama_stack: Any,
    mock_authorization: None,
    mock_request: Any,
    mock_background_tasks: Any,
    test_auth: AuthTuple,
) -> None:
    """Test /v1/infer endpoint with minimal request (question only)."""
    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        request=mock_request,
        background_tasks=mock_background_tasks,
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
                cla=RlsapiV1CLA(nevra="cla-0.4.1", version="0.4.1"),
            ),
            "full_context",
            id="full_context",
        ),
    ],
)
async def test_rlsapi_v1_infer_with_context(
    mock_llama_stack: Any,
    mock_authorization: None,
    mock_request: Any,
    mock_background_tasks: Any,
    test_auth: AuthTuple,
    context: RlsapiV1Context,
    test_id: str,
) -> None:
    """Test /v1/infer endpoint with various context configurations."""
    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="Help me?", context=context),
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=test_auth,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text is not None
    assert response.data.request_id is not None


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_generates_unique_request_ids(
    mock_llama_stack: Any,
    mock_authorization: None,
    mock_request: Any,
    mock_background_tasks: Any,
    test_auth: AuthTuple,
) -> None:
    """Test that each /v1/infer call generates a unique request_id."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")

    responses = [
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=test_auth,
        )
        for _ in range(3)
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

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(
        side_effect=APIConnectionError(request=mocker.Mock())
    )

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="Test"),
            request=_create_mock_request(mocker),
            background_tasks=_create_mock_background_tasks(mocker),
            auth=test_auth,
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)
    assert "Llama Stack" in exc_info.value.detail["response"]


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_fallback_response_empty_output(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test /v1/infer returns fallback for empty output list."""
    _ = rlsapi_config

    mock_response = mocker.Mock()
    mock_response.output = []

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="Test"),
        request=_create_mock_request(mocker),
        background_tasks=_create_mock_background_tasks(mocker),
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

    mock_response = mocker.Mock()
    mock_response.output = [_create_mock_response_output(mocker, "response text")]

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    await infer_endpoint(
        infer_request=RlsapiV1InferRequest(
            question="My question",
            context=RlsapiV1Context(
                stdin="stdin content",
                attachments=RlsapiV1Attachment(contents="attachment content"),
                terminal=RlsapiV1Terminal(output="terminal output"),
            ),
        ),
        request=_create_mock_request(mocker),
        background_tasks=_create_mock_background_tasks(mocker),
        auth=test_auth,
    )

    call_args = mock_responses.create.call_args
    input_content = call_args.kwargs["input"]

    for expected in ["My question", "stdin content", "attachment content", "terminal"]:
        assert expected in input_content


# ==========================================
# MCP Tools Passthrough Tests
# ==========================================


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_no_mcp_servers_passes_empty_tools(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Regression: no MCP servers configured passes empty tools list.

    When mcp_servers is empty (the default), get_mcp_tools returns [],
    and responses.create should receive tools=[].
    """
    _ = rlsapi_config

    mock_response = mocker.Mock()
    mock_response.output = [_create_mock_response_output(mocker, "response text")]

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    mocker.patch(
        "app.endpoints.rlsapi_v1.get_mcp_tools",
        return_value=[],
    )

    await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        request=_create_mock_request(mocker),
        background_tasks=_create_mock_background_tasks(mocker),
        auth=test_auth,
    )

    call_kwargs = mock_responses.create.call_args.kwargs
    assert call_kwargs["tools"] == []


@pytest.mark.asyncio
async def test_rlsapi_v1_infer_mcp_tools_passed_to_llm(
    rlsapi_config: AppConfig,
    mock_authorization: None,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test that MCP tool definitions are forwarded to responses.create()."""
    _ = rlsapi_config

    mock_response = mocker.Mock()
    mock_response.output = [_create_mock_response_output(mocker, "enriched response")]

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder"
    )
    mock_holder_class.return_value.get_client.return_value = mock_client

    mcp_tools = [
        {
            "type": "mcp",
            "server_label": "rag-knowledge-base",
            "server_url": "http://rag-server:8080/sse",
            "require_approval": "never",
        }
    ]
    mocker.patch(
        "app.endpoints.rlsapi_v1.get_mcp_tools",
        return_value=mcp_tools,
    )

    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I configure SELinux?"),
        request=_create_mock_request(mocker),
        background_tasks=_create_mock_background_tasks(mocker),
        auth=test_auth,
    )

    call_kwargs = mock_responses.create.call_args.kwargs
    assert call_kwargs["tools"] == mcp_tools
    assert response.data.text == "enriched response"


# ==========================================
# Skip RAG Tests
# ==========================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "skip_rag",
    [pytest.param(False, id="default_false"), pytest.param(True, id="explicit_true")],
)
async def test_rlsapi_v1_infer_skip_rag(
    mock_llama_stack: Any,
    mock_authorization: None,
    mock_request: Any,
    mock_background_tasks: Any,
    test_auth: AuthTuple,
    skip_rag: bool,
) -> None:
    """Test skip_rag parameter is accepted.

    NOTE(major): RAG is not implemented in lightspeed-stack rlsapi v1.
    """
    infer_request = RlsapiV1InferRequest(
        question="How do I list files?", skip_rag=skip_rag
    )
    assert infer_request.skip_rag == skip_rag

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=test_auth,
    )
    assert isinstance(response, RlsapiV1InferResponse)
