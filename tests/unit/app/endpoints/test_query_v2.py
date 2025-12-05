# pylint: disable=redefined-outer-name, import-error
"""Unit tests for the /query (v2) REST API endpoint using Responses API."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from litellm.exceptions import RateLimitError
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.query_v2 import (
    get_mcp_tools,
    get_rag_tools,
    query_endpoint_handler_v2,
    retrieve_response,
)
from models.config import ModelContextProtocolServer
from models.requests import Attachment, QueryRequest

# User ID must be proper UUID
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture
def dummy_request() -> Request:
    """Create a dummy FastAPI Request object for testing."""
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
    """Test get_mcp_tools generates correct tool definitions with and without auth tokens."""
    servers = [
        ModelContextProtocolServer(name="fs", url="http://localhost:3000"),
        ModelContextProtocolServer(name="git", url="https://git.example.com/mcp"),
    ]

    tools_no_token = get_mcp_tools(servers, token=None)
    assert len(tools_no_token) == 2
    assert tools_no_token[0]["type"] == "mcp"
    assert tools_no_token[0]["server_label"] == "fs"
    assert tools_no_token[0]["server_url"] == "http://localhost:3000"
    assert "headers" not in tools_no_token[0]

    tools_with_token = get_mcp_tools(servers, token="abc")
    assert len(tools_with_token) == 2
    assert tools_with_token[1]["type"] == "mcp"
    assert tools_with_token[1]["server_label"] == "git"
    assert tools_with_token[1]["server_url"] == "https://git.example.com/mcp"
    assert tools_with_token[1]["headers"] == {"Authorization": "Bearer abc"}


def test_get_mcp_tools_with_mcp_headers() -> None:
    """Test get_mcp_tools merges token auth and per-server headers correctly."""
    servers = [
        ModelContextProtocolServer(name="fs", url="http://localhost:3000"),
        ModelContextProtocolServer(name="git", url="https://git.example.com/mcp"),
    ]

    # Test with mcp_headers only (no token)
    mcp_headers = {
        "http://localhost:3000": {"X-Custom-Header": "value1"},
        "https://git.example.com/mcp": {"X-API-Key": "secret123"},
    }
    tools = get_mcp_tools(servers, token=None, mcp_headers=mcp_headers)
    assert len(tools) == 2
    assert tools[0]["headers"] == {"X-Custom-Header": "value1"}
    assert tools[1]["headers"] == {"X-API-Key": "secret123"}

    # Test with both token and mcp_headers (should merge)
    tools_merged = get_mcp_tools(servers, token="abc", mcp_headers=mcp_headers)
    assert len(tools_merged) == 2
    assert tools_merged[0]["headers"] == {
        "Authorization": "Bearer abc",
        "X-Custom-Header": "value1",
    }
    assert tools_merged[1]["headers"] == {
        "Authorization": "Bearer abc",
        "X-API-Key": "secret123",
    }

    # Test mcp_headers can override Authorization
    override_headers = {
        "http://localhost:3000": {"Authorization": "Custom auth"},
    }
    tools_override = get_mcp_tools(servers, token="abc", mcp_headers=override_headers)
    assert tools_override[0]["headers"] == {"Authorization": "Custom auth"}
    assert tools_override[1]["headers"] == {"Authorization": "Bearer abc"}


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
    # vector_stores.list should not matter when no_tools=True, but keep it valid
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    # Ensure system prompt resolution does not require real config
    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello", no_tools=True)
    summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-x", qr, token="tkn"
    )

    assert conv_id == "resp-1"
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
async def test_retrieve_response_builds_rag_and_mcp_tools(
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly builds RAG and MCP tools from configuration."""
    mock_client = mocker.Mock()
    response_obj = mocker.Mock()
    response_obj.id = "resp-2"
    response_obj.output = []
    response_obj.usage = None
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = [mocker.Mock(id="dbA")]
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mock_cfg = mocker.Mock()
    mock_cfg.mcp_servers = [
        ModelContextProtocolServer(name="fs", url="http://localhost:3000"),
    ]
    mocker.patch("app.endpoints.query_v2.configuration", mock_cfg)

    qr = QueryRequest(query="hello")
    _summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-y", qr, token="mytoken"
    )

    assert conv_id == "resp-2"
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
    assert mcp_tool["headers"] == {"Authorization": "Bearer mytoken"}


@pytest.mark.asyncio
async def test_retrieve_response_parses_output_and_tool_calls(
    mocker: MockerFixture,
) -> None:
    """Test that retrieve_response correctly parses output content and tool calls from response."""
    mock_client = mocker.Mock()

    # Build output with content variants and tool calls
    output_item_1 = mocker.Mock()
    output_item_1.type = "message"
    output_item_1.role = "assistant"
    output_item_1.content = [mocker.Mock(text="Hello "), mocker.Mock(text="world")]

    output_item_2 = mocker.Mock()
    output_item_2.type = "message"
    output_item_2.role = "assistant"
    output_item_2.content = "!"

    # Tool call as a separate output item (Responses API format)
    tool_call_item = mocker.Mock()
    tool_call_item.type = "function_call"
    tool_call_item.id = "tc-1"
    tool_call_item.name = "do_something"
    tool_call_item.arguments = {"x": 1}
    tool_call_item.status = None  # Explicitly set to avoid Mock auto-creation

    response_obj = mocker.Mock()
    response_obj.id = "resp-3"
    response_obj.output = [output_item_1, output_item_2, tool_call_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-z", qr, token="tkn"
    )

    assert conv_id == "resp-3"
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
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-usage", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-with-usage"
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
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-usage-dict", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-with-usage-dict"
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
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, token_usage = await retrieve_response(
        mock_client, "model-empty-usage", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-empty-usage"
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
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)
    # Mock shields.list
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

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

    summary = mocker.Mock(llm_response="ANSWER", tool_calls=[], rag_chunks=[])
    token_usage = mocker.Mock(input_tokens=10, output_tokens=20)
    mocker.patch(
        "app.endpoints.query_v2.retrieve_response",
        return_value=(summary, "conv-1", [], token_usage),
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
        auth=("user123", "", False, "token-abc"),
        mcp_headers={},
    )

    assert res.conversation_id == "conv-1"
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
    assert detail["response"] == "Unable to connect to Llama Stack"
    fail_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_query_endpoint_quota_exceeded(
    mocker: MockerFixture, dummy_request: Request
) -> None:
    """Test that query endpoint raises HTTP 429 when model quota is exceeded."""
    query_request = QueryRequest(
        query="What is OpenStack?",
        provider="openai",
        model="gpt-4-turbo",
        attachments=[],
    )  # type: ignore
    mock_client = mocker.AsyncMock()
    mock_client.responses.create.side_effect = RateLimitError(
        model="gpt-4-turbo", llm_provider="openai", message=""
    )
    mocker.patch(
        "app.endpoints.query.select_model_and_provider_id",
        return_value=("openai/gpt-4-turbo", "gpt-4-turbo", "openai"),
    )
    mocker.patch("app.endpoints.query.validate_model_provider_override")
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client",
        return_value=mock_client,
    )

    with pytest.raises(HTTPException) as exc_info:
        await query_endpoint_handler_v2(
            dummy_request, query_request=query_request, auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "The model quota has been exceeded"  # type: ignore
    assert "gpt-4-turbo" in detail["cause"]  # type: ignore


@pytest.mark.asyncio
async def test_retrieve_response_with_shields_available(mocker: MockerFixture) -> None:
    """Test that shields are listed and passed to responses API when available."""
    mock_client = mocker.Mock()

    # Mock shields.list to return available shields
    shield1 = mocker.Mock()
    shield1.identifier = "shield-1"
    shield2 = mocker.Mock()
    shield2.identifier = "shield-2"
    mock_client.shields.list = mocker.AsyncMock(return_value=[shield1, shield2])

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Safe response"

    response_obj = mocker.Mock()
    response_obj.id = "resp-shields"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-shields", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-shields"
    assert summary.llm_response == "Safe response"

    # Verify that shields were passed in extra_body
    kwargs = mock_client.responses.create.call_args.kwargs
    assert "extra_body" in kwargs
    assert "guardrails" in kwargs["extra_body"]
    assert kwargs["extra_body"]["guardrails"] == ["shield-1", "shield-2"]


@pytest.mark.asyncio
async def test_retrieve_response_with_no_shields_available(
    mocker: MockerFixture,
) -> None:
    """Test that no extra_body is added when no shields are available."""
    mock_client = mocker.Mock()

    # Mock shields.list to return no shields
    mock_client.shields.list = mocker.AsyncMock(return_value=[])

    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Response without shields"

    response_obj = mocker.Mock()
    response_obj.id = "resp-no-shields"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-no-shields", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-no-shields"
    assert summary.llm_response == "Response without shields"

    # Verify that no extra_body was added
    kwargs = mock_client.responses.create.call_args.kwargs
    assert "extra_body" not in kwargs


@pytest.mark.asyncio
async def test_retrieve_response_detects_shield_violation(
    mocker: MockerFixture,
) -> None:
    """Test that shield violations are detected and metrics are incremented."""
    mock_client = mocker.Mock()

    # Mock shields.list to return available shields
    shield1 = mocker.Mock()
    shield1.identifier = "safety-shield"
    mock_client.shields.list = mocker.AsyncMock(return_value=[shield1])

    # Create output with shield violation (refusal)
    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "I cannot help with that request"
    output_item.refusal = "Content violates safety policy"

    response_obj = mocker.Mock()
    response_obj.id = "resp-violation"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    # Mock the validation error metric
    validation_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    qr = QueryRequest(query="dangerous query")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-violation", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-violation"
    assert summary.llm_response == "I cannot help with that request"

    # Verify that the validation error metric was incremented
    validation_metric.inc.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_response_no_violation_with_shields(
    mocker: MockerFixture,
) -> None:
    """Test that no metric is incremented when there's no shield violation."""
    mock_client = mocker.Mock()

    # Mock shields.list to return available shields
    shield1 = mocker.Mock()
    shield1.identifier = "safety-shield"
    mock_client.shields.list = mocker.AsyncMock(return_value=[shield1])

    # Create output without shield violation
    output_item = mocker.Mock()
    output_item.type = "message"
    output_item.role = "assistant"
    output_item.content = "Safe response"
    output_item.refusal = None  # No violation

    response_obj = mocker.Mock()
    response_obj.id = "resp-safe"
    response_obj.output = [output_item]
    response_obj.usage = None

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.data = []
    mock_client.vector_stores.list = mocker.AsyncMock(return_value=mock_vector_stores)

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    # Mock the validation error metric
    validation_metric = mocker.patch("metrics.llm_calls_validation_errors_total")

    qr = QueryRequest(query="safe query")
    summary, conv_id, _referenced_docs, _token_usage = await retrieve_response(
        mock_client, "model-safe", qr, token="tkn", provider_id="test-provider"
    )

    assert conv_id == "resp-safe"
    assert summary.llm_response == "Safe response"

    # Verify that the validation error metric was NOT incremented
    validation_metric.inc.assert_not_called()
