# pylint: disable=redefined-outer-name, import-error
"""Unit tests for the /query (v2) REST API endpoint using Responses API."""

import pytest
from fastapi import HTTPException, status, Request

from llama_stack_client import APIConnectionError

from models.requests import QueryRequest, Attachment
from models.config import ModelContextProtocolServer

from app.endpoints.query_v2 import (
    get_rag_tools,
    get_mcp_tools,
    retrieve_response,
    query_endpoint_handler_v2,
)


@pytest.fixture
def dummy_request() -> Request:
    req = Request(scope={"type": "http"})
    return req


def test_get_rag_tools():
    assert get_rag_tools([]) is None

    tools = get_rag_tools(["db1", "db2"])
    assert isinstance(tools, list)
    assert tools[0]["type"] == "file_search"
    assert tools[0]["vector_store_ids"] == ["db1", "db2"]
    assert tools[0]["max_num_results"] == 10


def test_get_mcp_tools_with_and_without_token():
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


@pytest.mark.asyncio
async def test_retrieve_response_no_tools_bypasses_tools(mocker):
    mock_client = mocker.Mock()
    # responses.create returns a synthetic OpenAI-like response
    response_obj = mocker.Mock()
    response_obj.id = "resp-1"
    response_obj.output = []
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    # vector_dbs.list should not matter when no_tools=True, but keep it valid
    mock_client.vector_dbs.list = mocker.AsyncMock(return_value=[])

    # Ensure system prompt resolution does not require real config
    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello", no_tools=True)
    summary, conv_id = await retrieve_response(mock_client, "model-x", qr, token="tkn")

    assert conv_id == "resp-1"
    assert summary.llm_response == ""
    # tools must be passed as None
    kwargs = mock_client.responses.create.call_args.kwargs
    assert kwargs["tools"] is None
    assert kwargs["model"] == "model-x"
    assert kwargs["instructions"] == "PROMPT"


@pytest.mark.asyncio
async def test_retrieve_response_builds_rag_and_mcp_tools(mocker):
    mock_client = mocker.Mock()
    response_obj = mocker.Mock()
    response_obj.id = "resp-2"
    response_obj.output = []
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_client.vector_dbs.list = mocker.AsyncMock(
        return_value=[mocker.Mock(identifier="dbA")]
    )

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mock_cfg = mocker.Mock()
    mock_cfg.mcp_servers = [
        ModelContextProtocolServer(name="fs", url="http://localhost:3000"),
    ]
    mocker.patch("app.endpoints.query_v2.configuration", mock_cfg)

    qr = QueryRequest(query="hello")
    await retrieve_response(mock_client, "model-y", qr, token="mytoken")

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
async def test_retrieve_response_parses_output_and_tool_calls(mocker):
    mock_client = mocker.Mock()

    # Build output with content variants and tool calls
    tool_call_fn = mocker.Mock(name="fn")
    tool_call_fn.name = "do_something"
    tool_call_fn.arguments = {"x": 1}
    tool_call = mocker.Mock()
    tool_call.id = "tc-1"
    tool_call.function = tool_call_fn

    output_item_1 = mocker.Mock()
    output_item_1.content = [mocker.Mock(text="Hello "), mocker.Mock(text="world")]
    output_item_1.tool_calls = []

    output_item_2 = mocker.Mock()
    output_item_2.content = "!"
    output_item_2.tool_calls = [tool_call]

    response_obj = mocker.Mock()
    response_obj.id = "resp-3"
    response_obj.output = [output_item_1, output_item_2]

    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_client.vector_dbs.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    qr = QueryRequest(query="hello")
    summary, conv_id = await retrieve_response(mock_client, "model-z", qr, token="tkn")

    assert conv_id == "resp-3"
    assert summary.llm_response == "Hello world!"
    assert len(summary.tool_calls) == 1
    assert summary.tool_calls[0].id == "tc-1"
    assert summary.tool_calls[0].name == "do_something"
    assert summary.tool_calls[0].args == {"x": 1}


@pytest.mark.asyncio
async def test_retrieve_response_validates_attachments(mocker):
    mock_client = mocker.Mock()
    response_obj = mocker.Mock()
    response_obj.id = "resp-4"
    response_obj.output = []
    mock_client.responses.create = mocker.AsyncMock(return_value=response_obj)
    mock_client.vector_dbs.list = mocker.AsyncMock(return_value=[])

    mocker.patch("app.endpoints.query_v2.get_system_prompt", return_value="PROMPT")
    mocker.patch("app.endpoints.query_v2.configuration", mocker.Mock(mcp_servers=[]))

    validate_spy = mocker.patch(
        "app.endpoints.query_v2.validate_attachments_metadata", return_value=None
    )

    attachments = [
        Attachment(attachment_type="log", content_type="text/plain", content="x"),
    ]

    qr = QueryRequest(query="hello", attachments=attachments)
    _summary, _cid = await retrieve_response(mock_client, "model-a", qr, token="tkn")

    validate_spy.assert_called_once()


@pytest.mark.asyncio
async def test_query_endpoint_handler_v2_success(mocker, dummy_request):
    # Mock configuration to avoid configuration not loaded errors
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.query_v2.configuration", mock_config)

    mock_client = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mocker.Mock()])
    mocker.patch(
        "client.AsyncLlamaStackClientHolder.get_client", return_value=mock_client
    )
    mocker.patch(
        "app.endpoints.query_v2.evaluate_model_hints", return_value=(None, None)
    )
    mocker.patch(
        "app.endpoints.query_v2.select_model_and_provider_id",
        return_value=("llama/m", "m", "p"),
    )

    summary = mocker.Mock(llm_response="ANSWER", tool_calls=[])
    mocker.patch(
        "app.endpoints.query_v2.retrieve_response",
        return_value=(summary, "conv-1"),
    )
    mocker.patch(
        "app.endpoints.query_v2.process_transcript_and_persist_conversation",
        return_value=None,
    )

    metric = mocker.patch("metrics.llm_calls_total")

    res = await query_endpoint_handler_v2(
        request=dummy_request,
        query_request=QueryRequest(query="hi"),
        auth=("user123", "", False, "token-abc"),
        mcp_headers={},
    )

    assert res.conversation_id == "conv-1"
    assert res.response == "ANSWER"
    metric.labels("p", "m").inc.assert_called_once()


@pytest.mark.asyncio
async def test_query_endpoint_handler_v2_api_connection_error(mocker, dummy_request):
    # Mock configuration to avoid configuration not loaded errors
    mock_config = mocker.Mock()
    mock_config.llama_stack_configuration = mocker.Mock()
    mocker.patch("app.endpoints.query_v2.configuration", mock_config)

    def _raise(*_args, **_kwargs):
        raise APIConnectionError(request=None)

    mocker.patch("client.AsyncLlamaStackClientHolder.get_client", side_effect=_raise)

    fail_metric = mocker.patch("metrics.llm_calls_failures_total")

    with pytest.raises(HTTPException) as exc:
        await query_endpoint_handler_v2(
            request=dummy_request,
            query_request=QueryRequest(query="hi"),
            auth=("user123", "", False, "token-abc"),
            mcp_headers={},
        )

    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unable to connect to Llama Stack" in str(exc.value.detail)
    fail_metric.inc.assert_called_once()
