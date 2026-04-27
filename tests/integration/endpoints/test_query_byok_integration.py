"""Integration tests for the /query endpoint BYOK inline and tool RAG functionality."""

# pylint: disable=too-many-lines

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client.types import VersionInfo
from pytest_mock import AsyncMockType, MockerFixture

import constants
from app.endpoints.query import query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.successful import QueryResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_byok_vector_io_response(mocker: MockerFixture) -> Any:
    """Build a mock vector_io.query response with BYOK RAG chunks.

    Returns a mock with .chunks and .scores attributes simulating a
    vector store search result with two chunks.
    """
    chunk_1 = mocker.MagicMock()
    chunk_1.content = "OpenShift is a Kubernetes distribution by Red Hat."
    chunk_1.chunk_id = "chunk-1"
    chunk_1.metadata = {
        "document_id": "doc-ocp-overview",
        "title": "OpenShift Overview",
        "reference_url": "https://docs.redhat.com/ocp/overview",
    }

    chunk_2 = mocker.MagicMock()
    chunk_2.content = "Pods are the smallest deployable units in Kubernetes."
    chunk_2.chunk_id = "chunk-2"
    chunk_2.metadata = {
        "document_id": "doc-k8s-pods",
        "title": "Kubernetes Pods",
        "reference_url": "https://docs.redhat.com/k8s/pods",
    }

    response = mocker.MagicMock()
    response.chunks = [chunk_1, chunk_2]
    response.scores = [0.95, 0.88]
    return response


def _make_vector_io_response(
    mocker: MockerFixture,
    chunks_data: list[tuple[str, str, float]],
) -> Any:
    """Build a mock vector_io.query response with arbitrary chunks.

    Parameters:
    ----------
        mocker: pytest-mock fixture.
        chunks_data: List of (content, chunk_id, score) tuples.

    Returns:
    -------
        Mock with .chunks and .scores attributes.
    """
    chunks = []
    scores = []
    for content, chunk_id, score in chunks_data:
        chunk = mocker.MagicMock()
        chunk.content = content
        chunk.chunk_id = chunk_id
        chunk.metadata = {"document_id": chunk_id}
        chunks.append(chunk)
        scores.append(score)

    response = mocker.MagicMock()
    response.chunks = chunks
    response.scores = scores
    return response


def _build_base_mock_client(mocker: MockerFixture) -> Any:
    """Build a base mock Llama Stack client with common stubs.

    Configures models, shields, conversations, version, and a default
    responses.create return value.
    """
    mock_client = mocker.AsyncMock()

    # Model list
    mock_model = mocker.MagicMock()
    mock_model.id = "test-provider/test-model"
    mock_model.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "llm",
    }
    mock_client.models.list.return_value = [mock_model]

    # Shields (empty)
    mock_client.shields.list.return_value = []

    # Conversations
    mock_conversation = mocker.MagicMock()
    mock_conversation.id = "conv_" + "a" * 48
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conversation)

    # Version
    mock_client.inspect.version.return_value = VersionInfo(version="0.4.3")

    # Default response
    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-byok"
    mock_output_item = mocker.MagicMock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = (
        "Based on the documentation, OpenShift is a Kubernetes distribution."
    )
    mock_output_item.refusal = None
    mock_response.output = [mock_output_item]
    mock_response.stop_reason = "end_turn"
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 20
    mock_response.usage = mock_usage
    mock_client.responses.create.return_value = mock_response

    return mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="mock_byok_client")
def mock_byok_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock Llama Stack client with BYOK inline RAG configured.

    Configures vector_io.query to return BYOK RAG chunks and sets
    vector_stores.list to empty (no tool-based vector stores).
    """
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

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


@pytest.fixture(name="mock_byok_tool_rag_client")
def mock_byok_tool_rag_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock Llama Stack client with BYOK tool RAG (file_search) configured.

    Configures vector_stores.list with a BYOK store and responses.create
    to return a file_search_call output item alongside the assistant message.
    """
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

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

    # Response with file_search tool call
    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-tool-rag"

    mock_tool_output = mocker.MagicMock()
    mock_tool_output.type = "file_search_call"
    mock_tool_output.id = "call-fs-1"
    mock_tool_output.queries = ["What is OpenShift?"]
    mock_tool_output.status = "completed"

    mock_result = mocker.MagicMock()
    mock_result.file_id = "doc-ocp-1"
    mock_result.filename = "openshift-docs.txt"
    mock_result.score = 0.92
    mock_result.text = "OpenShift is a Kubernetes distribution by Red Hat."
    mock_result.attributes = {
        "doc_url": "https://docs.redhat.com/ocp/overview",
        "link": "https://docs.redhat.com/ocp/overview",
    }
    mock_result.model_dump = mocker.Mock(
        return_value={
            "file_id": "doc-ocp-1",
            "filename": "openshift-docs.txt",
            "score": 0.92,
            "text": "OpenShift is a Kubernetes distribution by Red Hat.",
            "attributes": {
                "doc_url": "https://docs.redhat.com/ocp/overview",
            },
        }
    )
    mock_tool_output.results = [mock_result]

    mock_message = mocker.MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = (
        "Based on the documentation, OpenShift is a Kubernetes distribution."
    )
    mock_message.refusal = None

    mock_response.output = [mock_tool_output, mock_message]
    mock_response.stop_reason = "end_turn"
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 60
    mock_usage.output_tokens = 25
    mock_response.usage = mock_usage
    mock_client.responses.create.return_value = mock_response

    mock_holder_class.return_value.get_client.return_value = mock_client
    yield mock_client


@pytest.fixture(name="byok_config")
def byok_config_fixture(test_config: AppConfig, mocker: MockerFixture) -> AppConfig:
    """Load test config and patch BYOK RAG configuration.

    Adds a BYOK RAG entry and inline RAG strategy so that inline RAG
    code paths are exercised with real configuration logic.
    """
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

    # Patch the loaded configuration's byok_rag and rag.inline
    test_config.configuration.byok_rag = [byok_entry]
    test_config.configuration.rag.inline = ["test-knowledge"]

    return test_config


@pytest.fixture(name="byok_tool_config")
def byok_tool_config_fixture(
    test_config: AppConfig, mocker: MockerFixture
) -> AppConfig:
    """Load test config with BYOK RAG configured for tool-based (file_search) usage.

    Sets rag.inline to empty and rag.tool to include the BYOK store,
    so only tool-based RAG is active.
    """
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
# Inline BYOK RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_inline_rag_injects_context(
    byok_config: AppConfig,
    mock_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline BYOK RAG fetches chunks and injects context into the query.

    Verifies:
    - vector_io.query is called for BYOK inline RAG
    - RAG context is injected into the responses.create input
    - Response includes RAG chunks from inline sources
    """
    _ = byok_config

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.response is not None

    # Verify vector_io.query was called for inline RAG
    mock_byok_client.vector_io.query.assert_called()
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_byok_client.vector_io.query.call_args.kwargs
    assert call_kwargs["query"] == "What is OpenShift?"

    # Verify RAG context was injected into responses.create input
    # Use call_args_list[0] — the first call is the main query;
    # a second call may follow for topic summary generation.
    create_kwargs = mock_byok_client.responses.create.call_args_list[0].kwargs
    input_text = create_kwargs["input"]
    assert "file_search found" in input_text
    assert "OpenShift is a Kubernetes distribution" in input_text

    # Verify RAG chunks are included in the response
    assert response.rag_chunks is not None
    assert len(response.rag_chunks) > 0


@pytest.mark.asyncio
async def test_query_byok_inline_rag_returns_referenced_documents(
    byok_config: AppConfig,
    mock_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline BYOK RAG extracts referenced documents from chunks.

    Verifies:
    - Referenced documents are extracted from BYOK RAG chunk metadata
    - Documents include URLs from chunk metadata
    """
    _ = byok_config
    _ = mock_byok_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.referenced_documents is not None
    assert len(response.referenced_documents) == 2

    # Verify known document metadata propagated from mock chunks
    doc_urls = [
        str(doc.doc_url) for doc in response.referenced_documents if doc.doc_url
    ]
    assert any(
        "docs.redhat.com/ocp/overview" in url for url in doc_urls
    ), f"Expected ocp/overview URL in {doc_urls}"
    assert any(
        "docs.redhat.com/k8s/pods" in url for url in doc_urls
    ), f"Expected k8s/pods URL in {doc_urls}"

    doc_titles = [
        doc.doc_title for doc in response.referenced_documents if doc.doc_title
    ]
    assert "OpenShift Overview" in doc_titles
    assert "Kubernetes Pods" in doc_titles


@pytest.mark.asyncio
async def test_query_byok_inline_rag_with_request_vector_store_ids(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that per-request vector_store_ids not in rag.inline are filtered out.

    Config has rag.inline = ["source-a"] (resolves to vs-source-a).
    Request passes vector_store_ids = ["source-b"] which is NOT in rag.inline.
    No inline RAG should be triggered because config is the source of truth.

    Verifies:
    - vector_io.query is NOT called (source-b is not in rag.inline)
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

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    # Request specifies source-b which is NOT in rag.inline config
    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=["source-b"],
        shield_ids=None,
        solr=None,
    )

    await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # source-b is not in rag.inline, so no inline RAG should be triggered
    assert mock_client.vector_io.query.call_count == 0


@pytest.mark.asyncio
async def test_query_byok_request_vector_store_ids_filters_configured_stores(
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
    - Returned chunks only reference source-a
    """
    entry_a = mocker.MagicMock()
    entry_a.rag_id = "source-a"
    entry_a.vector_db_id = "vs-source-a"
    entry_a.score_multiplier = 1.0

    entry_b = mocker.MagicMock()
    entry_b.rag_id = "source-b"
    entry_b.vector_db_id = "vs-source-b"
    entry_b.score_multiplier = 1.0

    # Both sources are in config
    test_config.configuration.byok_rag = [entry_a, entry_b]
    test_config.configuration.rag.inline = ["source-a", "source-b"]

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    # Request narrows down to only source-a (using rag_id, not vector_db_id)
    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=["source-a"],
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Only vs-source-a should have been queried
    assert mock_client.vector_io.query.call_count == 1
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-a"

    # Chunks should only come from source-a
    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == 2
    assert all(chunk.source == "source-a" for chunk in response.rag_chunks)


@pytest.mark.asyncio
async def test_query_byok_inline_rag_empty_vector_store_ids_returns_no_chunks(
    byok_config: AppConfig,
    mock_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that passing an empty vector_store_ids list produces no RAG chunks.

    Verifies:
    - vector_io.query is never called when vector_store_ids=[]
    - Response contains no RAG chunks
    - Response still succeeds
    """
    _ = byok_config

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=[],
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.response is not None
    mock_byok_client.vector_io.query.assert_not_called()
    assert not response.rag_chunks


@pytest.mark.asyncio
async def test_query_byok_inline_rag_error_is_handled_gracefully(
    byok_config: AppConfig,
    mock_byok_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK RAG search failures are handled gracefully.

    Verifies:
    - When vector_io.query raises an exception, the query still succeeds
    - The error is silently handled (BYOK search errors are non-fatal)
    """
    _ = byok_config

    mock_byok_client.vector_io.query.side_effect = Exception("Connection refused")

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Query should succeed despite BYOK RAG failure, but with no chunks
    assert isinstance(response, QueryResponse)
    assert not response.rag_chunks


# ==============================================================================
# Tool-based BYOK RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_tool_rag_returns_tool_calls(
    byok_tool_config: AppConfig,
    mock_byok_tool_rag_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK tool RAG results include file_search tool calls.

    Verifies:
    - Response includes tool_calls from file_search_call output
    - Tool call name is file_search
    """
    _ = byok_tool_config
    _ = mock_byok_tool_rag_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.tool_calls is not None
    assert len(response.tool_calls) > 0
    assert response.tool_calls[0].name == "file_search"


@pytest.mark.asyncio
async def test_query_byok_tool_rag_referenced_documents(
    byok_tool_config: AppConfig,
    mock_byok_tool_rag_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK tool RAG extracts referenced documents from file_search results.

    Verifies:
    - Referenced documents are extracted from file_search_call results
    - Documents include proper metadata
    """
    _ = byok_tool_config
    _ = mock_byok_tool_rag_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.referenced_documents is not None
    assert len(response.referenced_documents) >= 1

    # Verify known values from the mock file_search result propagated
    doc_urls = [
        str(doc.doc_url) for doc in response.referenced_documents if doc.doc_url
    ]
    assert any(
        "docs.redhat.com/ocp/overview" in url for url in doc_urls
    ), f"Expected ocp/overview URL in {doc_urls}"


# ==============================================================================
# Combined Inline + Tool RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_combined_inline_and_tool_rag(  # pylint: disable=too-many-locals,too-many-statements
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that inline and tool-based BYOK RAG results are combined.

    Verifies:
    - Both inline RAG chunks and tool RAG chunks appear in response
    - RAG chunks from both sources are merged
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
    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

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

    # Response includes file_search_call (tool RAG result)
    mock_response = mocker.MagicMock(spec=OpenAIResponseObject)
    mock_response.id = "response-combined"

    mock_tool_output = mocker.MagicMock()
    mock_tool_output.type = "file_search_call"
    mock_tool_output.id = "call-fs-combined"
    mock_tool_output.queries = ["What is OpenShift?"]
    mock_tool_output.status = "completed"

    mock_result = mocker.MagicMock()
    mock_result.file_id = "doc-tool-1"
    mock_result.filename = "tool-doc.txt"
    mock_result.score = 0.90
    mock_result.text = "Tool-based RAG result about OpenShift."
    mock_result.attributes = {"doc_url": "https://example.com/tool-doc"}
    mock_result.model_dump = mocker.Mock(
        return_value={
            "file_id": "doc-tool-1",
            "filename": "tool-doc.txt",
            "score": 0.90,
            "text": "Tool-based RAG result about OpenShift.",
            "attributes": {"doc_url": "https://example.com/tool-doc"},
        }
    )
    mock_tool_output.results = [mock_result]

    mock_message = mocker.MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = "Combined answer from inline and tool RAG."
    mock_message.refusal = None

    mock_response.output = [mock_tool_output, mock_message]
    mock_response.stop_reason = "end_turn"
    mock_response.tool_calls = []
    mock_usage = mocker.MagicMock()
    mock_usage.input_tokens = 80
    mock_usage.output_tokens = 30
    mock_response.usage = mock_usage
    mock_client.responses.create.return_value = mock_response

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    # Verify both inline and tool RAG chunks are present
    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == 3

    # Verify tool calls are present (from tool RAG)
    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1


# ==============================================================================
# Inline RAG rag_id Resolution Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_inline_rag_only_configured_rag_id_is_queried(
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that only the rag_id listed in rag.inline triggers retrieval.

    Two BYOK sources are registered (source-a and source-b) but only
    source-a is listed in rag.inline.  Only the vector_db_id for
    source-a should be queried and only its chunks should appear in the response.

    Verifies:
    - vector_io.query is called exactly once (for the configured source)
    - The call targets the correct vector_db_id
    - Returned chunks only reference source-a
    - source-b chunks are absent
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

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(
        query="What is OpenShift?",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert mock_client.vector_io.query.call_count == 1
    # call_args.kwargs holds the keyword arguments of the most recent call to vector_io.query.
    # e.g. "vector_store_id" is the store queried, "query" is the search text.
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-a"

    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == 2
    sources = {chunk.source for chunk in response.rag_chunks}
    assert "source-a" in sources
    assert "source-b" not in sources


# ==============================================================================
# Score Multiplier Priority Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_score_multiplier_shifts_chunk_priority(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that score_multiplier can shift chunk priority across sources.

    Doc A (source-a) has high base similarity (0.90) with multiplier 1.0.
    Doc B (source-b) has low base similarity (0.40) with multiplier 5.0.
    After weighting: Doc A = 0.90, Doc B = 2.00.
    Doc B should appear above Doc A in the final chunks.

    Verifies:
    - The chunk with the higher weighted score appears first
    - score_multiplier correctly influences ranking
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

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

    # Source A: high base similarity
    resp_a = _make_vector_io_response(
        mocker,
        [
            ("Doc A content - high similarity", "doc-a", 0.90),
        ],
    )
    # Source B: low base similarity
    resp_b = _make_vector_io_response(
        mocker,
        [
            ("Doc B content - low similarity", "doc-b", 0.40),
        ],
    )

    # Return different results per vector store
    async def _side_effect(**kwargs: Any) -> Any:
        if kwargs["vector_store_id"] == "vs-source-a":
            return resp_a
        return resp_b

    mock_client.vector_io.query = mocker.AsyncMock(side_effect=_side_effect)

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(
        query="test query",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == 2

    # Doc B (weighted 2.0) should rank above Doc A (weighted 0.9)
    first_chunk = response.rag_chunks[0]
    second_chunk = response.rag_chunks[1]
    assert first_chunk.source == "source-b"
    assert second_chunk.source == "source-a"
    assert first_chunk.score is not None
    assert second_chunk.score is not None
    assert first_chunk.score > second_chunk.score


# ==============================================================================
# BYOK_RAG_MAX_CHUNKS Capping Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_query_byok_max_chunks_caps_retrieved_results(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK_RAG_MAX_CHUNKS caps the number of returned chunks.

    A single source returns more chunks than BYOK_RAG_MAX_CHUNKS allows.
    The response should contain at most BYOK_RAG_MAX_CHUNKS chunks and
    they should be the highest-scored ones.

    Verifies:
    - Number of RAG chunks does not exceed BYOK_RAG_MAX_CHUNKS
    - Returned chunks are the top-scoring ones
    """
    entry = mocker.MagicMock()
    entry.rag_id = "big-source"
    entry.vector_db_id = "vs-big-source"
    entry.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["big-source"]

    # Disable reranker for this test since it's testing chunk capping, not reranking
    test_config.configuration.reranker.enabled = False

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

    # Generate more chunks than BYOK_RAG_MAX_CHUNKS
    num_chunks = constants.BYOK_RAG_MAX_CHUNKS + 1
    chunks_data = [
        (f"Chunk content {i}", f"chunk-{i}", round(0.50 + i * 0.03, 2))
        for i in range(num_chunks)
    ]
    # Scores increase with index: chunk-0 = 0.50, chunk-14 = 0.92 (for max=10)
    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_vector_io_response(mocker, chunks_data)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    mock_holder_class.return_value.get_client.return_value = mock_client

    query_request = QueryRequest(
        query="test query",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == constants.BYOK_RAG_MAX_CHUNKS

    # Check that the score is computed properly
    for chunk in response.rag_chunks:
        assert chunk.score is not None

    # Verify chunks are sorted by score descending (highest first)
    scores: list[float] = [
        chunk.score for chunk in response.rag_chunks if chunk.score is not None
    ]
    assert scores == sorted(scores, reverse=True)

    # The lowest-scored chunks from the original set should be excluded
    # The highest score in the original set is at the last index
    highest_original_score = chunks_data[-1][2]  # score of the last chunk
    # When reranker is disabled, BYOK boost is NOT applied, so we expect original score
    assert response.rag_chunks[0].score == highest_original_score


@pytest.mark.asyncio
async def test_query_byok_max_chunks_caps_across_multiple_sources(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that BYOK_RAG_MAX_CHUNKS caps chunks across multiple sources.

    Two sources each return several chunks.  The combined result should
    not exceed BYOK_RAG_MAX_CHUNKS and should contain the globally
    highest-scored chunks regardless of source.

    Verifies:
    - Total chunks across sources are capped at BYOK_RAG_MAX_CHUNKS
    - Top-scoring chunks from both sources are included
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

    mock_holder_class = mocker.patch("app.endpoints.query.AsyncLlamaStackClientHolder")
    mock_client = _build_base_mock_client(mocker)

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

    query_request = QueryRequest(
        query="test query",
        conversation_id=None,
        provider=None,
        model=None,
        system_prompt=None,
        attachments=None,
        no_tools=False,
        generate_topic_summary=None,
        media_type=None,
        vector_store_ids=None,
        shield_ids=None,
        solr=None,
    )

    response = await query_endpoint_handler(
        request=test_request,
        query_request=query_request,
        auth=test_auth,
        mcp_headers={},
    )

    assert response.rag_chunks is not None
    assert len(response.rag_chunks) == constants.BYOK_RAG_MAX_CHUNKS

    # Check that the score is computed properly
    for chunk in response.rag_chunks:
        assert chunk.score is not None

    scores: list[float] = [
        chunk.score for chunk in response.rag_chunks if chunk.score is not None
    ]
    assert scores == sorted(scores, reverse=True)

    # Both sources must survive the cap
    sources = {chunk.source for chunk in response.rag_chunks}
    assert "source-a" in sources
    assert "source-b" in sources

    # Lowest-scoring chunks from each source must be dropped
    chunk_contents = {chunk.content for chunk in response.rag_chunks}
    assert "Source A chunk 0" not in chunk_contents
    assert "Source B chunk 0" not in chunk_contents
