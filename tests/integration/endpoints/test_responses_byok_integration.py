"""Integration tests for the /responses endpoint BYOK RAG functionality."""

from typing import Any

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

import constants
from app.endpoints.responses import responses_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import ResponsesRequest
from models.api.responses.successful import ResponsesResponse
from models.common.responses.contexts import ResponsesContext
from tests.integration.endpoints.test_query_byok_integration import (
    _build_base_mock_client,
    _make_byok_vector_io_response,
    _make_vector_io_response,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_AUTH: AuthTuple = (
    "00000000-0000-0000-0000-000",
    "lightspeed-user",
    True,
    "",
)

_RESPONSE_DUMP: dict[str, Any] = {
    "id": "resp-1",
    "object": "response",
    "created_at": 1700000000,
    "status": "completed",
    "model": "test-provider/test-model",
    "output": [
        {
            "type": "message",
            "id": "msg-1",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "OpenShift is a Kubernetes distribution.",
                    "annotations": [],
                }
            ],
        }
    ],
    "usage": {
        "input_tokens": 50,
        "output_tokens": 20,
        "total_tokens": 70,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_responses_mock_client(mocker: MockerFixture) -> Any:
    """Build a mock client suitable for the /responses endpoint."""
    mock_client = _build_base_mock_client(mocker)
    mock_client.responses.create.return_value.model_dump.return_value = (
        _RESPONSE_DUMP.copy()
    )
    return mock_client


def _patch_all_client_holders(mocker: MockerFixture, mock_client: Any) -> None:
    """Patch AsyncLlamaStackClientHolder in all modules used by the responses endpoint."""
    for module in (
        "app.endpoints.responses",
        "utils.endpoints",
    ):
        holder = mocker.patch(f"{module}.AsyncLlamaStackClientHolder")
        holder.return_value.get_client.return_value = mock_client

    original_cls = ResponsesContext

    def _skip_validation(**kwargs: Any) -> ResponsesContext:
        return original_cls.model_construct(**kwargs)

    mocker.patch(
        "app.endpoints.responses.ResponsesContext", side_effect=_skip_validation
    )


# ==============================================================================
# Inline BYOK RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_byok_inline_rag_injects_context(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that inline BYOK RAG fetches chunks and injects context into the input.

    Verifies:
    - vector_io.query is called for BYOK inline RAG
    - RAG context is injected into the responses.create input
    - Response is a valid ResponsesResponse
    """
    entry = mocker.MagicMock()
    entry.rag_id = "test-knowledge"
    entry.vector_db_id = "vs-byok-knowledge"
    entry.score_multiplier = 1.0
    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["test-knowledge"]

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    responses_request = ResponsesRequest(input="What is OpenShift?", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    # Verify vector_io.query was called for inline RAG
    mock_client.vector_io.query.assert_called()
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["query"] == "What is OpenShift?"

    # Verify RAG context was injected into responses.create input
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    assert "file_search found" in input_text
    assert "OpenShift is a Kubernetes distribution" in input_text


@pytest.mark.asyncio
async def test_responses_byok_inline_rag_error_is_handled_gracefully(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that BYOK RAG search failures are handled gracefully.

    Verifies:
    - When vector_io.query raises an exception, the endpoint still succeeds
    - The error is silently handled (BYOK search errors are non-fatal)
    """
    entry = mocker.MagicMock()
    entry.rag_id = "test-knowledge"
    entry.vector_db_id = "vs-byok-knowledge"
    entry.score_multiplier = 1.0
    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["test-knowledge"]

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    mock_client.vector_io.query = mocker.AsyncMock(
        side_effect=Exception("Connection refused")
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    responses_request = ResponsesRequest(input="What is OpenShift?", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    # Endpoint should succeed despite BYOK RAG failure
    assert isinstance(response, ResponsesResponse)


# ==============================================================================
# Tool-based BYOK RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_byok_tool_rag_returns_tool_calls(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that BYOK tool RAG configures file_search tool in responses.create call.

    Verifies:
    - file_search tool is present in the tools passed to responses.create
    - The tool includes the configured vector store ID
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

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    mock_vector_store = mocker.MagicMock()
    mock_vector_store.id = "vs-byok-knowledge"
    mock_list_result = mocker.MagicMock()
    mock_list_result.data = [mock_vector_store]
    mock_client.vector_stores.list.return_value = mock_list_result

    responses_request = ResponsesRequest(input="What is OpenShift?", stream=False)

    await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert mock_client.responses.create.called
    call_kwargs = mock_client.responses.create.call_args_list[0]

    tools = call_kwargs.kwargs.get("tools", [])
    file_search_tools = [
        t
        for t in tools
        if (t.get("type") if isinstance(t, dict) else getattr(t, "type", None))
        == "file_search"
    ]
    assert len(file_search_tools) == 1
    vs_ids = (
        file_search_tools[0].get("vector_store_ids")
        if isinstance(file_search_tools[0], dict)
        else file_search_tools[0].vector_store_ids
    )
    assert vs_ids == ["vs-byok-knowledge"]


# ==============================================================================
# Combined Inline + Tool RAG Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_byok_combined_inline_and_tool_rag(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that inline and tool-based BYOK RAG are both active when configured.

    Verifies:
    - Inline RAG context is injected into the input
    - file_search tool is present in the tools passed to responses.create
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
    test_config.configuration.rag.inline = ["test-knowledge"]
    test_config.configuration.rag.tool = ["test-knowledge"]

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

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

    responses_request = ResponsesRequest(input="What is OpenShift?", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    # Verify inline RAG context was injected
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    assert "file_search found" in input_text

    # Verify tool RAG file_search tool is present
    tools = create_call.kwargs.get("tools", [])
    file_search_tools = [
        t
        for t in tools
        if (t.get("type") if isinstance(t, dict) else getattr(t, "type", None))
        == "file_search"
    ]
    assert len(file_search_tools) == 1
    vs_ids = (
        file_search_tools[0].get("vector_store_ids")
        if isinstance(file_search_tools[0], dict)
        else file_search_tools[0].vector_store_ids
    )
    assert vs_ids == ["vs-byok-knowledge"]


# ==============================================================================
# Inline RAG rag_id Resolution Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_byok_inline_rag_only_configured_rag_id_is_queried(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that only the rag_id listed in rag.inline triggers retrieval.

    Two BYOK sources are registered (source-a and source-b) but only
    source-a is listed in rag.inline. Only the vector_db_id for
    source-a should be queried.

    Verifies:
    - vector_io.query is called exactly once (for the configured source)
    - The call targets the correct vector_db_id
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

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    mock_client.vector_io.query = mocker.AsyncMock(
        return_value=_make_byok_vector_io_response(mocker)
    )

    mock_vs_resp = mocker.MagicMock()
    mock_vs_resp.data = []
    mock_client.vector_stores.list.return_value = mock_vs_resp

    responses_request = ResponsesRequest(input="What is OpenShift?", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    assert mock_client.vector_io.query.call_count == 1
    call_kwargs = mock_client.vector_io.query.call_args.kwargs
    assert call_kwargs["vector_store_id"] == "vs-source-a"


# ==============================================================================
# Score Multiplier Priority Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_byok_score_multiplier_shifts_chunk_priority(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that score_multiplier can shift chunk priority across sources.

    Doc A (source-a) has high base similarity (0.90) with multiplier 1.0.
    Doc B (source-b) has low base similarity (0.40) with multiplier 5.0.
    After weighting: Doc A = 0.90, Doc B = 2.00.
    Doc B should appear above Doc A in the final context.

    Verifies:
    - The chunk with the higher weighted score appears first in the context
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

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

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

    responses_request = ResponsesRequest(input="test query", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    # Doc B (weighted 2.0) should rank above Doc A (weighted 0.9) in the context
    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    assert "file_search found 2 chunks:" in input_text

    # Doc B (higher weighted score) should appear before Doc A in the context
    pos_b = input_text.find("Doc B content - low similarity")
    pos_a = input_text.find("Doc A content - high similarity")
    assert pos_b != -1 and pos_a != -1
    assert (
        pos_b < pos_a
    ), "Doc B should appear before Doc A due to higher weighted score"


# ==============================================================================
# INLINE_RAG_MAX_CHUNKS Capping Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_responses_rag_content_limit_caps_retrieved_results(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that INLINE_RAG_MAX_CHUNKS caps the number of returned chunks.

    A single source returns more chunks than INLINE_RAG_MAX_CHUNKS allows.
    The context sent to the LLM should contain at most INLINE_RAG_MAX_CHUNKS chunks.

    Verifies:
    - Context chunk count does not exceed INLINE_RAG_MAX_CHUNKS
    - Returned chunks are the top-scoring ones
    """
    entry = mocker.MagicMock()
    entry.rag_id = "big-source"
    entry.vector_db_id = "vs-big-source"
    entry.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["big-source"]
    test_config.configuration.reranker.enabled = False

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    # Generate more chunks than INLINE_RAG_MAX_CHUNKS
    num_chunks = constants.INLINE_RAG_MAX_CHUNKS + 1
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

    responses_request = ResponsesRequest(input="test query", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    expected_header = f"file_search found {constants.INLINE_RAG_MAX_CHUNKS} chunks:"
    assert expected_header in input_text

    # The highest-scored chunk should be present
    assert f"Chunk content {num_chunks - 1}" in input_text
    # The lowest-scored chunk should be excluded
    assert "Chunk content 0" not in input_text


@pytest.mark.asyncio
async def test_responses_rag_content_limit_caps_across_multiple_sources(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that INLINE_RAG_MAX_CHUNKS caps chunks across multiple sources.

    Two sources each return several chunks. The combined result should not
    exceed INLINE_RAG_MAX_CHUNKS and should contain the globally highest-scored
    chunks regardless of source.

    Verifies:
    - Total chunks across sources are capped at INLINE_RAG_MAX_CHUNKS
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

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    # Overlapping score bands so top-k must pick from both sources
    n = constants.INLINE_RAG_MAX_CHUNKS
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

    responses_request = ResponsesRequest(input="test query", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    expected_header = f"file_search found {constants.INLINE_RAG_MAX_CHUNKS} chunks:"
    assert expected_header in input_text

    # Both sources should survive the cap (high-scoring chunks from each)
    assert "Source A chunk" in input_text
    assert "Source B chunk" in input_text

    # Lowest-scoring chunks from each source should be dropped
    assert "Source A chunk 0" not in input_text
    assert "Source B chunk 0" not in input_text


@pytest.mark.asyncio
async def test_responses_rag_content_limit_caps_inline_rag(  # pylint: disable=too-many-locals
    test_config: AppConfig,
    mocker: MockerFixture,
    test_request: Request,
) -> None:
    """Test that INLINE_RAG_MAX_CHUNKS caps inline RAG below BYOK_RAG_MAX_CHUNKS.

    Sets INLINE_RAG_MAX_CHUNKS to 3 (below BYOK_RAG_MAX_CHUNKS=10) and feeds
    10 chunks. The context sent to the LLM should contain at most 3 chunks.

    Verifies:
    - Context chunk count equals the lowered INLINE_RAG_MAX_CHUNKS
    - Only the highest-scored chunks appear in the context
    """
    mocker.patch("utils.vector_search.constants.INLINE_RAG_MAX_CHUNKS", 3)

    entry = mocker.MagicMock()
    entry.rag_id = "big-source"
    entry.vector_db_id = "vs-big-source"
    entry.score_multiplier = 1.0

    test_config.configuration.byok_rag = [entry]
    test_config.configuration.rag.inline = ["big-source"]
    test_config.configuration.reranker.enabled = False

    mock_client = _build_responses_mock_client(mocker)
    _patch_all_client_holders(mocker, mock_client)

    num_chunks = constants.BYOK_RAG_MAX_CHUNKS
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

    responses_request = ResponsesRequest(input="test query", stream=False)

    response = await responses_endpoint_handler(
        request=test_request,
        responses_request=responses_request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ResponsesResponse)

    create_call = mock_client.responses.create.call_args_list[0]
    input_text = create_call.kwargs.get("input", "")
    expected_header = "file_search found 3 chunks:"
    assert expected_header in input_text

    assert f"Chunk content {num_chunks - 1}" in input_text
    assert "Chunk content 0" not in input_text
