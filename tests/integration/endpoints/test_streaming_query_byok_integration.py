"""Integration tests for /streaming_query endpoint BYOK inline and tool RAG functionality."""

# pylint: disable=too-many-lines

import json
from collections.abc import AsyncIterator, Generator
from typing import Any

import pytest
from fastapi import Request, status
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import OpenAIResponseObject
from pytest_mock import AsyncMockType, MockerFixture

import constants
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import QueryRequest
from tests.integration.endpoints.test_query_byok_integration import (
    _build_base_mock_client,
    _make_byok_vector_io_response,
    _make_vector_io_response,
)


async def _collect_sse_events(response: StreamingResponse) -> list[dict[str, Any]]:
    """Consume a StreamingResponse and parse SSE events into dicts.

    Parameters:
        response: The StreamingResponse to consume.

    Returns:
        List of parsed JSON event dicts from ``data:`` lines.
    """
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
        for line in text.strip().splitlines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


def _build_base_streaming_mock_client(mocker: MockerFixture) -> Any:
    """Build a base mock Llama Stack client configured for streaming responses.

    Extends the base query mock client with streaming-specific stubs:
    conversations.items.create and a streaming responses.create.
    """
    mock_client = _build_base_mock_client(mocker)

    # Streaming additions
    mock_client.conversations.items.create = mocker.AsyncMock()

    async def _mock_stream() -> AsyncIterator[Any]:
        chunk = mocker.MagicMock()
        chunk.type = "response.output_text.done"
        chunk.text = (
            "Based on the documentation, OpenShift is a Kubernetes distribution."
        )
        yield chunk

        # Emit response.completed so referenced_documents propagate to end event
        completed_chunk = mocker.MagicMock()
        completed_chunk.type = "response.completed"
        mock_final = mocker.MagicMock(spec=OpenAIResponseObject)
        mock_final.id = "response-inline-stream"
        mock_final.error = None
        mock_usage = mocker.MagicMock()
        mock_usage.input_tokens = 50
        mock_usage.output_tokens = 20
        mock_final.usage = mock_usage
        mock_final.output = []
        completed_chunk.response = mock_final
        yield completed_chunk

    async def _responses_create(**kwargs: Any) -> Any:
        if kwargs.get("stream", True):
            return _mock_stream()
        mock_resp = mocker.MagicMock()
        mock_resp.output = [mocker.MagicMock(content="topic summary")]
        return mock_resp

    mock_client.responses.create = mocker.AsyncMock(side_effect=_responses_create)

    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="mock_streaming_byok_client")
def mock_streaming_byok_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock Llama Stack client with BYOK inline RAG configured for streaming.

    Configures vector_io.query to return BYOK RAG chunks and sets
    vector_stores.list to empty (no tool-based vector stores).
    """
    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    # BYOK vector_io returns results
    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    # No tool-based vector stores
    mock_vector_stores_response = mocker.MagicMock()
    mock_vector_stores_response.data = []
    mock_client.vector_stores.list.return_value = mock_vector_stores_response

    mock_holder_class.return_value.get_client.return_value = mock_client
    yield mock_client


@pytest.fixture(name="mock_streaming_byok_tool_client")
def mock_streaming_byok_tool_client_fixture(  # pylint: disable=too-many-statements
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock Llama Stack client with BYOK tool RAG (file_search) for streaming.

    Configures vector_stores.list with a BYOK store and responses.create
    to stream file_search_call output items alongside the assistant message.
    """
    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    # vector_io returns empty (no inline RAG)
    mock_empty_vector_io = mocker.MagicMock()
    mock_empty_vector_io.chunks = []
    mock_empty_vector_io.scores = []
    mock_client.vector_io.query = mocker.AsyncMock(return_value=mock_empty_vector_io)

    # Tool-based vector stores available
    mock_vector_store = mocker.MagicMock()
    mock_vector_store.id = "vs-byok-knowledge"
    mock_list_result = mocker.MagicMock()
    mock_list_result.data = [mock_vector_store]
    mock_client.vector_stores.list.return_value = mock_list_result

    # Build a streaming response with file_search and completion events
    async def _mock_tool_stream() -> AsyncIterator[Any]:
        # file_search output item done
        item_done_chunk = mocker.MagicMock()
        item_done_chunk.type = "response.output_item.done"
        item_done_chunk.output_index = 0

        mock_item = mocker.MagicMock()
        mock_item.type = "file_search_call"
        mock_item.id = "call-fs-stream-1"
        mock_item.queries = ["What is OpenShift?"]
        mock_item.status = "completed"

        mock_result = mocker.MagicMock()
        mock_result.file_id = "doc-ocp-1"
        mock_result.filename = "openshift-docs.txt"
        mock_result.score = 0.92
        mock_result.text = "OpenShift is a Kubernetes distribution by Red Hat."
        mock_result.attributes = {
            "doc_url": "https://docs.redhat.com/ocp/overview",
        }
        mock_result.model_dump = mocker.Mock(
            return_value={
                "file_id": "doc-ocp-1",
                "filename": "openshift-docs.txt",
                "score": 0.92,
                "text": "OpenShift is a Kubernetes distribution.",
                "attributes": {"doc_url": "https://docs.redhat.com/ocp/overview"},
            }
        )
        mock_item.results = [mock_result]
        item_done_chunk.item = mock_item
        yield item_done_chunk

        # Text done
        text_done_chunk = mocker.MagicMock()
        text_done_chunk.type = "response.output_text.done"
        text_done_chunk.text = (
            "Based on the documentation, OpenShift is a Kubernetes distribution."
        )
        yield text_done_chunk

        # Response completed
        completed_chunk = mocker.MagicMock()
        completed_chunk.type = "response.completed"
        mock_final_response = mocker.MagicMock(spec=OpenAIResponseObject)
        mock_final_response.id = "response-tool-stream"
        mock_final_response.error = None

        mock_usage = mocker.MagicMock()
        mock_usage.input_tokens = 60
        mock_usage.output_tokens = 25
        mock_final_response.usage = mock_usage

        # file_search results in the final response output
        mock_fs_output = mocker.MagicMock()
        mock_fs_output.type = "file_search_call"
        mock_fs_output.id = "call-fs-stream-1"
        mock_fs_output.results = [mock_result]
        mock_final_response.output = [mock_fs_output]

        completed_chunk.response = mock_final_response
        yield completed_chunk

    async def _responses_create(**kwargs: Any) -> Any:
        if kwargs.get("stream", True):
            return _mock_tool_stream()
        mock_resp = mocker.MagicMock()
        mock_resp.output = [mocker.MagicMock(content="topic summary")]
        return mock_resp

    mock_client.responses.create = mocker.AsyncMock(side_effect=_responses_create)

    mock_holder_class.return_value.get_client.return_value = mock_client
    yield mock_client


@pytest.fixture(name="byok_config")
def byok_config_fixture(test_config: AppConfig, mocker: MockerFixture) -> AppConfig:
    """Load test config and patch BYOK RAG configuration for inline RAG."""
    byok_entry = mocker.MagicMock()
    byok_entry.rag_id = "test-knowledge"
    byok_entry.vector_db_id = "vs-byok-knowledge"
    byok_entry.score_multiplier = 1.0
    byok_entry.model_dump.return_value = {
        "rag_id": "test-knowledge",
        "rag_type": "inline::faiss",
        "embedding_model": "sentence-transformers/all-mpnet-base-v2",
        "embedding_dimension": 768,
        "vector_db_id": "vs-byok-knowledge",
        "db_path": "/tmp/test-db",
        "score_multiplier": 1.0,
    }

    test_config.configuration.byok_rag = [byok_entry]
    test_config.configuration.rag.inline = ["test-knowledge"]

    return test_config


@pytest.fixture(name="byok_tool_config")
def byok_tool_config_fixture(
    test_config: AppConfig, mocker: MockerFixture
) -> AppConfig:
    """Load test config with BYOK RAG configured for tool-based (file_search) usage."""
    byok_entry = mocker.MagicMock()
    byok_entry.rag_id = "test-knowledge"
    byok_entry.vector_db_id = "vs-byok-knowledge"
    byok_entry.score_multiplier = 1.0
    byok_entry.model_dump.return_value = {
        "rag_id": "test-knowledge",
        "rag_type": "inline::faiss",
        "embedding_model": "sentence-transformers/all-mpnet-base-v2",
        "embedding_dimension": 768,
        "vector_db_id": "vs-byok-knowledge",
        "db_path": "/tmp/test-db",
        "score_multiplier": 1.0,
    }

    test_config.configuration.byok_rag = [byok_entry]
    test_config.configuration.rag.inline = []
    test_config.configuration.rag.tool = ["test-knowledge"]

    return test_config


# ==============================================================================
# Inline BYOK RAG Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_inline_rag_injects_context(
    byok_config: AppConfig,
    mock_streaming_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline BYOK RAG context is injected into streaming query input.

    Verifies:
    - RAG context from vector_io.query is injected into responses.create input
    - Input contains formatted file_search results
    """
    _ = byok_config

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Verify RAG context was injected into responses.create input
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_streaming_byok_client.responses.create.call_args_list[0]
    call_kwargs = create_call.kwargs
    input_text = call_kwargs["input"]
    assert "file_search found" in input_text
    assert "OpenShift is a Kubernetes distribution" in input_text


@pytest.mark.asyncio
async def test_streaming_query_byok_inline_rag_with_request_vector_store_ids(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that per-request vector_store_ids override config for streaming query.

    Config has rag.inline = ["source-a"] (resolves to vs-source-a).
    Request passes vector_store_ids = ["vs-source-b"].
    Only vs-source-b should be queried, proving the override works.
    (passing vector_store_ids overrides config)

    Verifies:
    - vector_io.query is called with the request-specified store, not config
    - The config-based store is NOT queried
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    # Override: request specifies vs-source-b, not the config's vs-source-a
    query_request = QueryRequest(
        query="What is OpenShift?",
        vector_store_ids=["vs-source-b"],
    )

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Verify only vs-source-b was queried (not the config's vs-source-a)
    assert mock_client.vector_io.query.call_count == 1
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-b"


@pytest.mark.asyncio
async def test_streaming_query_byok_request_vector_store_ids_filters_configured_stores(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that request vector_store_ids selects a subset of stores configured in rag.inline.

    Both source-a and source-b are registered in byok_rag and listed in rag.inline.
    The request passes vector_store_ids = ["vs-source-a"] to select only one.

    Verifies:
    - vector_io.query is called exactly once (for vs-source-a only)
    - vs-source-b is NOT queried despite being in rag.inline
    - Injected context contains only source-a content
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a", "source-b"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        vector_store_ids=["vs-source-a"],
    )

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Only vs-source-a should have been queried
    assert mock_client.vector_io.query.call_count == 1
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-a"

    # Verify source-a context was injected into the LLM input
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    assert "file_search found" in input_text


@pytest.mark.asyncio
async def test_streaming_query_byok_inline_rag_empty_vector_store_ids_no_context(
    byok_config: AppConfig,
    mock_streaming_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that passing an empty vector_store_ids list produces no inline context.

    Verifies:
    - vector_io.query is never called when vector_store_ids=[]
    - No RAG context is injected into the streaming input
    - Streaming response still succeeds
    """
    _ = byok_config

    query_request = QueryRequest(query="What is OpenShift?", vector_store_ids=[])

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)
    mock_streaming_byok_client.vector_io.query.assert_not_called()

    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_streaming_byok_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    assert "file_search found" not in input_text


@pytest.mark.asyncio
async def test_streaming_query_byok_inline_rag_error_handled_gracefully(
    byok_config: AppConfig,
    mock_streaming_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK RAG search failures are handled gracefully in streaming.

    Verifies:
    - When vector_io.query raises an exception, streaming query still succeeds
    - The error is silently handled (BYOK search errors are non-fatal)
    - No inline RAG context is injected into the prompt when search fails
    """
    _ = byok_config

    mock_streaming_byok_client.vector_io.query.side_effect = Exception(
        "Connection refused"
    )

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Streaming query should succeed despite BYOK RAG failure
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response, StreamingResponse)

    # No inline RAG context should be injected when the search fails.
    # "file_search found" is the header added by _format_rag_context when chunks are present.
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_streaming_byok_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    assert "file_search found" not in input_text


@pytest.mark.asyncio
async def test_streaming_query_byok_inline_rag_returns_referenced_documents(
    byok_config: AppConfig,
    mock_streaming_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline BYOK RAG emits referenced documents in the end event.

    Verifies:
    - Injected context references documents from BYOK RAG chunk metadata
    - The SSE end event includes referenced_documents with known URLs/titles
    """
    _ = byok_config
    _ = mock_streaming_byok_client

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Consume the stream and verify the end event carries referenced documents
    events = await _collect_sse_events(response)
    end_events = [e for e in events if e.get("event") == "end"]
    assert len(end_events) == 1

    ref_docs = end_events[0]["data"].get("referenced_documents", [])
    assert len(ref_docs) == 2, f"Expected 2 referenced docs, got {ref_docs}"

    doc_urls = [str(doc.get("doc_url", "")) for doc in ref_docs if doc.get("doc_url")]
    assert any(
        "docs.redhat.com/ocp/overview" in url for url in doc_urls
    ), f"Expected ocp/overview URL in {doc_urls}"
    assert any(
        "docs.redhat.com/k8s/pods" in url for url in doc_urls
    ), f"Expected k8s/pods URL in {doc_urls}"

    doc_titles = [doc.get("doc_title") for doc in ref_docs if doc.get("doc_title")]
    assert "OpenShift Overview" in doc_titles
    assert "Kubernetes Pods" in doc_titles


# ==============================================================================
# Tool-based BYOK RAG Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_tool_rag_emits_tool_call_events(
    byok_tool_config: AppConfig,
    mock_streaming_byok_tool_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK tool RAG emits tool call SSE events during streaming.

    Verifies:
    - Stream contains tool_call events from file_search_call output
    - Tool call event references file_search / knowledge_search
    """
    _ = byok_tool_config
    _ = mock_streaming_byok_tool_client

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    events = await _collect_sse_events(response)
    tool_call_events = [e for e in events if e.get("event") == "tool_call"]
    assert len(tool_call_events) > 0

    tool_names = [e["data"].get("name", "") for e in tool_call_events]
    assert any(
        "file_search" in name or "knowledge_search" in name for name in tool_names
    )


@pytest.mark.asyncio
async def test_streaming_query_byok_tool_rag_emits_referenced_documents(
    byok_tool_config: AppConfig,
    mock_streaming_byok_tool_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK tool RAG streaming emits referenced documents in end event.

    Verifies:
    - End event includes referenced_documents list
    - Documents include URLs from file_search results
    """
    _ = byok_tool_config
    _ = mock_streaming_byok_tool_client

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    events = await _collect_sse_events(response)
    end_events = [e for e in events if e.get("event") == "end"]
    assert len(end_events) == 1

    ref_docs = end_events[0]["data"].get("referenced_documents", [])
    assert isinstance(ref_docs, list)
    assert len(ref_docs) >= 1, "Expected at least one referenced document"

    # Verify known URL from the mock file_search result propagated
    doc_urls = [str(doc.get("doc_url", "")) for doc in ref_docs if doc.get("doc_url")]
    assert any(
        "docs.redhat.com/ocp/overview" in url for url in doc_urls
    ), f"Expected ocp/overview URL in {doc_urls}"


# ==============================================================================
# Combined Inline + Tool RAG Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_combined_inline_and_tool_rag(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline and tool-based BYOK RAG both work in streaming.

    Verifies:
    - Inline RAG context is injected into the input
    - Tool RAG file_search is passed as a tool
    - Streaming response succeeds
    """
    # Configure both inline and tool RAG
    byok_entry = mocker.MagicMock()
    byok_entry.rag_id = "test-knowledge"
    byok_entry.vector_db_id = "vs-byok-knowledge"
    byok_entry.score_multiplier = 1.0
    test_config.configuration.byok_rag = [byok_entry]
    test_config.configuration.rag.inline = ["test-knowledge"]
    test_config.configuration.rag.tool = ["test-knowledge"]

    # Mock Llama Stack client
    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    # Inline RAG returns chunks via vector_io
    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    # Tool RAG vector stores
    mock_vector_store = mocker.MagicMock()
    mock_vector_store.id = "vs-byok-knowledge"
    mock_list_result = mocker.MagicMock()
    mock_list_result.data = [mock_vector_store]
    mock_client.vector_stores.list.return_value = mock_list_result

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == status.HTTP_200_OK

    # Verify inline RAG context was injected
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    call_kwargs = create_call.kwargs
    input_text = call_kwargs["input"]
    assert "file_search found" in input_text

    # Verify tool RAG file_search was passed
    assert call_kwargs.get("tools") is not None
    assert any(tool.get("type") == "file_search" for tool in call_kwargs["tools"])


# ==============================================================================
# Inline RAG rag_id Resolution Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_only_configured_rag_id_is_queried(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that only the rag_id listed in rag.inline triggers retrieval in streaming.

    Two BYOK sources are registered (source-a and source-b) but only
    source-a is listed in rag.inline.  Only vs-source-a should be queried
    and only its content should appear in the injected context.

    Verifies:
    - vector_io.query is called exactly once (for the configured source)
    - The call targets the correct vector_db_id
    - vs-source-b is NOT queried
    - Injected context contains source-a content
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(query="What is OpenShift?")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    assert mock_client.vector_io.query.call_count == 1
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-a"

    queried_stores = [
        c.kwargs["vector_store_id"] for c in mock_client.vector_io.query.call_args_list
    ]
    assert "vs-source-b" not in queried_stores

    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    assert "file_search found" in input_text


# ==============================================================================
# Score Multiplier Priority Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_score_multiplier_shifts_priority(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that score_multiplier shifts chunk priority in streaming query.

    Doc A (source-a) has high base similarity (0.90) with multiplier 1.0.
    Doc B (source-b) has low base similarity (0.40) with multiplier 5.0.
    After weighting: Doc A = 0.90, Doc B = 2.00.
    The injected context should list Doc B content before Doc A.

    Verifies:
    - The higher-weighted chunk content appears first in the injected context
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 5.0

    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a", "source-b"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    resp_a = _make_vector_io_response(
        mocker,
        [
            ("Doc A high similarity", "doc-a", 0.90),
        ],
    )
    resp_b = _make_vector_io_response(
        mocker,
        [
            ("Doc B low similarity boosted", "doc-b", 0.40),
        ],
    )

    async def _side_effect(**kwargs: Any) -> Any:
        if kwargs["vector_store_id"] == "vs-source-a":
            return resp_a
        return resp_b

    mock_client.vector_io.query = mocker.AsyncMock(side_effect=_side_effect)

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(query="test query")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Verify Doc B (weighted 2.0) appears before Doc A (weighted 0.9) in context
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    pos_b = input_text.find("Doc B low similarity boosted")
    pos_a = input_text.find("Doc A high similarity")
    assert pos_b != -1 and pos_a != -1
    assert pos_b < pos_a


# ==============================================================================
# BYOK_RAG_MAX_CHUNKS Capping Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_streaming_query_byok_max_chunks_caps_context(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK_RAG_MAX_CHUNKS caps chunks in streaming query context.

    A source returns more chunks than BYOK_RAG_MAX_CHUNKS.  The injected
    context should contain at most BYOK_RAG_MAX_CHUNKS chunk entries.

    Verifies:
    - Context chunk count does not exceed BYOK_RAG_MAX_CHUNKS
    - Only the highest-scored chunks appear in the context
    """
    entry = mocker.MagicMock()
    entry.rag_id = "big-source"
    entry.vector_db_id = "vs-big-source"
    entry.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["big-source"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    # Generate more chunks than BYOK_RAG_MAX_CHUNKS
    num_chunks = constants.BYOK_RAG_MAX_CHUNKS + 5
    chunks_data = [
        (f"Chunk content {i}", f"chunk-{i}", round(0.50 + i * 0.03, 2))
        for i in range(num_chunks)
    ]
    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_vector_io_response(mocker, chunks_data)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(query="test query")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # Verify the context header reports the capped count
    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    expected_header = f"file_search found {constants.BYOK_RAG_MAX_CHUNKS} chunks:"
    assert expected_header in input_text

    # The lowest-scoring chunk should NOT be in the context
    assert "Chunk content 0" not in input_text
    # The highest-scoring chunk should be in the context
    assert f"Chunk content {num_chunks - 1}" in input_text


@pytest.mark.asyncio
async def test_streaming_query_byok_max_chunks_caps_across_multiple_sources(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK_RAG_MAX_CHUNKS caps chunks across multiple sources in streaming.

    Two sources each return several chunks.  The combined context should
    not exceed BYOK_RAG_MAX_CHUNKS and should contain the globally
    highest-scored chunks regardless of source.

    Verifies:
    - Total chunks across sources are capped at BYOK_RAG_MAX_CHUNKS
    - Only the highest-scored chunks appear in the context
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a", "source-b"]

    mock_holder_class = mocker.patch(
        "app.endpoints.streaming_query.AsyncLlamaStackClientHolder"
    )
    mock_client = _build_base_streaming_mock_client(mocker)

    # Overlapping score bands so top-k must pick from both sources
    n = constants.BYOK_RAG_MAX_CHUNKS
    resp_a = _make_vector_io_response(
        mocker,
        [
            (f"Source A chunk {i}", f"a-chunk-{i}", round(0.70 + i * 0.05, 2))
            for i in range(n)
        ],
    )
    resp_b = _make_vector_io_response(
        mocker,
        [
            (f"Source B chunk {i}", f"b-chunk-{i}", round(0.72 + i * 0.05, 2))
            for i in range(n)
        ],
    )

    async def _side_effect(**kwargs: Any) -> Any:
        if kwargs["vector_store_id"] == "vs-source-a":
            return resp_a
        return resp_b

    mock_client.vector_io.query = mocker.AsyncMock(side_effect=_side_effect)

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(query="test query")

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert isinstance(response, StreamingResponse)

    # responses.create is the mock for the OpenAI-compatible LLM API call.
    # .kwargs holds its keyword arguments, e.g. "input" is the full prompt text sent to the model.
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs["input"]
    expected_header = f"file_search found {constants.BYOK_RAG_MAX_CHUNKS} chunks:"
    assert expected_header in input_text

    # Both sources must appear in the context (overlapping scores guarantee this)
    assert "Source A chunk" in input_text
    assert "Source B chunk" in input_text

    # Lowest-scoring chunks from each source must be dropped
    assert "Source A chunk 0" not in input_text
    assert "Source B chunk 0" not in input_text
