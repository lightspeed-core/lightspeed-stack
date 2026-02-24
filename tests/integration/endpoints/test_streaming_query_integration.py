"""Integration tests for the /streaming_query endpoint."""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from typing import Any, Generator

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import QueryRequest


@pytest.fixture(name="mock_llama_stack_streaming")
def mock_llama_stack_streaming_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock the Llama Stack client for streaming_query endpoint.

    Configures models.list, vector_stores.list, and conversations.create so
    prepare_responses_params can run until get_mcp_tools.
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

    mock_holder_class.return_value.get_client.return_value = mock_client
    yield mock_client


@pytest.mark.asyncio
async def test_streaming_query_endpoint_returns_401_with_www_authenticate_when_mcp_oauth_required(
    test_config: AppConfig,
    mock_llama_stack_streaming: Any,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test streaming_query returns 401 with WWW-Authenticate when MCP server requires OAuth.

    When prepare_responses_params calls get_mcp_tools and an MCP server is
    configured for OAuth without client-provided headers, get_mcp_tools raises
    401 with WWW-Authenticate. This test verifies the streaming handler
    propagates that response to the client.
    """
    _ = test_config
    _ = mock_llama_stack_streaming

    expected_www_auth = 'Bearer realm="oauth"'
    oauth_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://example.com requires OAuth"},
        headers={"WWW-Authenticate": expected_www_auth},
    )
    mocker.patch(
        "utils.responses.get_mcp_tools",
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
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("WWW-Authenticate") == expected_www_auth
