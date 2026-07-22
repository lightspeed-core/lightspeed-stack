"""Integration tests for the /streaming_query endpoint (using Responses API)."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pytest_mock import AsyncMockType, MockerFixture

from lightspeed_stack.app.endpoints.streaming_query import (
    streaming_query_endpoint_handler,
)
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.models.api.requests import QueryRequest
from lightspeed_stack.models.common.query import Attachment


@pytest.fixture(name="mock_streaming_llama_stack_client")
def mock_llama_stack_streaming_fixture(
    mocker: MockerFixture,
    mock_streaming_query_agent: AsyncMockType,
) -> Generator[Any, None, None]:
    """Mock only the Llama Stack client (holder + client).

    Configures the client so the real handler runs: models, vector_stores,
    conversations, shields, vector_io, and responses.create for topic summary.
    Agent inference is mocked separately via ``mock_streaming_query_agent``.
    """
    _ = mock_streaming_query_agent
    mock_holder_class = mocker.patch(
        "lightspeed_stack.app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = mocker.AsyncMock()

    mock_model = mocker.MagicMock()
    mock_model.id = "test-provider/test-model"
    mock_model.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "llm",
    }
    mock_client.models.list.return_value = [mock_model]

    mock_vector_stores_response = mocker.MagicMock()
    mock_vector_stores_response.data = []
    mock_client.vector_stores.list.return_value = mock_vector_stores_response

    mock_conversation = mocker.MagicMock()
    mock_conversation.id = "conv_" + "a" * 48
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)

    mock_client.shields.list.return_value = []

    mock_client.conversations.items.create = mocker.AsyncMock()

    mock_vector_io_response = mocker.MagicMock()
    mock_vector_io_response.chunks = []
    mock_vector_io_response.scores = []
    mock_client.vector_io.query = mocker.AsyncMock(return_value=mock_vector_io_response)

    async def _responses_create(**_kwargs: Any) -> Any:
        mock_resp = mocker.MagicMock()
        mock_resp.output = [mocker.MagicMock(content="topic summary")]
        return mock_resp

    mock_client.responses.create = mocker.AsyncMock(side_effect=_responses_create)

    mock_holder_class.return_value.get_client.return_value = mock_client

    yield mock_client


# ==========================================
# Attachment tests (mirror query integration)
# ==========================================

STREAMING_ATTACHMENT_TEST_CASES = [
    pytest.param(
        {
            "attachments": None,
            "expected_status": 200,
            "expected_error": None,
        },
        id="empty_payload",
    ),
    pytest.param(
        {
            "attachments": [],
            "expected_status": 200,
            "expected_error": None,
        },
        id="empty_attachments_list",
    ),
    pytest.param(
        {
            "attachments": [
                Attachment(
                    attachment_type="log",
                    content_type="text/plain",
                    content="log content",
                ),
                Attachment(
                    attachment_type="configuration",
                    content_type="application/json",
                    content='{"key": "value"}',
                ),
            ],
            "expected_status": 200,
            "expected_error": None,
        },
        id="multiple_attachments",
    ),
    pytest.param(
        {
            "attachments": [
                Attachment(
                    attachment_type="unknown_type",
                    content_type="text/plain",
                    content="content",
                )
            ],
            "expected_status": 422,
            "expected_error": "unknown_type",
        },
        id="attachment_unknown_type_returns_422",
    ),
    pytest.param(
        {
            "attachments": [
                Attachment(
                    attachment_type="log",
                    content_type="unknown/type",
                    content="content",
                )
            ],
            "expected_status": 422,
            "expected_error": "unknown/type",
        },
        id="attachment_unknown_content_type_returns_422",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", STREAMING_ATTACHMENT_TEST_CASES)
async def test_streaming_query_v2_endpoint_attachment_handling(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    test_case: dict,
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    mock_streaming_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Tests for streaming_query v2 endpoint attachment validation.

    Tests various attachment scenarios using parameterized test data including:
    - No attachments (None)
    - Empty attachments list
    - Multiple attachments
    - Unknown attachment type (422 error)
    - Unknown content type (422 error)

    Parameters:
        test_case: Dictionary containing test parameters (attachments,
            expected_status, expected_error)
        test_config: Test configuration
        mock_streaming_llama_stack_client: Mocked Llama Stack client
        mock_streaming_query_agent: Mocked Pydantic AI agent for build_agent
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_streaming_llama_stack_client
    _ = mock_streaming_query_agent

    attachments = test_case["attachments"]
    expected_status = test_case["expected_status"]
    expected_error = test_case["expected_error"]

    # Build query request with or without attachments
    if attachments is None:
        query_request = QueryRequest(query="what is kubernetes?")
    else:
        query_request = QueryRequest(
            query="what is kubernetes?",
            attachments=attachments,
        )

    if expected_status == 200:
        # Success case - verify streaming response
        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )
        assert response.status_code == expected_status
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
    else:
        # Error case - verify exception
        with pytest.raises(HTTPException) as exc_info:
            await streaming_query_endpoint_handler(
                request=test_request,
                query_request=query_request,
                auth=test_auth,
                mcp_headers={},
            )
        assert exc_info.value.status_code == expected_status
        assert isinstance(exc_info.value.detail, dict)
        if expected_error:
            assert expected_error in exc_info.value.detail["cause"]
            assert "Invalid" in exc_info.value.detail["response"]


def test_streaming_query_v2_endpoint_empty_body_returns_422(
    integration_http_client: TestClient,
) -> None:
    """Test streaming_query with empty request body returns 422."""
    response = integration_http_client.post(
        "/v1/streaming_query",
        json={},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    data = response.json()
    assert "detail" in data


STREAMING_OAUTH_401_TEST_CASES = [
    pytest.param(
        {
            "www_authenticate": 'Bearer realm="oauth"',
            "expect_www_authenticate": True,
        },
        id="with_www_authenticate_when_mcp_oauth_required",
    ),
    pytest.param(
        {
            "www_authenticate": None,
            "expect_www_authenticate": False,
        },
        id="without_www_authenticate_when_oauth_probe_times_out",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", STREAMING_OAUTH_401_TEST_CASES)
async def test_streaming_query_endpoint_returns_401_for_mcp_oauth(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    test_case: dict,
    test_config: AppConfig,
    mock_streaming_llama_stack_client: Any,
    mock_streaming_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Tests for streaming_query endpoint MCP OAuth 401 responses.

    Tests different OAuth failure scenarios:
    - MCP server requires OAuth with WWW-Authenticate header
    - OAuth probe times out without WWW-Authenticate header

    When get_mcp_tools raises 401 (with or without WWW-Authenticate),
    the streaming handler should propagate that response to the client.

    Parameters:
        test_case: Dictionary containing test parameters (www_authenticate,
            expect_www_authenticate)
        test_config: Test configuration
        mock_streaming_llama_stack_client: Mocked Llama Stack client
        mock_streaming_query_agent: Mocked Pydantic AI agent for build_agent
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture
    """
    _ = test_config
    _ = mock_streaming_llama_stack_client
    _ = mock_streaming_query_agent

    www_authenticate = test_case["www_authenticate"]
    expect_www_authenticate = test_case["expect_www_authenticate"]

    # Build 401 exception with or without WWW-Authenticate header
    oauth_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://example.com requires OAuth"},
        headers={"WWW-Authenticate": www_authenticate} if www_authenticate else None,
    )

    mocker.patch(
        "lightspeed_stack.utils.responses.get_mcp_tools",
        new_callable=mocker.AsyncMock,
        side_effect=oauth_401,
    )

    query_request = QueryRequest(query="What is Ansible?")

    with pytest.raises(HTTPException) as exc_info:
        await streaming_query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    if expect_www_authenticate:
        assert exc_info.value.headers is not None
        assert exc_info.value.headers.get("WWW-Authenticate") == www_authenticate
    else:
        assert (
            exc_info.value.headers is None
            or exc_info.value.headers.get("WWW-Authenticate") is None
        )
