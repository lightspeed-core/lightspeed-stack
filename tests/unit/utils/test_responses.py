"""Unit tests for utils/responses.py functions."""

# pylint: disable=line-too-long,too-many-lines

import json
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import HTTPException
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
    OpenAIResponseOutputMessageMCPListTools as MCPListTools,
    OpenAIResponseMCPApprovalRequest as MCPApprovalRequest,
    OpenAIResponseMCPApprovalResponse as MCPApprovalResponse,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from pydantic import AnyUrl
from pytest_mock import MockerFixture

from models.config import ModelContextProtocolServer
from models.requests import QueryRequest
from utils.responses import (
    build_mcp_tool_call_from_arguments_done,
    build_tool_call_summary,
    build_tool_result_from_mcp_output_item_done,
    extract_rag_chunks_from_file_search_item,
    extract_text_from_response_item,
    extract_text_from_response_items,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_mcp_tools,
    get_rag_tools,
    get_topic_summary,
    parse_arguments_string,
    parse_referenced_documents,
    prepare_responses_params,
    prepare_tools,
    _build_chunk_attributes,
    _increment_llm_call_metric,
    _resolve_source_for_result,
)
from utils.types import RAGChunk


class MockOutputItem:  # pylint: disable=too-few-public-methods
    """Mock Responses API output item."""

    def __init__(
        self,
        item_type: Optional[str] = None,
        role: Optional[str] = None,
        content: Any = None,
    ) -> None:
        # Use setattr to avoid conflict with built-in 'type'
        setattr(self, "type", item_type)
        self.role = role
        self.content = content


class MockContentPart:  # pylint: disable=too-few-public-methods
    """Mock content part for message content."""

    def __init__(
        self,
        text: Optional[str] = None,
        refusal: Optional[str] = None,
        part_type: Optional[str] = None,
    ) -> None:
        self.text = text
        self.refusal = refusal
        if part_type:
            self.type = part_type
        elif text:
            self.type = "output_text"
        elif refusal:
            self.type = "refusal"


def make_output_item(
    item_type: Optional[str] = None, role: Optional[str] = None, content: Any = None
) -> MockOutputItem:
    """Create a mock Responses API output item.

    Args:
        item_type: The type of the output item (e.g., "message", "function_call")
        role: The role of the message (e.g., "assistant", "user")
        content: The content of the message (can be str, list, or None)

    Returns:
        MockOutputItem: Mock object with type, role, and content attributes
    """
    mock_item = MockOutputItem(item_type=item_type, role=role, content=content)
    return mock_item


def make_content_part(
    text: Optional[str] = None,
    refusal: Optional[str] = None,
    part_type: Optional[str] = None,
) -> MockContentPart:
    """Create a mock content part for message content.

    Args:
        text: Text content of the part
        refusal: Refusal message content
        part_type: Type of the content part ("output_text" or "refusal")

    Returns:
        MockContentPart: Mock object with text and/or refusal attributes
    """
    return MockContentPart(text=text, refusal=refusal, part_type=part_type)


@pytest.mark.parametrize(
    "item_type,role,content,expected",
    [
        # Non-message types should return empty string
        ("function_call", "assistant", "some text", ""),
        ("file_search_call", "assistant", "some text", ""),
        (None, "assistant", "some text", ""),
        # User role messages are filtered out - return empty string
        ("message", "user", "some text", ""),
        # Valid assistant message with string content
        ("message", "assistant", "Hello, world!", "Hello, world!"),
        ("message", "assistant", "", ""),
    ],
    ids=[
        "function_call_type_returns_empty",
        "file_search_call_type_returns_empty",
        "none_type_returns_empty",
        "user_role_returns_empty",
        "valid_string_content",
        "empty_string_content",
    ],
)
def test_extract_text_basic_cases(
    item_type: str, role: str, content: Any, expected: str
) -> None:
    """Test basic extraction cases for different types, roles, and simple content.

    Args:
        item_type: Type of the output item
        role: Role of the message
        content: Content of the message
        expected: Expected extracted text
    """
    output_item = make_output_item(item_type=item_type, role=role, content=content)
    result = extract_text_from_response_item(output_item)  # type: ignore[arg-type]
    assert result == expected


@pytest.mark.parametrize(
    "content_parts,expected",
    [
        # Empty list
        ([], ""),
        # List with make_content_part objects containing text (with type="output_text")
        (
            [make_content_part(text="Part 1"), make_content_part(text=" Part 2")],
            "Part 1 Part 2",
        ),
        ([make_content_part(text="Only text")], "Only text"),
        # List with make_content_part objects containing refusal (with type="refusal")
        (
            [make_content_part(refusal="I cannot help with that")],
            "I cannot help with that",
        ),
        (
            [
                make_content_part(text="Some text"),
                make_content_part(refusal=" but I refuse"),
            ],
            "Some text but I refuse",
        ),
    ],
    ids=[
        "empty_list",
        "list_of_objects_with_text",
        "single_object_with_text",
        "object_with_refusal",
        "mixed_text_and_refusal_objects",
    ],
)
def test_extract_text_list_content(content_parts: list[Any], expected: str) -> None:
    """Test extraction from list-based content with various part types.

    Args:
        content_parts: List of content parts (strings, objects, dicts)
        expected: Expected concatenated text result
    """
    output_item = make_output_item(
        item_type="message", role="assistant", content=content_parts
    )
    result = extract_text_from_response_item(output_item)  # type: ignore[arg-type]
    assert result == expected


def test_extract_text_with_real_world_structure() -> None:
    """Test extraction with a structure mimicking real Responses API output.

    This test simulates a typical response structure with multiple content parts
    including text and potential refusals.
    """
    # Simulate a real-world response with multiple content parts
    content = [
        make_content_part(text="I can help you with that. "),
        make_content_part(text="Here's the information you requested: "),
        make_content_part(text="The answer is 42."),
    ]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_item(output_item)  # type: ignore[arg-type]

    expected = "I can help you with that. Here's the information you requested: The answer is 42."
    assert result == expected


def test_extract_text_preserves_order() -> None:
    """Test that content parts are concatenated in the correct order.

    Verifies that the order of content parts is preserved during extraction.
    """
    content = [
        make_content_part(text="First"),
        make_content_part(text=" Second"),
        make_content_part(text=" Third"),
        make_content_part(text=" Fourth"),
    ]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_item(output_item)  # type: ignore[arg-type]

    assert result == "First Second Third Fourth"


def test_extract_text_with_refusal_content() -> None:
    """Test extraction with refusal content parts.

    Verifies that refusal type content parts are properly extracted.
    """
    content = [
        make_content_part(refusal="I understand your request, "),
        make_content_part(refusal="but I cannot help with that."),
    ]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_item(output_item)  # type: ignore[arg-type]

    assert result == "I understand your request, but I cannot help with that."


class TestExtractTextFromResponseItems:
    """Test cases for extract_text_from_response_items function."""

    def test_extract_text_from_response_items_none(self) -> None:
        """Test extract_text_from_response_items returns empty string for None."""
        result = extract_text_from_response_items(None)
        assert result == ""

    def test_extract_text_from_response_items_empty_list(self) -> None:
        """Test extract_text_from_response_items returns empty string for empty list."""
        result = extract_text_from_response_items([])
        assert result == ""

    def test_extract_text_from_response_items_single_item(self) -> None:
        """Test extract_text_from_response_items with a single message item."""
        output_item = make_output_item(
            item_type="message", role="assistant", content="Hello world"
        )
        result = extract_text_from_response_items([output_item])  # type: ignore[arg-type]
        assert result == "Hello world"

    def test_extract_text_from_response_items_multiple_items(self) -> None:
        """Test extract_text_from_response_items with multiple message items."""
        item1 = make_output_item(
            item_type="message", role="assistant", content="First message"
        )
        item2 = make_output_item(
            item_type="message", role="assistant", content="Second message"
        )
        result = extract_text_from_response_items([item1, item2])  # type: ignore[arg-type]
        assert result == "First message Second message"

    def test_extract_text_from_response_items_filters_non_messages(self) -> None:
        """Test extract_text_from_response_items filters out non-message items."""
        item1 = make_output_item(
            item_type="message", role="assistant", content="Valid message"
        )
        item2 = make_output_item(
            item_type="function_call", role="assistant", content="Should be ignored"
        )
        result = extract_text_from_response_items([item1, item2])  # type: ignore[arg-type]
        assert result == "Valid message"

    def test_extract_text_from_response_items_filters_user_messages(self) -> None:
        """Test extract_text_from_response_items filters out user role messages."""
        item1 = make_output_item(
            item_type="message", role="assistant", content="Assistant message"
        )
        item2 = make_output_item(
            item_type="message", role="user", content="User message"
        )
        result = extract_text_from_response_items([item1, item2])  # type: ignore[arg-type]
        # User messages are filtered out - only assistant message is included
        assert result == "Assistant message"

    def test_extract_text_from_response_items_with_list_content(self) -> None:
        """Test extract_text_from_response_items with list-based content."""
        content = [
            make_content_part(text="Part 1"),
            make_content_part(text="Part 2"),
        ]
        output_item = make_output_item(
            item_type="message", role="assistant", content=content
        )
        result = extract_text_from_response_items([output_item])  # type: ignore[arg-type]
        assert result == "Part 1 Part 2"


class TestGetRAGTools:
    """Test cases for get_rag_tools utility function."""

    def test_get_rag_tools_empty_list(self) -> None:
        """Test get_rag_tools returns None for empty list."""
        assert get_rag_tools([]) is None

    def test_get_rag_tools_with_vector_stores(self) -> None:
        """Test get_rag_tools returns correct tool format for vector stores."""
        tools = get_rag_tools(["db1", "db2"])
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["type"] == "file_search"
        assert tools[0]["vector_store_ids"] == ["db1", "db2"]
        assert tools[0]["max_num_results"] == 10


class TestGetMCPTools:
    """Test cases for get_mcp_tools utility function."""

    @pytest.mark.asyncio
    async def test_get_mcp_tools_without_auth(self, mocker: MockerFixture) -> None:
        """Test get_mcp_tools with servers without authorization headers."""
        servers_no_auth = [
            ModelContextProtocolServer(
                name="fs", url="http://localhost:3000", provider_id="mcp"
            ),
            ModelContextProtocolServer(
                name="git", url="https://git.example.com/mcp", provider_id="mcp"
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers_no_auth
        mocker.patch("utils.responses.configuration", mock_config)

        tools_no_auth = await get_mcp_tools(token=None)
        assert len(tools_no_auth) == 2
        assert tools_no_auth[0]["type"] == "mcp"
        assert tools_no_auth[0]["server_label"] == "fs"
        assert tools_no_auth[0]["server_url"] == "http://localhost:3000"
        assert "headers" not in tools_no_auth[0]

    @pytest.mark.asyncio
    async def test_get_mcp_tools_with_kubernetes_auth(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools with kubernetes auth."""
        servers_k8s = [
            ModelContextProtocolServer(
                name="k8s-server",
                url="http://localhost:3000",
                authorization_headers={"Authorization": "kubernetes"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers_k8s
        mocker.patch("utils.responses.configuration", mock_config)
        tools_k8s = await get_mcp_tools(token="user-k8s-token")
        assert len(tools_k8s) == 1
        assert tools_k8s[0]["headers"] == {"Authorization": "Bearer user-k8s-token"}

    @pytest.mark.asyncio
    async def test_get_mcp_tools_with_mcp_headers(self, mocker: MockerFixture) -> None:
        """Test get_mcp_tools with client-provided headers."""
        servers = [
            ModelContextProtocolServer(
                name="fs",
                url="http://localhost:3000",
                authorization_headers={"Authorization": "client", "X-Custom": "client"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        mcp_headers = {
            "fs": {
                "Authorization": "client-provided-token",
                "X-Custom": "custom-value",
            }
        }
        tools = await get_mcp_tools(token=None, mcp_headers=mcp_headers)
        assert len(tools) == 1
        assert tools[0]["headers"] == {
            "Authorization": "client-provided-token",
            "X-Custom": "custom-value",
        }

        # Test with mcp_headers=None (server should be skipped)
        tools_no_headers = await get_mcp_tools(token=None, mcp_headers=None)
        assert len(tools_no_headers) == 0

    @pytest.mark.asyncio
    async def test_get_mcp_tools_client_auth_no_mcp_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools skips server when mcp_headers is None and server requires client auth."""  # noqa: E501
        servers = [
            ModelContextProtocolServer(
                name="client-auth-server",
                url="http://localhost:3000",
                authorization_headers={"X-Custom": "client"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        # When mcp_headers is None and server requires client auth,
        # should return None for that header
        # This tests the specific path at line 391
        tools = await get_mcp_tools(token=None, mcp_headers=None)
        # Server should be skipped because it requires client auth but mcp_headers is None
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_get_mcp_tools_client_auth_missing_server_in_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools skips server when mcp_headers doesn't contain server name."""
        servers = [
            ModelContextProtocolServer(
                name="client-auth-server",
                url="http://localhost:3000",
                authorization_headers={"X-Custom": "client"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        # mcp_headers exists but doesn't contain this server name
        # This tests the specific path at line 394
        mcp_headers = {"other-server": {"X-Custom": "value"}}
        tools = await get_mcp_tools(token=None, mcp_headers=mcp_headers)
        # Server should be skipped because mcp_headers doesn't contain this server
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_get_mcp_tools_with_static_headers(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools with static headers from config files."""
        secret_file = tmp_path / "token.txt"
        secret_file.write_text("static-secret-token")

        servers = [
            ModelContextProtocolServer(
                name="server1",
                url="http://localhost:3000",
                authorization_headers={"Authorization": str(secret_file)},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        tools = await get_mcp_tools(token=None)
        assert len(tools) == 1
        assert tools[0]["headers"] == {"Authorization": "static-secret-token"}

    @pytest.mark.asyncio
    async def test_get_mcp_tools_with_mixed_headers(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools with mixed header types."""
        secret_file = tmp_path / "api-key.txt"
        secret_file.write_text("secret-api-key")

        servers = [
            ModelContextProtocolServer(
                name="mixed-server",
                url="http://localhost:3000",
                authorization_headers={
                    "Authorization": "kubernetes",
                    "X-API-Key": str(secret_file),
                    "X-Custom": "client",
                },
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        mcp_headers = {
            "mixed-server": {
                "X-Custom": "client-custom-value",
            }
        }

        tools = await get_mcp_tools(token="k8s-token", mcp_headers=mcp_headers)
        assert len(tools) == 1
        assert tools[0]["headers"] == {
            "Authorization": "Bearer k8s-token",
            "X-API-Key": "secret-api-key",
            "X-Custom": "client-custom-value",
        }

    @pytest.mark.asyncio
    async def test_get_mcp_tools_skips_server_with_missing_auth(
        self, mocker: MockerFixture
    ) -> None:
        """Test that servers with required but unavailable auth headers are skipped."""
        servers = [
            ModelContextProtocolServer(
                name="missing-k8s-auth",
                url="http://localhost:3001",
                authorization_headers={"Authorization": "kubernetes"},
                provider_id="x",
            ),
            ModelContextProtocolServer(
                name="missing-client-auth",
                url="http://localhost:3002",
                authorization_headers={"X-Token": "client"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        tools = await get_mcp_tools(token=None, mcp_headers=None)
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_get_mcp_tools_includes_server_without_auth(
        self, mocker: MockerFixture
    ) -> None:
        """Test that servers without auth config are always included."""
        servers = [
            ModelContextProtocolServer(
                name="public-server",
                url="http://localhost:3000",
                authorization_headers={},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        tools = await get_mcp_tools(token=None, mcp_headers=None)
        assert len(tools) == 1
        assert tools[0]["server_label"] == "public-server"
        assert "headers" not in tools[0]

    @pytest.mark.asyncio
    async def test_get_mcp_tools_oauth_no_headers_raises_401_with_www_authenticate(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools raises 401 with WWW-Authenticate when OAuth required and no headers."""
        servers = [
            ModelContextProtocolServer(
                name="oauth-server",
                url="http://localhost:3000",
                authorization_headers={"Authorization": "oauth"},
                provider_id="x",
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        mock_resp = mocker.Mock()
        mock_resp.headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'}
        mock_session = mocker.MagicMock()
        mock_get_cm = mocker.AsyncMock()
        mock_get_cm.__aenter__.return_value = mock_resp
        mock_get_cm.__aexit__.return_value = None
        mock_session.get.return_value = mock_get_cm
        mock_session_cm = mocker.AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        mock_session_cm.__aexit__.return_value = None
        mocker.patch(
            "utils.mcp_oauth_probe.aiohttp.ClientSession",
            return_value=mock_session_cm,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_mcp_tools(token=None, mcp_headers=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.headers is not None
        assert (
            exc_info.value.headers.get("WWW-Authenticate")
            == 'Bearer error="invalid_token"'
        )

    @pytest.mark.asyncio
    async def test_get_mcp_tools_with_propagated_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_mcp_tools propagates allowlisted headers from the incoming request."""
        servers = [
            ModelContextProtocolServer(
                name="rbac",
                url="http://rbac:8080",
                headers=["x-rh-identity", "x-request-id"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        request_headers = {
            "x-rh-identity": "encoded-identity",
            "x-request-id": "req-456",
            "content-type": "application/json",
        }
        tools = await get_mcp_tools(
            token=None, mcp_headers=None, request_headers=request_headers
        )
        assert len(tools) == 1
        assert tools[0]["headers"] == {
            "x-rh-identity": "encoded-identity",
            "x-request-id": "req-456",
        }

    @pytest.mark.asyncio
    async def test_get_mcp_tools_propagated_headers_do_not_overwrite_auth_headers(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Test that propagated headers do not overwrite authorization_headers."""
        secret_file = tmp_path / "token.txt"
        secret_file.write_text("secret-token")

        servers = [
            ModelContextProtocolServer(
                name="rbac",
                url="http://rbac:8080",
                authorization_headers={"Authorization": str(secret_file)},
                headers=["Authorization", "x-rh-identity"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        request_headers = {
            "authorization": "request-auth-value",
            "x-rh-identity": "identity-value",
        }
        tools = await get_mcp_tools(
            token=None, mcp_headers=None, request_headers=request_headers
        )
        assert len(tools) == 1
        # Authorization from authorization_headers should win
        assert tools[0]["headers"]["Authorization"] == "secret-token"
        # x-rh-identity from propagated headers should be included
        assert tools[0]["headers"]["x-rh-identity"] == "identity-value"

    @pytest.mark.asyncio
    async def test_get_mcp_tools_propagated_headers_missing_from_request(
        self, mocker: MockerFixture
    ) -> None:
        """Test that missing allowlisted headers are simply skipped, server not skipped."""
        servers = [
            ModelContextProtocolServer(
                name="rbac",
                url="http://rbac:8080",
                headers=["x-rh-identity", "x-missing"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        request_headers = {
            "x-rh-identity": "identity-value",
        }
        tools = await get_mcp_tools(
            token=None, mcp_headers=None, request_headers=request_headers
        )
        assert len(tools) == 1
        assert tools[0]["headers"] == {"x-rh-identity": "identity-value"}

    @pytest.mark.asyncio
    async def test_get_mcp_tools_propagated_headers_no_request_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test that propagated headers are skipped when request_headers is None."""
        servers = [
            ModelContextProtocolServer(
                name="rbac",
                url="http://rbac:8080",
                headers=["x-rh-identity"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        tools = await get_mcp_tools(token=None, mcp_headers=None, request_headers=None)
        assert len(tools) == 1
        assert "headers" not in tools[0]

    @pytest.mark.asyncio
    async def test_get_mcp_tools_propagated_headers_additive_with_mcp_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test that propagated headers work alongside MCP-HEADERS (client mechanism)."""
        servers = [
            ModelContextProtocolServer(
                name="server1",
                url="http://server1:8080",
                authorization_headers={"Authorization": "client"},
                headers=["x-rh-identity"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        mcp_hdrs = {"server1": {"Authorization": "Bearer client-token"}}
        request_headers = {"x-rh-identity": "identity-value"}

        tools = await get_mcp_tools(
            token=None, mcp_headers=mcp_hdrs, request_headers=request_headers
        )
        assert len(tools) == 1
        assert tools[0]["headers"] == {
            "Authorization": "Bearer client-token",
            "x-rh-identity": "identity-value",
        }

    @pytest.mark.asyncio
    async def test_get_mcp_tools_mixed_case_precedence(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Test case-insensitive precedence: auth header wins over propagated variant."""
        secret_file = tmp_path / "token.txt"
        secret_file.write_text("file-secret")

        servers = [
            ModelContextProtocolServer(
                name="rbac",
                url="http://rbac:8080",
                authorization_headers={"Authorization": str(secret_file)},
                headers=["authorization", "x-rh-identity"],
            ),
        ]
        mock_config = mocker.Mock()
        mock_config.mcp_servers = servers
        mocker.patch("utils.responses.configuration", mock_config)

        request_headers = {
            "authorization": "request-value",
            "x-rh-identity": "identity-value",
        }
        tools = await get_mcp_tools(
            token=None, mcp_headers=None, request_headers=request_headers
        )
        assert len(tools) == 1
        # Auth header should win (case-insensitive)
        assert tools[0]["headers"]["Authorization"] == "file-secret"
        # Propagated header should be included
        assert tools[0]["headers"]["x-rh-identity"] == "identity-value"
        # No duplicate "authorization" key
        assert len(tools[0]["headers"]) == 2


class TestGetTopicSummary:
    """Tests for get_topic_summary function."""

    @pytest.mark.asyncio
    async def test_get_topic_summary_success(self, mocker: MockerFixture) -> None:
        """Test successful topic summary generation."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_output_item = make_output_item(
            item_type="message", role="assistant", content="Topic Summary"
        )
        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mocker.patch(
            "utils.responses.get_topic_summary_system_prompt", return_value="Summarize:"
        )
        mocker.patch("utils.responses.configuration", mocker.Mock())

        result = await get_topic_summary("test question", mock_client, "model1")
        assert result == "Topic Summary"
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_topic_summary_empty_response(
        self, mocker: MockerFixture
    ) -> None:
        """Test topic summary with empty response."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_response = mocker.Mock()
        mock_response.output = []
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mocker.patch(
            "utils.responses.get_topic_summary_system_prompt", return_value="Summarize:"
        )
        mocker.patch("utils.responses.configuration", mocker.Mock())

        result = await get_topic_summary("test question", mock_client, "model1")
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_topic_summary_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test topic summary raises HTTPException on connection error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        mocker.patch(
            "utils.responses.get_topic_summary_system_prompt", return_value="Summarize:"
        )
        mocker.patch("utils.responses.configuration", mocker.Mock())

        with pytest.raises(HTTPException) as exc_info:
            await get_topic_summary("test question", mock_client, "model1")
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_topic_summary_api_error(self, mocker: MockerFixture) -> None:
        """Test topic summary raises HTTPException on API error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        # Create a mock exception that will be caught by except APIStatusError
        mock_error = APIStatusError(
            message="API error", response=mocker.Mock(request=None), body=None
        )
        mock_client.responses.create = mocker.AsyncMock(side_effect=mock_error)

        mocker.patch(
            "utils.responses.get_topic_summary_system_prompt", return_value="Summarize:"
        )
        mocker.patch("utils.responses.configuration", mocker.Mock())
        mocker.patch(
            "utils.responses.handle_known_apistatus_errors",
            return_value=mocker.Mock(
                model_dump=lambda: {
                    "status_code": 500,
                    "detail": {"response": "Error", "cause": "API error"},
                }
            ),
        )

        with pytest.raises(HTTPException):
            await get_topic_summary("test question", mock_client, "model1")


class TestPrepareTools:
    """Tests for prepare_tools function."""

    @pytest.mark.asyncio
    async def test_prepare_tools_with_vector_store_ids(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_tools with specified vector store IDs."""
        mock_client = mocker.AsyncMock()
        mocker.patch("utils.responses.get_mcp_tools", return_value=None)

        result = await prepare_tools(mock_client, ["vs1", "vs2"], False, "token")
        assert result is not None
        assert len(result) == 1
        assert result[0]["type"] == "file_search"
        assert result[0]["vector_store_ids"] == ["vs1", "vs2"]

    @pytest.mark.asyncio
    async def test_prepare_tools_fetch_vector_stores(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_tools fetches vector stores when not specified."""
        mock_client = mocker.AsyncMock()
        mock_vector_store1 = mocker.Mock()
        mock_vector_store1.id = "vs1"
        mock_vector_store2 = mocker.Mock()
        mock_vector_store2.id = "vs2"
        mock_vector_stores = mocker.Mock()
        mock_vector_stores.data = [mock_vector_store1, mock_vector_store2]
        mock_client.vector_stores.list = mocker.AsyncMock(
            return_value=mock_vector_stores
        )
        mocker.patch("utils.responses.get_mcp_tools", return_value=None)

        result = await prepare_tools(mock_client, None, False, "token")
        assert result is not None
        assert len(result) == 1
        assert result[0]["vector_store_ids"] == ["vs1", "vs2"]

    @pytest.mark.asyncio
    async def test_prepare_tools_connection_error(self, mocker: MockerFixture) -> None:
        """Test prepare_tools raises HTTPException on connection error."""
        mock_client = mocker.AsyncMock()
        mock_client.vector_stores.list = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await prepare_tools(mock_client, None, False, "token")
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_prepare_tools_with_mcp_servers(self, mocker: MockerFixture) -> None:
        """Test prepare_tools includes MCP tools."""
        mock_client = mocker.AsyncMock()
        mock_mcp_tool = {"type": "mcp", "server_label": "test-server"}
        mocker.patch("utils.responses.get_mcp_tools", return_value=[mock_mcp_tool])

        result = await prepare_tools(mock_client, ["vs1"], False, "token")
        assert result is not None
        assert len(result) == 2  # RAG tool + MCP tool
        assert any(tool.get("type") == "mcp" for tool in result)

    @pytest.mark.asyncio
    async def test_prepare_tools_api_status_error(self, mocker: MockerFixture) -> None:
        """Test prepare_tools raises HTTPException on API status error when fetching vector stores."""  # noqa: E501
        mock_client = mocker.AsyncMock()
        mock_client.vector_stores.list = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error", response=mocker.Mock(request=None), body=None
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await prepare_tools(mock_client, None, False, "token")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_prepare_tools_empty_toolgroups(self, mocker: MockerFixture) -> None:
        """Test prepare_tools returns None when no tools are available."""
        mock_client = mocker.AsyncMock()
        mock_vector_stores = mocker.Mock()
        mock_vector_stores.data = []  # No vector stores
        mock_client.vector_stores.list = mocker.AsyncMock(
            return_value=mock_vector_stores
        )
        mocker.patch("utils.responses.get_mcp_tools", return_value=None)

        result = await prepare_tools(mock_client, None, False, "token")
        assert result is None

    @pytest.mark.asyncio
    async def test_prepare_tools_no_tools_true(self, mocker: MockerFixture) -> None:
        """Test prepare_tools returns None when no_tools=True."""
        mock_client = mocker.AsyncMock()

        # Should return None immediately without fetching vector stores or MCP tools
        result = await prepare_tools(mock_client, ["vs1", "vs2"], True, "token")

        assert result is None
        # Verify that vector_stores.list was not called
        mock_client.vector_stores.list.assert_not_called()


class TestPrepareResponsesParams:
    """Tests for prepare_responses_params function."""

    @pytest.mark.asyncio
    async def test_prepare_responses_params_with_conversation_id(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params with existing conversation ID."""
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])

        query_request = QueryRequest(
            query="test", conversation_id="123e4567-e89b-12d3-a456-426614174000"
        )  # pyright: ignore[reportCallIssue]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch("utils.responses.prepare_tools", return_value=None)
        mocker.patch("utils.responses.prepare_input", return_value="test")
        mocker.patch(
            "utils.responses.to_llama_stack_conversation_id", return_value="llama_conv1"
        )

        result = await prepare_responses_params(
            mock_client, query_request, None, "token"
        )
        assert result.input == "test"
        assert result.model == "provider1/model1"
        assert result.conversation == "llama_conv1"

    @pytest.mark.asyncio
    async def test_prepare_responses_params_create_conversation(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params creates new conversation when ID not provided."""
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])

        mock_conversation = mocker.Mock()
        mock_conversation.id = "new_conv_id"
        mock_client.conversations.create = mocker.AsyncMock(
            return_value=mock_conversation
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch("utils.responses.prepare_tools", return_value=None)
        mocker.patch("utils.responses.prepare_input", return_value="test")

        result = await prepare_responses_params(
            mock_client, query_request, None, "token"
        )
        assert result.conversation == "new_conv_id"
        mock_client.conversations.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_prepare_responses_params_connection_error_on_models(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params raises HTTPException on connection error when fetching models."""  # noqa: E501
        mock_client = mocker.AsyncMock()
        mock_client.models.list = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]
        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await prepare_responses_params(mock_client, query_request, None, "token")
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_prepare_responses_params_connection_error_on_conversation(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params raises HTTPException on connection error when creating conversation."""  # noqa: E501
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])
        mock_client.conversations.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch("utils.responses.prepare_tools", return_value=None)
        mocker.patch("utils.responses.prepare_input", return_value="test")

        with pytest.raises(HTTPException) as exc_info:
            await prepare_responses_params(mock_client, query_request, None, "token")
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_prepare_responses_params_api_status_error_on_models(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params raises HTTPException on API status error when fetching models."""  # noqa: E501
        mock_client = mocker.AsyncMock()
        mock_client.models.list = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error", response=mocker.Mock(request=None), body=None
            )
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]
        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)

        with pytest.raises(HTTPException) as exc_info:
            await prepare_responses_params(mock_client, query_request, None, "token")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_prepare_responses_params_includes_mcp_provider_data_headers(
        self, mocker: MockerFixture
    ) -> None:
        """Test that extra_headers with x-llamastack-provider-data is set when MCP tools have headers."""
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])

        mock_conversation = mocker.Mock()
        mock_conversation.id = "new_conv_id"
        mock_client.conversations.create = mocker.AsyncMock(
            return_value=mock_conversation
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        # Simulate MCP tools with headers (as returned by prepare_tools/get_mcp_tools)
        mcp_tools_with_headers = [
            {
                "type": "mcp",
                "server_label": "mcp::aap-controller",
                "server_url": "http://aap.foo.redhat.com:8004/sse",
                "require_approval": "never",
                "headers": {"X-Authorization": "client-token"},
            },
            {
                "type": "mcp",
                "server_label": "mcp::aap-lightspeed",
                "server_url": "http://aap.foo.redhat.com:8005/sse",
                "require_approval": "never",
                "headers": {"X-Authorization": "client-token-2"},
            },
        ]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch(
            "utils.responses.prepare_tools", return_value=mcp_tools_with_headers
        )
        mocker.patch("utils.responses.prepare_input", return_value="test")

        result = await prepare_responses_params(
            mock_client, query_request, None, "token"
        )

        # The result should contain extra_headers with x-llamastack-provider-data
        dumped = result.model_dump()
        assert (
            dumped["extra_headers"] is not None
        ), "extra_headers should not be None when MCP tools have headers"
        assert "x-llamastack-provider-data" in dumped["extra_headers"]

        provider_data = json.loads(
            dumped["extra_headers"]["x-llamastack-provider-data"]
        )
        assert "mcp_headers" in provider_data
        assert provider_data["mcp_headers"] == {
            "http://aap.foo.redhat.com:8004/sse": {"X-Authorization": "client-token"},
            "http://aap.foo.redhat.com:8005/sse": {"X-Authorization": "client-token-2"},
        }

    @pytest.mark.asyncio
    async def test_prepare_responses_params_no_extra_headers_without_mcp_tools(
        self, mocker: MockerFixture
    ) -> None:
        """Test that extra_headers is None when no MCP tools have headers."""
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])

        mock_conversation = mocker.Mock()
        mock_conversation.id = "new_conv_id"
        mock_client.conversations.create = mocker.AsyncMock(
            return_value=mock_conversation
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch("utils.responses.prepare_tools", return_value=None)
        mocker.patch("utils.responses.prepare_input", return_value="test")

        result = await prepare_responses_params(
            mock_client, query_request, None, "token"
        )

        dumped = result.model_dump()
        assert dumped.get("extra_headers") is None

    @pytest.mark.asyncio
    async def test_prepare_responses_params_api_status_error_on_conversation(
        self, mocker: MockerFixture
    ) -> None:
        """Test prepare_responses_params raises HTTPException on API status error when creating conversation."""  # noqa: E501
        mock_client = mocker.AsyncMock()
        mock_model = mocker.Mock()
        mock_model.id = "provider1/model1"
        mock_model.custom_metadata = {"model_type": "llm", "provider_id": "provider1"}
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])
        mock_client.conversations.create = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error", response=mocker.Mock(request=None), body=None
            )
        )

        query_request = QueryRequest(query="test")  # pyright: ignore[reportCallIssue]

        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("utils.responses.configuration", mock_config)
        mocker.patch("utils.responses.get_system_prompt", return_value="System prompt")
        mocker.patch("utils.responses.prepare_tools", return_value=None)
        mocker.patch("utils.responses.prepare_input", return_value="test")

        with pytest.raises(HTTPException) as exc_info:
            await prepare_responses_params(mock_client, query_request, None, "token")
        assert exc_info.value.status_code == 500


class TestParseReferencedDocuments:
    """Tests for parse_referenced_documents function."""

    def test_parse_referenced_documents_none_response(self) -> None:
        """Test parsing with None response."""
        result = parse_referenced_documents(None)
        assert not result

    def test_parse_referenced_documents_empty_output(
        self, mocker: MockerFixture
    ) -> None:
        """Test parsing with empty output."""
        mock_response = mocker.Mock()
        mock_response.output = []
        result = parse_referenced_documents(mock_response)
        assert not result

    def test_parse_referenced_documents_file_search_call(
        self, mocker: MockerFixture
    ) -> None:
        """Test parsing from file_search_call results."""
        mock_result1 = mocker.Mock()
        mock_result1.attributes = {
            "link": "https://example.com/doc1",
            "title": "Document 1",
        }

        mock_result2 = {
            "attributes": {"url": "https://example.com/doc2", "title": "Document 2"},
        }

        mock_output_item = mocker.Mock()
        mock_output_item.type = "file_search_call"
        mock_output_item.results = [mock_result1, mock_result2]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]

        result = parse_referenced_documents(mock_response)
        assert len(result) == 2
        assert result[0].doc_title == "Document 1"
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[1].doc_title == "Document 2"
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")

    def test_parse_referenced_documents_message_annotations(
        self, mocker: MockerFixture
    ) -> None:
        """Test parsing from message content annotations - no longer supported."""
        # Message annotations are no longer parsed by parse_referenced_documents
        # This test verifies that message type output items are ignored
        mock_annotation1 = mocker.Mock()
        mock_annotation1.type = "url_citation"
        mock_annotation1.url = "https://example.com/doc1"
        mock_annotation1.title = "Document 1"

        mock_annotation2 = {"type": "file_citation", "filename": "doc2.pdf"}

        mock_part = mocker.Mock()
        mock_part.annotations = [mock_annotation1, mock_annotation2]

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        mock_output_item.content = [mock_part]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]

        result = parse_referenced_documents(mock_response)
        # Message annotations are no longer parsed, so result should be empty
        assert len(result) == 0

    def test_parse_referenced_documents_string_parts_skipped(
        self, mocker: MockerFixture
    ) -> None:
        """Test that message type output items are ignored."""
        # Message annotations are no longer parsed by parse_referenced_documents
        mock_annotation = mocker.Mock()
        mock_annotation.type = "url_citation"
        mock_annotation.url = "https://example.com/doc1"
        mock_annotation.title = "Document 1"

        mock_part = mocker.Mock()
        mock_part.annotations = [mock_annotation]

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        # Include a string part that should be skipped
        mock_output_item.content = ["string part", mock_part]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]

        result = parse_referenced_documents(mock_response)
        # Message type is no longer parsed, so result should be empty
        assert len(result) == 0

    def test_parse_referenced_documents_deduplication(
        self, mocker: MockerFixture
    ) -> None:
        """Test that duplicate documents are deduplicated."""
        mock_result = mocker.Mock()
        mock_result.attributes = {
            "link": "https://example.com/doc1",
            "title": "Document 1",
        }

        mock_output_item = mocker.Mock()
        mock_output_item.type = "file_search_call"
        mock_output_item.results = [mock_result, mock_result]  # Duplicate

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]

        result = parse_referenced_documents(mock_response)
        assert len(result) == 1  # Should be deduplicated


class TestExtractTokenUsage:
    """Tests for extract_token_usage function."""

    @pytest.mark.parametrize(
        "input_tokens,output_tokens",
        [(100, 50), (200, 100)],
        ids=["usage_100_50", "usage_200_100"],
    )
    def test_extract_token_usage_with_usage_object(
        self,
        mocker: MockerFixture,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Test extracting token usage from usage object (mock with input/output tokens)."""
        mock_usage = mocker.Mock()
        mock_usage.input_tokens = input_tokens
        mock_usage.output_tokens = output_tokens

        mocker.patch(
            "utils.responses.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("utils.responses.metrics.llm_token_sent_total")
        mocker.patch("utils.responses.metrics.llm_token_received_total")
        mocker.patch("utils.responses._increment_llm_call_metric")

        result = extract_token_usage(mock_usage, "provider1/model1")
        assert result.input_tokens == input_tokens
        assert result.output_tokens == output_tokens
        assert result.llm_calls == 1

    def test_extract_token_usage_no_usage(self, mocker: MockerFixture) -> None:
        """Test extracting token usage when usage is None."""
        mocker.patch(
            "utils.responses.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("utils.responses._increment_llm_call_metric")

        result = extract_token_usage(None, "provider1/model1")
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.llm_calls == 1

    def test_extract_token_usage_zero_tokens(self, mocker: MockerFixture) -> None:
        """Test extracting token usage when tokens are 0."""
        mock_usage = mocker.Mock()
        mock_usage.input_tokens = 0
        mock_usage.output_tokens = 0

        mocker.patch(
            "utils.responses.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("utils.responses._increment_llm_call_metric")

        result = extract_token_usage(mock_usage, "provider1/model1")
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_extract_token_usage_none_response(self, mocker: MockerFixture) -> None:
        """Test extracting token usage with None response."""
        mocker.patch(
            "utils.responses.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("utils.responses._increment_llm_call_metric")

        result = extract_token_usage(None, "provider1/model1")
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_extract_token_usage_metrics_error(self, mocker: MockerFixture) -> None:
        """Test extracting token usage handles errors when updating metrics."""
        mock_usage = mocker.Mock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mocker.patch(
            "utils.responses.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        # Make metrics raise an error
        mock_metric = mocker.Mock()
        mock_metric.labels.return_value.inc = mocker.Mock(
            side_effect=AttributeError("No attribute")
        )
        mocker.patch("utils.responses.metrics.llm_token_sent_total", mock_metric)
        mocker.patch("utils.responses.metrics.llm_token_received_total", mock_metric)
        mocker.patch("utils.responses.logger")
        mocker.patch("utils.responses._increment_llm_call_metric")

        # Should not raise, just log warning
        result = extract_token_usage(mock_usage, "provider1/model1")
        assert result.input_tokens == 100
        assert result.output_tokens == 50


class TestBuildToolCallSummary:
    """Tests for build_tool_call_summary function."""

    def test_build_tool_call_summary_function_call(self, mocker: MockerFixture) -> None:
        """Test building summary for function_call."""
        mock_item = mocker.Mock(spec=FunctionCall)
        mock_item.type = "function_call"
        mock_item.call_id = "call_123"
        mock_item.name = "test_function"
        mock_item.arguments = '{"arg1": "value1"}'

        rag_chunks: list[RAGChunk] = []
        mocker.patch(
            "utils.responses.parse_arguments_string", return_value={"arg1": "value1"}
        )

        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)
        assert call_summary is not None
        assert call_summary.name == "test_function"
        assert call_summary.args == {"arg1": "value1"}
        assert result_summary is None

    def test_build_tool_call_summary_file_search_call(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for file_search_call."""
        mock_result = mocker.Mock()
        mock_result.text = "chunk text"
        mock_result.filename = "doc.pdf"
        mock_result.score = 0.9
        mock_result.attributes = None
        mock_result.model_dump = mocker.Mock(
            return_value={"text": "chunk text", "filename": "doc.pdf", "score": 0.9}
        )

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.type = "file_search_call"
        mock_item.id = "search_123"
        mock_item.queries = ["query1"]
        mock_item.results = [mock_result]
        mock_item.status = "success"

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)

        assert call_summary is not None
        assert call_summary.name == "file_search"
        assert len(rag_chunks) == 1
        assert result_summary is not None
        assert result_summary.status == "success"

    def test_build_tool_call_summary_web_search_call(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for web_search_call."""
        mock_item = mocker.Mock(spec=WebSearchCall)
        mock_item.type = "web_search_call"
        mock_item.id = "web_123"
        mock_item.status = "success"

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)

        assert call_summary is not None
        assert call_summary.name == "web_search"
        assert result_summary is not None
        assert result_summary.status == "success"

    def test_build_tool_call_summary_mcp_call(self, mocker: MockerFixture) -> None:
        """Test building summary for mcp_call."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.type = "mcp_call"
        mock_item.id = "mcp_123"
        mock_item.name = "mcp_tool"
        mock_item.arguments = '{"arg": "value"}'
        mock_item.server_label = "test_server"
        mock_item.error = None
        mock_item.output = "output"

        rag_chunks: list[RAGChunk] = []
        mocker.patch(
            "utils.responses.parse_arguments_string", return_value={"arg": "value"}
        )

        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)
        assert call_summary is not None
        assert call_summary.name == "mcp_tool"
        assert call_summary.args["server_label"] == "test_server"
        assert result_summary is not None
        assert result_summary.status == "success"

    def test_build_tool_call_summary_mcp_call_with_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for mcp_call with error."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.type = "mcp_call"
        mock_item.id = "mcp_123"
        mock_item.name = "mcp_tool"
        mock_item.arguments = "{}"
        mock_item.server_label = None
        mock_item.error = "Error occurred"
        mock_item.output = None

        rag_chunks: list[RAGChunk] = []
        mocker.patch("utils.responses.parse_arguments_string", return_value={})

        _call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)
        assert result_summary is not None
        assert result_summary.status == "failure"
        assert result_summary.content == "Error occurred"

    def test_build_tool_call_summary_mcp_list_tools(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for mcp_list_tools."""
        mock_tool = mocker.Mock()
        mock_tool.name = "tool1"
        mock_tool.description = "Description"
        mock_tool.input_schema = {"type": "object"}

        mock_item = mocker.Mock(spec=MCPListTools)
        mock_item.type = "mcp_list_tools"
        mock_item.id = "list_123"
        mock_item.server_label = "test_server"
        mock_item.tools = [mock_tool]

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)

        assert call_summary is not None
        assert call_summary.name == "mcp_list_tools"
        assert result_summary is not None
        assert "tools" in json.loads(result_summary.content)

    def test_build_tool_call_summary_mcp_approval_request(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for mcp_approval_request."""
        mock_item = mocker.Mock(spec=MCPApprovalRequest)
        mock_item.type = "mcp_approval_request"
        mock_item.id = "approval_123"
        mock_item.name = "approve_action"
        mock_item.arguments = '{"action": "delete"}'

        rag_chunks: list[RAGChunk] = []
        mocker.patch(
            "utils.responses.parse_arguments_string", return_value={"action": "delete"}
        )

        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)
        assert call_summary is not None
        assert call_summary.name == "approve_action"
        assert result_summary is None

    def test_build_tool_call_summary_mcp_approval_response(
        self, mocker: MockerFixture
    ) -> None:
        """Test building summary for mcp_approval_response."""
        mock_item = mocker.Mock(spec=MCPApprovalResponse)
        mock_item.type = "mcp_approval_response"
        mock_item.approval_request_id = "request_123"
        mock_item.approve = True
        mock_item.reason = "Approved"

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)

        assert call_summary is None
        assert result_summary is not None
        assert result_summary.status == "success"
        assert "reason" in json.loads(result_summary.content)

    def test_build_tool_call_summary_unknown_type(self, mocker: MockerFixture) -> None:
        """Test building summary for unknown type returns None."""
        mock_item = mocker.Mock()
        mock_item.type = "unknown_type"

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(mock_item, rag_chunks)
        assert call_summary is None
        assert result_summary is None


class TestExtractRagChunksFromFileSearchItem:
    """Tests for extract_rag_chunks_from_file_search_item function."""

    def test_extract_rag_chunks_with_results(self, mocker: MockerFixture) -> None:
        """Test extracting RAG chunks from file search results."""
        mock_result1 = mocker.Mock()
        mock_result1.text = "chunk 1"
        mock_result1.filename = "doc1.pdf"
        mock_result1.score = 0.9
        mock_result1.attributes = None

        mock_result2 = mocker.Mock()
        mock_result2.text = "chunk 2"
        mock_result2.filename = "doc2.pdf"
        mock_result2.score = 0.8
        mock_result2.attributes = None

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.results = [mock_result1, mock_result2]

        rag_chunks: list[RAGChunk] = []
        extract_rag_chunks_from_file_search_item(mock_item, rag_chunks)

        assert len(rag_chunks) == 2
        assert rag_chunks[0].content == "chunk 1"
        assert rag_chunks[0].source is None
        assert rag_chunks[0].score == 0.9

    def test_extract_rag_chunks_no_results(self, mocker: MockerFixture) -> None:
        """Test extracting RAG chunks when results is None."""
        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.results = None

        rag_chunks: list[RAGChunk] = []
        extract_rag_chunks_from_file_search_item(mock_item, rag_chunks)
        assert len(rag_chunks) == 0


class TestParseArgumentsString:
    """Tests for parse_arguments_string function."""

    def test_parse_arguments_string_valid_json(self) -> None:
        """Test parsing valid JSON string."""
        result = parse_arguments_string('{"key": "value", "num": 123}')
        assert result == {"key": "value", "num": 123}

    def test_parse_arguments_string_wrapped_content(self) -> None:
        """Test parsing string that needs wrapping."""
        result = parse_arguments_string('"key": "value"')
        assert result == {"key": "value"}

    def test_parse_arguments_string_invalid_json(self) -> None:
        """Test parsing invalid JSON falls back to args wrapper."""
        result = parse_arguments_string("not json at all")
        assert result == {"args": "not json at all"}

    def test_parse_arguments_string_non_dict_json(self) -> None:
        """Test parsing JSON that's not a dict falls back."""
        result = parse_arguments_string('["array", "not", "dict"]')
        assert result == {"args": '["array", "not", "dict"]'}

    def test_parse_arguments_string_empty_string(self) -> None:
        """Test parsing empty string."""
        result = parse_arguments_string("")
        assert result == {"args": ""}


class TestIncrementLlmCallMetric:
    """Tests for _increment_llm_call_metric function."""

    def test_increment_llm_call_metric_success(self, mocker: MockerFixture) -> None:
        """Test successful metric increment."""
        mock_metric = mocker.Mock()
        mock_metric.labels.return_value.inc = mocker.Mock()
        mocker.patch("utils.responses.metrics.llm_calls_total", mock_metric)

        _increment_llm_call_metric("provider1", "model1")

        mock_metric.labels.assert_called_once_with("provider1", "model1")
        mock_metric.labels.return_value.inc.assert_called_once()

    def test_increment_llm_call_metric_attribute_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test metric increment handles AttributeError."""
        mocker.patch(
            "utils.responses.metrics.llm_calls_total",
            side_effect=AttributeError("No attribute"),
        )
        mocker.patch("utils.responses.logger")

        # Should not raise exception
        _increment_llm_call_metric("provider1", "model1")

    def test_increment_llm_call_metric_type_error(self, mocker: MockerFixture) -> None:
        """Test metric increment handles TypeError."""
        mock_metric = mocker.Mock()
        mock_metric.labels.return_value.inc = mocker.Mock(
            side_effect=TypeError("Invalid type")
        )
        mocker.patch("utils.responses.metrics.llm_calls_total", mock_metric)
        mocker.patch("utils.responses.logger")

        # Should not raise exception
        _increment_llm_call_metric("provider1", "model1")

    def test_increment_llm_call_metric_value_error(self, mocker: MockerFixture) -> None:
        """Test metric increment handles ValueError."""
        mock_metric = mocker.Mock()
        mock_metric.labels.return_value.inc = mocker.Mock(
            side_effect=ValueError("Invalid value")
        )
        mocker.patch("utils.responses.metrics.llm_calls_total", mock_metric)
        mocker.patch("utils.responses.logger")

        # Should not raise exception
        _increment_llm_call_metric("provider1", "model1")


class TestBuildMCPToolCallFromArgumentsDone:
    """Tests for build_mcp_tool_call_from_arguments_done function."""

    def test_build_mcp_tool_call_with_valid_item(self) -> None:
        """Test building MCP tool call with valid item info."""
        mcp_call_items = {0: ("call_123", "test_tool")}
        tool_call = build_mcp_tool_call_from_arguments_done(
            output_index=0,
            arguments='{"param": "value"}',
            mcp_call_items=mcp_call_items,
        )

        assert tool_call is not None
        assert tool_call.id == "call_123"
        assert tool_call.name == "test_tool"
        assert tool_call.type == "mcp_call"
        assert tool_call.args == {"param": "value"}
        # Item should be removed from dict
        assert 0 not in mcp_call_items

    def test_build_mcp_tool_call_with_missing_item(self) -> None:
        """Test building MCP tool call when item info is missing."""
        mcp_call_items: dict[int, tuple[str, str]] = {}
        tool_call = build_mcp_tool_call_from_arguments_done(
            output_index=0,
            arguments='{"param": "value"}',
            mcp_call_items=mcp_call_items,
        )

        assert tool_call is None

    def test_build_mcp_tool_call_parses_arguments(self) -> None:
        """Test that arguments are properly parsed."""
        mcp_call_items = {1: ("call_456", "another_tool")}
        tool_call = build_mcp_tool_call_from_arguments_done(
            output_index=1,
            arguments='{"key1": "val1", "key2": 42}',
            mcp_call_items=mcp_call_items,
        )

        assert tool_call is not None
        assert tool_call.args == {"key1": "val1", "key2": 42}


class TestBuildToolResultFromMCPOutputItemDone:
    """Tests for build_tool_result_from_mcp_output_item_done function."""

    def test_build_mcp_tool_result_success(self, mocker: MockerFixture) -> None:
        """Test building MCP tool result for successful call."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.id = "call_123"
        mock_item.error = None
        mock_item.output = "Success output"

        result = build_tool_result_from_mcp_output_item_done(mock_item)

        assert result.id == "call_123"
        assert result.status == "success"
        assert result.content == "Success output"
        assert result.type == "mcp_call"
        assert result.round == 1

    def test_build_mcp_tool_result_failure(self, mocker: MockerFixture) -> None:
        """Test building MCP tool result for failed call."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.id = "call_456"
        mock_item.error = "Error message"
        mock_item.output = None

        result = build_tool_result_from_mcp_output_item_done(mock_item)

        assert result.id == "call_456"
        assert result.status == "failure"
        assert result.content == "Error message"
        assert result.type == "mcp_call"

    def test_build_mcp_tool_result_empty_output(self, mocker: MockerFixture) -> None:
        """Test building MCP tool result with empty output."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.id = "call_789"
        mock_item.error = None
        mock_item.output = ""

        result = build_tool_result_from_mcp_output_item_done(mock_item)

        assert result.status == "success"
        assert result.content == ""

    def test_build_mcp_tool_result_none_output(self, mocker: MockerFixture) -> None:
        """Test building MCP tool result with None output."""
        mock_item = mocker.Mock(spec=MCPCall)
        mock_item.id = "call_999"
        mock_item.error = None
        mock_item.output = None

        result = build_tool_result_from_mcp_output_item_done(mock_item)

        assert result.status == "success"
        assert result.content == ""


class TestResolveSourceForResult:
    """Tests for _resolve_source_for_result function."""

    def test_single_store_mapped(self, mocker: MockerFixture) -> None:
        """Test resolution with single vector store that has a mapping."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"

        source = _resolve_source_for_result(
            mock_result, ["vs-001"], {"vs-001": "ocp-4.18-docs"}
        )
        assert source == "ocp-4.18-docs"

    def test_single_store_unmapped(self, mocker: MockerFixture) -> None:
        """Test resolution with single vector store without mapping returns raw store ID."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"

        source = _resolve_source_for_result(mock_result, ["vs-unknown"], {})
        assert source == "vs-unknown"

    def test_multiple_stores_with_attribute(self, mocker: MockerFixture) -> None:
        """Test resolution with multiple stores using result attributes."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"
        mock_result.attributes = {"vector_store_id": "vs-002"}

        source = _resolve_source_for_result(
            mock_result,
            ["vs-001", "vs-002"],
            {"vs-001": "ocp-4.18-docs", "vs-002": "rhel-9-docs"},
        )
        assert source == "rhel-9-docs"

    def test_multiple_stores_no_attribute(self, mocker: MockerFixture) -> None:
        """Test resolution with multiple stores and no vector_store_id attribute returns None."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"
        mock_result.attributes = {}

        source = _resolve_source_for_result(
            mock_result,
            ["vs-001", "vs-002"],
            {"vs-001": "ocp-4.18-docs", "vs-002": "rhel-9-docs"},
        )
        assert source is None

    def test_no_stores(self, mocker: MockerFixture) -> None:
        """Test resolution with no vector stores returns None."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"

        source = _resolve_source_for_result(mock_result, [], {})
        assert source is None

    def test_multiple_stores_attribute_not_in_mapping(
        self, mocker: MockerFixture
    ) -> None:
        """Test resolution when attribute store ID is not in mapping returns raw store ID."""
        mock_result = mocker.Mock()
        mock_result.filename = "file-abc123"
        mock_result.attributes = {"vector_store_id": "vs-unknown"}

        source = _resolve_source_for_result(
            mock_result,
            ["vs-001", "vs-002"],
            {"vs-001": "ocp-docs"},
        )
        assert source == "vs-unknown"


class TestBuildChunkAttributes:
    """Tests for _build_chunk_attributes function."""

    def test_with_dict_attributes(self, mocker: MockerFixture) -> None:
        """Test extraction of dict attributes."""
        mock_result = mocker.Mock()
        mock_result.attributes = {"title": "My Doc", "url": "https://example.com"}

        attrs = _build_chunk_attributes(mock_result)
        assert attrs == {"title": "My Doc", "url": "https://example.com"}

    def test_with_empty_dict(self, mocker: MockerFixture) -> None:
        """Test extraction returns None for empty dict."""
        mock_result = mocker.Mock()
        mock_result.attributes = {}

        attrs = _build_chunk_attributes(mock_result)
        assert attrs is None

    def test_with_none_attributes(self, mocker: MockerFixture) -> None:
        """Test extraction returns None when no attributes."""
        mock_result = mocker.Mock()
        mock_result.attributes = None

        attrs = _build_chunk_attributes(mock_result)
        assert attrs is None

    def test_with_no_attributes_attr(self, mocker: MockerFixture) -> None:
        """Test extraction returns None when result has no attributes attr."""
        result = mocker.Mock(spec=[])
        attrs = _build_chunk_attributes(result)
        assert attrs is None


class TestExtractVectorStoreIdsFromTools:
    """Tests for extract_vector_store_ids_from_tools function."""

    def test_with_file_search_tool(self) -> None:
        """Test extraction from file_search tool definition."""
        tools = [
            {"type": "file_search", "vector_store_ids": ["vs-1", "vs-2"]},
            {"type": "mcp", "server_label": "test"},
        ]
        result = extract_vector_store_ids_from_tools(tools)
        assert result == ["vs-1", "vs-2"]

    def test_with_no_file_search(self) -> None:
        """Test extraction returns empty list when no file_search tool."""
        tools = [{"type": "mcp", "server_label": "test"}]
        result = extract_vector_store_ids_from_tools(tools)
        assert result == []

    def test_with_none_tools(self) -> None:
        """Test extraction returns empty list for None tools."""
        result = extract_vector_store_ids_from_tools(None)
        assert result == []

    def test_with_empty_tools(self) -> None:
        """Test extraction returns empty list for empty tools list."""
        result = extract_vector_store_ids_from_tools([])
        assert result == []


class TestExtractRagChunksWithIndexResolution:
    """Tests for extract_rag_chunks_from_file_search_item with index resolution."""

    def test_chunks_resolved_single_store(self, mocker: MockerFixture) -> None:
        """Test RAG chunk source is resolved with single vector store."""
        mock_result = mocker.Mock()
        mock_result.text = "content"
        mock_result.filename = "file-6376abcd"
        mock_result.score = 0.95
        mock_result.attributes = {"title": "OCP Docs"}

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.results = [mock_result]

        rag_chunks: list[RAGChunk] = []
        extract_rag_chunks_from_file_search_item(
            mock_item,
            rag_chunks,
            vector_store_ids=["vs-001"],
            rag_id_mapping={"vs-001": "ocp-4.18-docs"},
        )

        assert len(rag_chunks) == 1
        assert rag_chunks[0].source == "ocp-4.18-docs"
        assert rag_chunks[0].attributes == {"title": "OCP Docs"}
        assert rag_chunks[0].content == "content"
        assert rag_chunks[0].score == 0.95

    def test_chunks_no_mapping_falls_back(self, mocker: MockerFixture) -> None:
        """Test RAG chunk source falls back to filename when no mapping."""
        mock_result = mocker.Mock()
        mock_result.text = "content"
        mock_result.filename = "file-abc"
        mock_result.score = 0.5
        mock_result.attributes = None

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.results = [mock_result]

        rag_chunks: list[RAGChunk] = []
        extract_rag_chunks_from_file_search_item(mock_item, rag_chunks)

        assert len(rag_chunks) == 1
        assert rag_chunks[0].source is None
        assert rag_chunks[0].attributes is None

    def test_chunks_multiple_stores_attribute_resolution(
        self, mocker: MockerFixture
    ) -> None:
        """Test RAG chunk source resolved via attributes with multiple stores."""
        mock_result = mocker.Mock()
        mock_result.text = "content"
        mock_result.filename = "file-xyz"
        mock_result.score = 0.8
        mock_result.attributes = {"vector_store_id": "vs-002", "title": "RHEL"}

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.results = [mock_result]

        rag_chunks: list[RAGChunk] = []
        extract_rag_chunks_from_file_search_item(
            mock_item,
            rag_chunks,
            vector_store_ids=["vs-001", "vs-002"],
            rag_id_mapping={"vs-001": "ocp-docs", "vs-002": "rhel-9-docs"},
        )

        assert len(rag_chunks) == 1
        assert rag_chunks[0].source == "rhel-9-docs"
        assert rag_chunks[0].attributes == {
            "vector_store_id": "vs-002",
            "title": "RHEL",
        }


class TestBuildToolCallSummaryWithIndexResolution:
    """Tests for build_tool_call_summary with index resolution."""

    def test_file_search_with_mapping(self, mocker: MockerFixture) -> None:
        """Test that build_tool_call_summary passes mapping to extraction."""
        mock_result = mocker.Mock()
        mock_result.text = "chunk text"
        mock_result.filename = "file-uuid"
        mock_result.score = 0.9
        mock_result.attributes = {"title": "Doc Title"}
        mock_result.model_dump = mocker.Mock(
            return_value={
                "text": "chunk text",
                "filename": "file-uuid",
                "score": 0.9,
                "attributes": {"title": "Doc Title"},
            }
        )

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.type = "file_search_call"
        mock_item.id = "search_456"
        mock_item.queries = ["what is OCP?"]
        mock_item.results = [mock_result]
        mock_item.status = "success"

        rag_chunks: list[RAGChunk] = []
        call_summary, result_summary = build_tool_call_summary(
            mock_item,
            rag_chunks,
            vector_store_ids=["vs-001"],
            rag_id_mapping={"vs-001": "ocp-4.18-docs"},
        )

        assert len(rag_chunks) == 1
        assert rag_chunks[0].source == "ocp-4.18-docs"
        assert rag_chunks[0].attributes == {"title": "Doc Title"}
        assert call_summary is not None
        assert result_summary is not None

    def test_file_search_without_mapping(self, mocker: MockerFixture) -> None:
        """Test that build_tool_call_summary works without mapping (backward compat)."""
        mock_result = mocker.Mock()
        mock_result.text = "chunk text"
        mock_result.filename = "doc.pdf"
        mock_result.score = 0.9
        mock_result.attributes = None
        mock_result.model_dump = mocker.Mock(
            return_value={"text": "chunk text", "filename": "doc.pdf", "score": 0.9}
        )

        mock_item = mocker.Mock(spec=FileSearchCall)
        mock_item.type = "file_search_call"
        mock_item.id = "search_789"
        mock_item.queries = ["query"]
        mock_item.results = [mock_result]
        mock_item.status = "success"

        rag_chunks: list[RAGChunk] = []
        call_summary, _ = build_tool_call_summary(mock_item, rag_chunks)

        assert len(rag_chunks) == 1
        assert rag_chunks[0].source is None
        assert rag_chunks[0].attributes is None
        assert call_summary is not None


class TestParseReferencedDocumentsWithSource:
    """Tests for parse_referenced_documents with source resolution."""

    def test_single_store_source_populated(self, mocker: MockerFixture) -> None:
        """Test that source is populated on referenced documents with single store."""
        mock_result = mocker.Mock()
        mock_result.attributes = {
            "url": "https://docs.example.com/page",
            "title": "Example Page",
        }

        mock_output = mocker.Mock()
        mock_output.type = "file_search_call"
        mock_output.results = [mock_result]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output]

        docs = parse_referenced_documents(
            mock_response,
            vector_store_ids=["vs-001"],
            rag_id_mapping={"vs-001": "ocp-4.18-docs"},
        )

        assert len(docs) == 1
        assert docs[0].source == "ocp-4.18-docs"
        assert docs[0].doc_title == "Example Page"

    def test_no_mapping_source_is_none(self, mocker: MockerFixture) -> None:
        """Test that source is None when no mapping provided."""
        mock_result = mocker.Mock()
        mock_result.attributes = {"title": "Doc"}

        mock_output = mocker.Mock()
        mock_output.type = "file_search_call"
        mock_output.results = [mock_result]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output]

        docs = parse_referenced_documents(mock_response)

        assert len(docs) == 1
        assert docs[0].source is None

    def test_multiple_stores_source_is_none(self, mocker: MockerFixture) -> None:
        """Test that source is None with multiple stores (ambiguous)."""
        mock_result = mocker.Mock()
        mock_result.attributes = {"title": "Doc"}

        mock_output = mocker.Mock()
        mock_output.type = "file_search_call"
        mock_output.results = [mock_result]

        mock_response = mocker.Mock()
        mock_response.output = [mock_output]

        docs = parse_referenced_documents(
            mock_response,
            vector_store_ids=["vs-001", "vs-002"],
            rag_id_mapping={"vs-001": "ocp-docs", "vs-002": "rhel-docs"},
        )

        assert len(docs) == 1
        assert docs[0].source is None
