# pylint: disable=redefined-outer-name, import-error,too-many-locals,too-many-lines
# pyright: reportCallIssue=false
"""Unit tests for the /query (v2) REST API endpoint using Responses API."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, Request, status
import httpx
from llama_stack_client import APIConnectionError, RateLimitError
from pytest_mock import MockerFixture

from app.endpoints.query_v2 import (
    get_mcp_tools,
    get_rag_tools,
    query_endpoint_handler_v2,
    retrieve_response,
)
from models.config import ModelContextProtocolServer
from models.requests import Attachment, QueryRequest
from utils.types import ShieldModerationResult

# User ID must be proper UUID
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture
def dummy_request() -> Request:
    """Create a dummy FastAPI Request object for testing.

    Create a minimal FastAPI Request object suitable for unit tests.

    Returns:
        request (fastapi.Request): A Request constructed with a bare HTTP scope
        (type "http") for use in tests.
    """
    req = Request(scope={"type": "http"})
    return req


def test_get_rag_tools() -> None:
    """Test get_rag_tools returns None for empty list and correct tool format for vector stores."""
    assert get_rag_tools([]) is None

    tools = get_rag_tools(["db1", "db2"])
    assert isinstance(tools, list)
    assert tools[0]["type"] == "file_search"
    assert tools[0]["vector_store_ids"] == ["db1", "db2"]
    assert tools[0]["max_num_results"] == 10


def test_get_mcp_tools_with_and_without_token() -> None:
    """Test get_mcp_tools with resolved_authorization_headers."""
    # Servers without authorization headers
    servers_no_auth = [
        ModelContextProtocolServer(
            name="fs",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
        ),
        ModelContextProtocolServer(
            name="git",
            provider_id="model-context-protocol",
            url="https://git.example.com/mcp",
        ),
    ]

    tools_no_auth = get_mcp_tools(servers_no_auth, token=None)
    assert len(tools_no_auth) == 2
    assert tools_no_auth[0]["type"] == "mcp"
    assert tools_no_auth[0]["server_label"] == "fs"
    assert tools_no_auth[0]["server_url"] == "http://localhost:3000"
    assert "headers" not in tools_no_auth[0]

    # Servers with kubernetes auth
    servers_k8s = [
        ModelContextProtocolServer(
            name="k8s-server",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={"Authorization": "kubernetes"},
        ),
    ]
    tools_k8s = get_mcp_tools(servers_k8s, token="user-k8s-token")
    assert len(tools_k8s) == 1
    assert tools_k8s[0]["authorization"] == "Bearer user-k8s-token"
    assert "headers" not in tools_k8s[0]  # No other headers


def test_get_mcp_tools_with_mcp_headers() -> None:
    """Test get_mcp_tools with client-provided headers."""
    # Server with client auth
    servers = [
        ModelContextProtocolServer(
            name="fs",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={"Authorization": "client", "X-Custom": "client"},
        ),
    ]

    # Test with mcp_headers provided
    mcp_headers = {
        "fs": {
            "Authorization": "client-provided-token",
            "X-Custom": "custom-value",
        }
    }
    tools = get_mcp_tools(servers, token=None, mcp_headers=mcp_headers)
    assert len(tools) == 1
    assert tools[0]["authorization"] == "client-provided-token"
    assert tools[0]["headers"] == {
        "X-Custom": "custom-value",
    }

    # Test with mcp_headers=None (server should be skipped since auth is required but unavailable)
    tools_no_headers = get_mcp_tools(servers, token=None, mcp_headers=None)
    assert len(tools_no_headers) == 0  # Server skipped due to missing required auth


def test_get_mcp_tools_with_static_headers(tmp_path: Path) -> None:
    """Test get_mcp_tools with static headers from config files."""
    # Create a secret file
    secret_file = tmp_path / "token.txt"
    secret_file.write_text("static-secret-token")

    servers = [
        ModelContextProtocolServer(
            name="server1",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={"Authorization": str(secret_file)},
        ),
    ]

    tools = get_mcp_tools(servers, token=None)
    assert len(tools) == 1
    assert tools[0]["authorization"] == "static-secret-token"
    assert "headers" not in tools[0]  # No other headers


def test_get_mcp_tools_with_mixed_headers(tmp_path: Path) -> None:
    """Test get_mcp_tools with mixed header types."""
    # Create a secret file
    secret_file = tmp_path / "api-key.txt"
    secret_file.write_text("secret-api-key")

    servers = [
        ModelContextProtocolServer(
            name="mixed-server",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={
                "Authorization": "kubernetes",
                "X-API-Key": str(secret_file),
                "X-Custom": "client",
            },
        ),
    ]

    mcp_headers = {
        "mixed-server": {
            "X-Custom": "client-custom-value",
        }
    }

    tools = get_mcp_tools(servers, token="k8s-token", mcp_headers=mcp_headers)
    assert len(tools) == 1
    assert tools[0]["authorization"] == "Bearer k8s-token"
    assert tools[0]["headers"] == {
        "X-API-Key": "secret-api-key",
        "X-Custom": "client-custom-value",
    }


def test_get_mcp_tools_skips_server_with_missing_auth() -> None:
    """Test that servers with required but unavailable auth headers are skipped."""
    servers = [
        # Server with kubernetes auth but no token provided
        ModelContextProtocolServer(
            name="missing-k8s-auth",
            provider_id="model-context-protocol",
            url="http://localhost:3001",
            authorization_headers={"Authorization": "kubernetes"},
        ),
        # Server with client auth but no MCP-HEADERS provided
        ModelContextProtocolServer(
            name="missing-client-auth",
            provider_id="model-context-protocol",
            url="http://localhost:3002",
            authorization_headers={"X-Token": "client"},
        ),
        # Server with partial auth (2 headers required, only 1 available)
        ModelContextProtocolServer(
            name="partial-auth",
            provider_id="model-context-protocol",
            url="http://localhost:3003",
            authorization_headers={
                "Authorization": "kubernetes",
                "X-Custom": "client",
            },
        ),
    ]

    # No token, no mcp_headers
    tools = get_mcp_tools(servers, token=None, mcp_headers=None)
    # All servers should be skipped
    assert len(tools) == 0


def test_get_mcp_tools_includes_server_without_auth() -> None:
    """Test that servers without auth config are always included."""
    servers = [
        # Server with no auth requirements
        ModelContextProtocolServer(
            name="public-server",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={},
        ),
    ]

    # Should work even without token or headers
    tools = get_mcp_tools(servers, token=None, mcp_headers=None)
    assert len(tools) == 1
    assert tools[0]["server_label"] == "public-server"
    assert "headers" not in tools[0]


@pytest.mark.asyncio
async def test_retrieve_response_no_tools_bypasses_tools(mocker: MockerFixture) -> None:
    """Test that no_tools=True bypasses tool configuration and passes None to responses API."""
    mock_client = mocker.Mock()
    # responses.create returns a synthetic OpenAI-like response
    response_obj = mocker.Mock()
    response_obj.id = "resp-1"
    response_obj.output = []
    response_obj.usage = None  # No usage info
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    # vector_stores.list should not matter when no_tools=True, but keep it valid
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    # Ensure system prompt resolution does not require real config
    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello", no_tools=True)
    summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-x", qr, token="tkn"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == ""
    assert referenced_docs == []
    assert token_usage.input_tokens == 0  # No usage info, so 0
    assert token_usage.output_tokens == 0
    # tools must be passed as None
    kwargs = mock_client.responses.create.call_args.kwargs
    assert kwargs["tools"] is None
    assert kwargs["model"] == "model-x"
    assert kwargs["instructions"] == "PROMPT"


@pytest.mark.asyncio
async def test_retrieve_response_builds_rag_and_mcp_tools(  # pylint: disable=too-many-locals
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly builds RAG and MCP tools from configuration."""
    mock_client = mocker.Mock()
    response_obj = mocker.Mock()
    response_obj.id = "resp-2"
    response_obj.output = []
    response_obj.usage = None
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = [mocker.Mock(id="dbA")]
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mock_cfg = mocker.Mock()
    mock_cfg.mcp_servers = [
        ModelContextProtocolServer(
            name="fs",
            provider_id="model-context-protocol",
            url="http://localhost:3000",
            authorization_headers={"Authorization": "kubernetes"},
        ),
    ]
    mocker.patch("app.endpoints.query_v2.configuration", mock_cfg)

    qr = QueryRequest(query="hello")
    _summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-y", qr, token="mytoken"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert referenced_docs == []
    assert token_usage.input_tokens == 0  # No usage info, so 0
    assert token_usage.output_tokens == 0

    kwargs = mock_client.responses.create.call_args.kwargs
    tools = kwargs["tools"]
    assert isinstance(tools, list)
    # Expect one file_search and one mcp tool
    tool_types = {t.get("type") for t in tools}
    assert tool_types == {"file_search", "mcp"}
    file_search = next(t for t in tools if t["type"] == "file_search")
    assert file_search["vector_store_ids"] == ["dbA"]
    mcp_tool = next(t for t in tools if t["type"] == "mcp")
    assert mcp_tool["server_label"] == "fs"
    assert mcp_tool["authorization"] == "Bearer mytoken"
    assert "headers" not in mcp_tool  # Authorization is separate


@pytest.mark.asyncio
async def test_retrieve_response_parses_output_and_tool_calls(
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly parses output content and tool calls from response."""
    mock_client = mocker.Mock()

    # Build output with content variants and tool calls
    part1 = mocker.Mock(text="Hello ")
    part1.annotations = []  # Ensure annotations is a list to avoid iteration error
    part2 = mocker.Mock(text="world")
    part2.annotations = []

    output_item_1 = mocker.Mock()
    output_item_1.type = "message"
    output_item_1.role = "assistant"
    output_item_1.content = [part1, part2]

    output_item_2 = mocker.Mock()
    output_item_2.type = "message"
    output_item_2.role = "assistant"
    output_item_2.content = "!"

    # Tool call as a separate output item (Responses API format)
    tool_call_item = mocker.Mock()
    tool_call_item.type = "function_call"
    tool_call_item.id = "tc-1"
    tool_call_item.call_id = "tc-1"
    tool_call_item.name = "do_something"
    tool_call_item.arguments = '{"x": 1}'
    tool_call_item.status = None  # Explicitly set to avoid Mock auto-creation

    response_obj = mocker.Mock()
    response_obj.id = "resp-3"
    response_obj.output = [output_item_1, output_item_2, tool_call_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-z", qr, token="tkn"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Hello world!"
    assert len(summary.tool_calls) == 1
    assert summary.tool_calls[0].id == "tc-1"
    assert summary.tool_calls[0].name == "do_something"
    assert summary.tool_calls[0].args == {"x": 1}
    assert referenced_docs == []
    assert token_usage.input_tokens == 0  # No usage info, so 0
    assert token_usage.output_tokens == 0


@pytest.mark.asyncio
async def test_retrieve_response_with_usage_info(mocker: MockerFixture) -> None:
    """Test that token usage is extracted when provided by the API as an object."""
    mock_client = mocker.Mock()

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Test response"
    output_item.tool_calls = []

    # Mock usage information as object
    mock_usage = mocker.Mock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 75

    response_obj = mocker.Mock()
    response_obj.id = "resp-with-usage"
    response_obj.output = [output_item]
    response_obj.usage = mock_usage

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-usage", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Test response"
    assert token_usage.input_tokens == 150
    assert token_usage.output_tokens == 75
    assert token_usage.llm_calls == 1


@pytest.mark.asyncio
async def test_retrieve_response_with_usage_dict(mocker: MockerFixture) -> None:
    """Test that token usage is extracted when provided by the API as a dict."""
    mock_client = mocker.Mock()

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Test response dict"
    output_item.tool_calls = []

    # Mock usage information as dict (like llama stack does)
    response_obj = mocker.Mock()
    response_obj.id = "resp-with-usage-dict"
    response_obj.output = [output_item]
    response_obj.usage = {"input_tokens": 200, "output_tokens": 100}

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-usage-dict", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Test response dict"
    assert token_usage.input_tokens == 200
    assert token_usage.output_tokens == 100
    assert token_usage.llm_calls == 1


@pytest.mark.asyncio
async def test_retrieve_response_with_empty_usage_dict(mocker: MockerFixture) -> None:
    """Test that empty usage dict is handled gracefully."""
    mock_client = mocker.Mock()

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Test response empty usage"
    output_item.tool_calls = []

    # Mock usage information as empty dict (tokens are 0 or missing)
    response_obj = mocker.Mock()
    response_obj.id = "resp-empty-usage"
    response_obj.output = [output_item]
    response_obj.usage = {}  # Empty dict

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-empty-usage", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Test response empty usage"
    assert token_usage.input_tokens == 0
    assert token_usage.output_tokens == 0
    assert token_usage.llm_calls == 1  # Always 1, even when no token usage data


@pytest.mark.asyncio
async def test_retrieve_response_validates_attachments(mocker: MockerFixture) -> None:
    """Test that retrieve_response validates attachments and includes them in the input string."""
    mock_client = mocker.Mock()
    response_obj = mocker.Mock()
    response_obj.id = "resp-4"
    response_obj.output = []
    response_obj.usage = None
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    validate_spy = mocker.patch(
        "app.endpoints.query_v2.validate_attachments_metadata", return_value=None
    )

    attachments = [
        Attachment(attachment_type="log", content_type="text/plain", content="x"),
    ]

    qr = QueryRequest(query="hello", attachments=attachments)
    _summary, _cid, _ref_docs, _token_usage = await retrieve_response(
        mock_client, "model-a", qr, token="tkn"
    )

    validate_spy.assert_called_once()
    # Verify that attachments are included in the input
    kwargs = mock_client.responses.create.call_args.kwargs
    assert "input" in kwargs
    # Input should be a string containing both query and attachment
    assert isinstance(kwargs["input"], str)
    assert "hello" in kwargs["input"]
    assert "[Attachment: log]" in kwargs["input"]
    assert "x" in kwargs["input"]


@pytest.mark.asyncio
async def test_query_endpoint_handler_v2_success(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test successful query endpoint handler execution with proper response structure."""
    # Mock configuration to avoid configuration not loaded errors
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mock_config.quota_limiters = []
    mocker.patch("app.endpoints.query_v2.configuration", mock_config)

    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch("app.endpoints.query.evaluate_model_hints", return_value=(None, None))
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("llama/m", "m", "p"),
    )

    summary = mocker.Mock(
        llm_response="ANSWER", tool_calls=[], tool_results=[], rag_chunks=[]
    )
    token_usage = mocker.Mock(input_tokens=10, output_tokens=20)
    # Use a valid SUID for conversation_id
    test_conversation_id = "00000000-0000-0000-0000-000000000001"
    mocker.patch(
        "app.endpoints.query_v2.retrieve_response",
        return_value=(summary, test_conversation_id, [], token_usage),
    )
    mocker.patch("app.endpoints.query_v2.get_topic_summary", return_value="Topic")
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)
    mocker.patch("app.endpoints.query.persist_user_conversation_details")
    mocker.patch("utils.endpoints.store_conversation_into_cache")
    mocker.patch("app.endpoints.query.get_session")

    # Add missing mocks for quota functions
    mocker.patch("utils.quota.check_tokens_available")
    mocker.patch("utils.quota.consume_tokens")
    mocker.patch("utils.quota.get_available_quotas", return_value={})

    # Mock the request state
    dummy_request.state.authorized_actions = []

    res = await query_endpoint_handler_v2(
        request=dummy_request,
        query_request=QueryRequest(query="hi"),
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert res.conversation_id == test_conversation_id
    assert res.response == "ANSWER"


@pytest.mark.asyncio
async def test_query_endpoint_handler_v2_api_connection_error(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that query endpoint handler properly handles and reports API connection errors."""
    # Mock configuration to avoid configuration not loaded errors
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.query_v2.configuration", mock_config)

    def _raise(*_args: Any, **_kwargs: Any) -> Exception:
        """Raises a custom APIConnectionError exception.

        Args:
            *_args: Variable length argument list.
            **_kwargs: Arbitrary keyword arguments.

        Returns:
            None

        Raises:
            APIConnectionError: Always raises this exception with a Request object.
        """
        request = Request(scope={"type": "http"})
        raise APIConnectionError(request=request)  # type: ignore

    mocker.patch("client.AsyncLlamaStackClientHolder.get_client", side_effect=_raise)

    fail_metric = mocker.patch("metrics.llm_calls_failures_total")

    with pytest.raises(HTTPException) as exc:
        await query_endpoint_handler_v2(
            request=dummy_request,
            query_request=QueryRequest(query="hi"),
            auth=("user123", "", False, "token-abc"),
            mcp_headers={},
        )

    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore[index]
    fail_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_query_endpoint_quota_exceeded(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that query endpoint raises HTTP 429 when model quota is exceeded."""
    query_request = QueryRequest(
        query="What is OpenStack?",
        provider="openai",
        model="gpt-4o-mini",
        attachments=[],
    )  # type: ignore
    mock_client = mocker.AsyncMock()
    mock_client.models.list = mocker.AsyncMock(return_value=[])
    mock_response = httpx.Response(429, request=httpx.Request("POST", "http://test"))
    mock_client.responses.create.side_effect = RateLimitError(
        "Rate limit exceeded for model gpt-4o-mini",
        response=mock_response,
        body=None,
    )
    # Mock conversation creation (needed for query_v2)
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("openai/gpt-4o-mini", "gpt-4o-mini", "openai"),
    )
    mocker.patch("app.endpoints.query.validate_model_provider_override")
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client",
        return_value=mock_client,
    )
    mocker.patch("app.endpoints.query.check_tokens_available")
    mocker.patch("app.endpoints.query.get_session")
    mocker.patch("app.endpoints.query.is_transcripts_enabled", return_value=False)
    mocker.patch(
        "app.endpoints.query_v2.run_shield_moderation",
        return_value=ShieldModerationResult(blocked=False),
    )
    mocker.patch(
        "app.endpoints.query_v2.prepare_tools_for_responses_api", return_value=None
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler_v2(
            dummy_request, query_request=query_request, auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "The quota has been exceeded"  # type: ignore
    assert "gpt-4o-mini" in detail["cause"]  # type: ignore


@pytest.mark.asyncio
async def test_retrieve_response_with_shields_available(mocker: MockerFixture) -> None:
    """Test that shield moderation runs and passes when content is safe."""
    mock_client = mocker.Mock()

    # Create mock shield with provider_resource_id
    mock_shield = mocker.Mock()
    mock_shield.identifier = "content-safety-shield"
    mock_shield.provider_resource_id = "moderation-model"
    mock_client.shields.list = mocker.AsyncMock(return_value=[mock_shield])

    # Create mock model matching the shield's provider_resource_id
    mock_model = mocker.Mock()
    mock_model.id = "moderation-model"
    mock_client.models.list = mocker.AsyncMock(return_value=[mock_model])

    # Mock moderations.create to return safe (not flagged) content
    mock_moderation_result = mocker.Mock()
    mock_moderation_result.flagged = False
    mock_moderation_response = mocker.Mock()
    mock_moderation_response.results = [mock_moderation_result]
    mock_client.moderations.create = mocker.AsyncMock(
        return_value=mock_moderation_response
    )

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Safe response"

    response_obj = mocker.Mock()
    response_obj.id = "resp-shields"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-shields", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Safe response"

    # Verify that moderation was called with the user's query
    mock_client.moderations.create.assert_called_once_with(
        input="hello", model="moderation-model"
    )
    # Verify that responses.create was called (moderation passed)
    mock_client.responses.create.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_response_with_no_shields_available(
    mocker: MockerFixture,
) -> None:
    """Test that LLM is called when no shields are configured."""
    mock_client = mocker.Mock()

    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Response without shields"

    response_obj = mocker.Mock()
    response_obj.id = "resp-no-shields"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-no-shields", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Response without shields"

    # Verify that responses.create was called
    mock_client.responses.create.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_response_detects_shield_violation(
    mocker: MockerFixture,
) -> None:
    """Test that shield moderation blocks content and returns early."""
    mock_client = mocker.Mock()

    # Mock conversations.create for new conversation creation
    mock_conversation = mocker.Mock()
    mock_conversation.id = "conv_abc123def456"
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)
    mock_client.conversations.items.create = mocker.AsyncMock(return_value=None)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    # Mock run_shield_moderation to return blocked
    mocker.patch(
        "app.endpoints.query_v2.run_shield_moderation",
        return_value=ShieldModerationResult(
            blocked=True, message="Content violates safety policy"
        ),
    )

    qr = QueryRequest(query="dangerous query")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-violation", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "abc123def456"  # Normalized (without conv_ prefix)
    assert summary.llm_response == "Content violates safety policy"

    # Verify that responses.create was NOT called (blocked by moderation)
    mock_client.responses.create.assert_not_called()


def _create_message_output_with_citations(mocker: MockerFixture) -> Any:
    """Create mock message output item with content annotations (citations)."""
    # 1. Output item with message content annotations (citations)
    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"

    # Mock content with annotations
    content_part = mocker.Mock()
    content_part.type = "output_text"
    content_part.text = "Here is a citation."

    annotation1 = mocker.Mock()
    annotation1.type = "url_citation"
    annotation1.url = "http://example.com/doc1"
    annotation1.title = "Doc 1"

    annotation2 = mocker.Mock()
    annotation2.type = "file_citation"
    annotation2.filename = "file1.txt"
    annotation2.url = None
    annotation2.title = None

    content_part.annotations = [annotation1, annotation2]
    output_item.content = [content_part]
    return output_item


def _create_file_search_output(mocker: MockerFixture) -> Any:
    """Create mock file search tool call output with results."""
    # 2. Output item with file search tool call results
    output_item = mocker.Mock()
    output_item.type = "file_search_call"
    output_item.id = "file-search-1"
    output_item.queries = (
        []
    )  # Ensure queries is a list to avoid iteration error in tool summary
    output_item.status = "completed"
    # Create mock result objects with proper attributes matching real llama-stack response
    result_1 = mocker.Mock()
    result_1.filename = "file2.pdf"
    result_1.attributes = {
        "docs_url": "http://example.com/doc2",
        "title": "Title 1",
        "document_id": "doc-123",
    }
    result_1.text = "Sample text from file2.pdf"
    result_1.score = 0.95
    result_1.file_id = "file-123"
    result_1.model_dump = mocker.Mock(
        return_value={
            "filename": "file2.pdf",
            "attributes": {
                "docs_url": "http://example.com/doc2",
                "title": "Title 1",
                "document_id": "doc-123",
            },
            "text": "Sample text from file2.pdf",
            "score": 0.95,
            "file_id": "file-123",
        }
    )

    result_2 = mocker.Mock()
    result_2.filename = "file3.docx"
    result_2.attributes = {
        "docs_url": "http://example.com/doc3",
        "title": "Title 2",
        "document_id": "doc-456",
    }
    result_2.text = "Sample text from file3.docx"
    result_2.score = 0.85
    result_2.file_id = "file-456"
    result_2.model_dump = mocker.Mock(
        return_value={
            "filename": "file3.docx",
            "attributes": {
                "docs_url": "http://example.com/doc3",
                "title": "Title 2",
                "document_id": "doc-456",
            },
            "text": "Sample text from file3.docx",
            "score": 0.85,
            "file_id": "file-456",
        }
    )

    output_item.results = [result_1, result_2]
    return output_item


@pytest.mark.asyncio
async def test_retrieve_response_parses_referenced_documents(
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly parses referenced documents from response."""
    mock_client = mocker.AsyncMock()

    # Create output items using helper functions
    output_item_1 = _create_message_output_with_citations(mocker)
    output_item_2 = _create_file_search_output(mocker)

    response_obj = mocker.Mock()
    response_obj.id = "resp-docs"
    response_obj.output = [output_item_1, output_item_2]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list and models.list for run_shield_moderation
    mock_client.shields.list = mocker.AsyncMock(return_value=[])
    mock_client.models.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="query with docs")
    _summary, _conv_id, referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-docs", qr, token="tkn", provider_id="test-provider"
    )

    # Referenced documents are now extracted only from file_search_call attributes
    assert len(referenced_docs) == 2

    # Verify Title 1 (File search result with URL)
    doc1 = next((d for d in referenced_docs if d.doc_title == "Title 1"), None)
    assert doc1
    assert doc1.doc_title == "Title 1"
    assert str(doc1.doc_url) == "http://example.com/doc2"

    # Verify Title 2 (File search result with URL)
    doc2 = next((d for d in referenced_docs if d.doc_title == "Title 2"), None)
    assert doc2
    assert doc2.doc_title == "Title 2"
    assert str(doc2.doc_url) == "http://example.com/doc3"

    # Verify RAG chunks were extracted from file_search_call results
    assert len(_summary.rag_chunks) == 2
    assert _summary.rag_chunks[0].content == "Sample text from file2.pdf"
    assert _summary.rag_chunks[0].source == "file2.pdf"
    assert _summary.rag_chunks[0].score == 0.95
    assert _summary.rag_chunks[1].content == "Sample text from file3.docx"
    assert _summary.rag_chunks[1].source == "file3.docx"
    assert _summary.rag_chunks[1].score == 0.85
