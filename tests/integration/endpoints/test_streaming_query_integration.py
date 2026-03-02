"""Integration tests for the /streaming_query endpoint (using Responses API)."""

from collections.abc import AsyncIterator
from typing import Any, Generator

import pytest
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pytest_mock import AsyncMockType, MockerFixture

from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import Attachment, QueryRequest


@pytest.fixture(name="mock_streaming_llama_stack_client")
def mock_llama_stack_streaming_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the Llama Stack client (holder + client).

    Configures the client so the real handler runs: models, vector_stores,
    conversations, shields, vector_io, and responses.create returning a minimal
    stream. No other code paths are patched.
    """
    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
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

    async def _mock_stream() -> AsyncIterator[Any]:
        chunk = mocker.MagicMock()
        chunk.type = "response.output_text.done"
        chunk.text = "test"
        yield chunk

    async def _responses_create(**kwargs: Any) -> Any:
        if kwargs.get("stream", True):
            return _mock_stream()
        mock_resp = mocker.MagicMock()
        mock_resp.output = [mocker.MagicMock(content="topic summary")]
        return mock_resp

    mock_client.responses.create = mocker.AsyncMock(side_effect=_responses_create)

    mock_holder_class.return_value.get_client.return_value = mock_client

    yield mock_client


# ==========================================
# Attachment tests (mirror query integration)
# ==========================================


@pytest.mark.asyncio
async def test_streaming_query_v2_endpoint_empty_payload(
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test streaming_query with minimal payload (no attachments)."""
    _ = test_config
    _ = mock_streaming_llama_stack_client

    query_request = QueryRequest(query="what is kubernetes?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_streaming_query_v2_endpoint_empty_attachments_list(
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test streaming_query accepts empty attachment list."""
    _ = test_config
    _ = mock_streaming_llama_stack_client

    query_request = QueryRequest(
        query="what is kubernetes?",
        attachments=[],
    )

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_streaming_query_v2_endpoint_multiple_attachments(
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test streaming_query with multiple attachments (log + configuration)."""
    _ = test_config
    _ = mock_streaming_llama_stack_client

    query_request = QueryRequest(
        query="what is kubernetes?",
        attachments=[
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
    )

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_streaming_query_v2_endpoint_attachment_unknown_type_returns_422(
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test streaming_query returns 422 for unknown attachment type."""
    _ = test_config
    _ = mock_streaming_llama_stack_client

    query_request = QueryRequest(
        query="what is kubernetes?",
        attachments=[
            Attachment(
                attachment_type="unknown_type",
                content_type="text/plain",
                content="content",
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await streaming_query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert isinstance(exc_info.value.detail, dict)
    assert "unknown_type" in exc_info.value.detail["cause"]
    assert "Invalid" in exc_info.value.detail["response"]


@pytest.mark.asyncio
async def test_streaming_query_v2_endpoint_attachment_unknown_content_type_returns_422(
    test_config: AppConfig,
    mock_streaming_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test streaming_query returns 422 for unknown attachment content type."""
    _ = test_config
    _ = mock_streaming_llama_stack_client

    query_request = QueryRequest(
        query="what is kubernetes?",
        attachments=[
            Attachment(
                attachment_type="log",
                content_type="unknown/type",
                content="content",
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await streaming_query_endpoint_handler(
            request=test_request,
            query_request=query_request,
            auth=test_auth,
            mcp_headers={},
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert isinstance(exc_info.value.detail, dict)
    assert "unknown/type" in exc_info.value.detail["cause"]
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
