"""Unit tests for vector search utilities."""

import pytest

import constants
from configuration import AppConfig
from utils.types import RAGChunk
from utils.vector_search import (
    _build_document_url,
    _build_query_params,
    _convert_solr_chunks_to_rag_format,
    _extract_byok_rag_chunks,
    _extract_solr_document_metadata,
    _fetch_byok_rag,
    _fetch_solr_rag,
    _format_rag_context,
    _get_solr_vector_store_ids,
    _is_solr_enabled,
    build_rag_context,
)


class TestIsSolrEnabled:
    """Tests for _is_solr_enabled function."""

    def test_solr_enabled_true(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when Solr is enabled in configuration."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = True
        mocker.patch("utils.vector_search.configuration", config_mock)
        assert _is_solr_enabled() is True

    def test_solr_enabled_false(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when Solr is disabled in configuration."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = False
        mocker.patch("utils.vector_search.configuration", config_mock)
        assert _is_solr_enabled() is False


class TestGetSolrVectorStoreIds:  # pylint: disable=too-few-public-methods
    """Tests for _get_solr_vector_store_ids function."""

    def test_returns_default_vector_store_id(self) -> None:
        """Test that function returns the default Solr vector store ID."""
        result = _get_solr_vector_store_ids()
        assert result == [constants.SOLR_DEFAULT_VECTOR_STORE_ID]
        assert len(result) == 1


class TestBuildQueryParams:
    """Tests for _build_query_params function."""

    def test_default_params(self) -> None:
        """Test default parameters when no solr filters provided."""
        params = _build_query_params()

        assert params["k"] == constants.SOLR_VECTOR_SEARCH_DEFAULT_K
        assert (
            params["score_threshold"]
            == constants.SOLR_VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD
        )
        assert params["mode"] == constants.SOLR_VECTOR_SEARCH_DEFAULT_MODE
        assert "solr" not in params

    def test_with_solr_filters(self) -> None:
        """Test parameters when solr filters are provided."""
        solr_filters = {"filter": "value"}
        params = _build_query_params(solr=solr_filters)

        assert params["solr"] == solr_filters
        assert params["k"] == constants.SOLR_VECTOR_SEARCH_DEFAULT_K


class TestExtractByokRagChunks:
    """Tests for _extract_byok_rag_chunks function."""

    def test_extract_chunks_with_metadata(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test extraction of chunks with metadata."""
        # Create mock chunks
        chunk1 = mocker.Mock()
        chunk1.content = "Content 1"
        chunk1.chunk_id = "chunk_1"
        chunk1.metadata = {"document_id": "doc_1", "title": "Document 1"}

        chunk2 = mocker.Mock()
        chunk2.content = "Content 2"
        chunk2.chunk_id = "chunk_2"
        chunk2.metadata = {"document_id": "doc_2", "title": "Document 2"}

        # Create mock search response
        search_response = mocker.Mock()
        search_response.chunks = [chunk1, chunk2]
        search_response.scores = [0.9, 0.8]

        result = _extract_byok_rag_chunks(
            search_response, vector_store_id="test_store", weight=1.5
        )

        assert len(result) == 2
        assert result[0]["content"] == "Content 1"
        assert result[0]["score"] == 0.9
        assert result[0]["weighted_score"] == 0.9 * 1.5
        assert result[0]["source"] == "test_store"
        assert result[0]["doc_id"] == "doc_1"

    def test_extract_chunks_without_metadata(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test extraction of chunks without metadata."""
        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.chunk_id = "chunk_id"
        chunk.metadata = None

        search_response = mocker.Mock()
        search_response.chunks = [chunk]
        search_response.scores = [0.75]

        result = _extract_byok_rag_chunks(
            search_response, vector_store_id="test_store", weight=1.0
        )

        assert len(result) == 1
        assert result[0]["doc_id"] == "chunk_id"
        assert result[0]["metadata"] == {}


class TestFormatRagContext:
    """Tests for _format_rag_context function."""

    def test_empty_chunks(self) -> None:
        """Test formatting with empty chunks list."""
        result = _format_rag_context([], "test query")
        assert result == ""

    def test_format_single_chunk(self) -> None:
        """Test formatting with a single chunk."""
        chunks = [RAGChunk(content="Test content", source="test_source", score=0.95)]
        result = _format_rag_context(chunks, "test query")

        assert "file_search found 1 chunks:" in result
        assert "BEGIN of file_search results." in result
        assert "Test content" in result
        assert "document_id: test_source" in result
        assert "score: 0.9500" in result
        assert "END of file_search results." in result
        assert 'answer the user\'s query: "test query"' in result

    def test_format_multiple_chunks(self) -> None:
        """Test formatting with multiple chunks."""
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.9),
            RAGChunk(content="Content 2", source="source_2", score=0.8),
            RAGChunk(
                content="Content 3",
                source="source_3",
                score=0.7,
                attributes={"url": "http://example.com"},
            ),
        ]
        result = _format_rag_context(chunks, "test query")

        assert "file_search found 3 chunks:" in result
        assert "Content 1" in result
        assert "Content 2" in result
        assert "Content 3" in result
        assert "document_id: source_1" in result
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result

    def test_format_chunk_with_attributes(self) -> None:
        """Test formatting chunk with additional attributes."""
        chunks = [
            RAGChunk(
                content="Test content",
                source="test_source",
                score=0.85,
                attributes={"title": "Test Doc", "author": "John Doe"},
            )
        ]
        result = _format_rag_context(chunks, "test query")

        assert "attributes:" in result
        assert "title" in result or "author" in result


class TestExtractSolrDocumentMetadata:
    """Tests for _extract_solr_document_metadata function."""

    def test_extract_from_dict_metadata(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test extraction from dict-based metadata."""
        chunk = mocker.Mock()
        chunk.metadata = {
            "doc_id": "doc_123",
            "title": "Test Document",
            "reference_url": "https://example.com/doc",
        }

        doc_id, title, reference_url = _extract_solr_document_metadata(chunk)

        assert doc_id == "doc_123"
        assert title == "Test Document"
        assert reference_url == "https://example.com/doc"

    def test_extract_from_chunk_metadata_object(  # type: ignore[no-untyped-def]
        self, mocker
    ) -> None:
        """Test extraction from typed chunk_metadata object."""
        chunk_meta = mocker.Mock()
        chunk_meta.doc_id = "doc_456"
        chunk_meta.title = "Another Document"
        chunk_meta.reference_url = "https://example.com/another"

        chunk = mocker.Mock()
        chunk.metadata = {}
        chunk.chunk_metadata = chunk_meta

        doc_id, title, reference_url = _extract_solr_document_metadata(chunk)

        assert doc_id == "doc_456"
        assert title == "Another Document"
        assert reference_url == "https://example.com/another"

    def test_extract_with_missing_fields(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test extraction when some fields are missing."""
        chunk = mocker.Mock()
        chunk.metadata = {"doc_id": "doc_789"}

        doc_id, title, reference_url = _extract_solr_document_metadata(chunk)

        assert doc_id == "doc_789"
        assert title is None
        assert reference_url is None


class TestBuildDocumentUrl:
    """Tests for _build_document_url function."""

    def test_offline_mode_with_doc_id(self) -> None:
        """Test URL building in offline mode with doc_id."""
        doc_url, reference_doc = _build_document_url(
            offline=True, doc_id="doc_123", reference_url=None
        )

        assert doc_url == constants.MIMIR_DOC_URL + "doc_123"
        assert reference_doc == "doc_123"

    def test_online_mode_with_reference_url(self) -> None:
        """Test URL building in online mode with reference_url."""
        doc_url, reference_doc = _build_document_url(
            offline=False,
            doc_id="doc_123",
            reference_url="https://docs.example.com/page",
        )

        assert doc_url == "https://docs.example.com/page"
        assert reference_doc == "https://docs.example.com/page"

    def test_online_mode_without_http(self) -> None:
        """Test online mode when reference_url doesn't start with http."""
        doc_url, reference_doc = _build_document_url(
            offline=False, doc_id="doc_123", reference_url="relative/path"
        )

        assert doc_url == constants.MIMIR_DOC_URL + "relative/path"
        assert reference_doc == "relative/path"

    def test_offline_mode_without_doc_id(self) -> None:
        """Test offline mode when doc_id is None."""
        doc_url, reference_doc = _build_document_url(
            offline=True, doc_id=None, reference_url="https://example.com"
        )

        assert doc_url == ""
        assert reference_doc is None


class TestConvertSolrChunksToRagFormat:
    """Tests for _convert_solr_chunks_to_rag_format function."""

    def test_convert_with_metadata_offline(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test conversion with metadata in offline mode."""
        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.metadata = {"parent_id": "parent_123"}
        chunk.chunk_metadata = None

        result = _convert_solr_chunks_to_rag_format([chunk], [0.85], offline=True)

        assert len(result) == 1
        assert result[0].content == "Test content"
        assert result[0].source == constants.OKP_RAG_ID
        assert result[0].score == 0.85
        assert "doc_url" in result[0].attributes
        assert "parent_123" in result[0].attributes["doc_url"]

    def test_convert_with_metadata_online(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test conversion with metadata in online mode."""
        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.metadata = {"reference_url": "https://example.com/doc"}
        chunk.chunk_metadata = None

        result = _convert_solr_chunks_to_rag_format([chunk], [0.75], offline=False)

        assert len(result) == 1
        assert result[0].attributes["doc_url"] == "https://example.com/doc"

    def test_convert_with_chunk_metadata(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test conversion with chunk_metadata object."""
        chunk_meta = mocker.Mock()
        chunk_meta.document_id = "doc_456"

        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.metadata = {}
        chunk.chunk_metadata = chunk_meta

        result = _convert_solr_chunks_to_rag_format([chunk], [0.9], offline=True)

        assert len(result) == 1
        assert result[0].attributes["document_id"] == "doc_456"

    def test_convert_multiple_chunks(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test conversion of multiple chunks."""
        chunk1 = mocker.Mock()
        chunk1.content = "Content 1"
        chunk1.metadata = {"parent_id": "parent_1"}
        chunk1.chunk_metadata = None

        chunk2 = mocker.Mock()
        chunk2.content = "Content 2"
        chunk2.metadata = {"parent_id": "parent_2"}
        chunk2.chunk_metadata = None

        result = _convert_solr_chunks_to_rag_format(
            [chunk1, chunk2], [0.9, 0.8], offline=True
        )

        assert len(result) == 2
        assert result[0].content == "Content 1"
        assert result[1].content == "Content 2"
        assert result[0].score == 0.9
        assert result[1].score == 0.8


class TestFetchByokRag:
    """Tests for _fetch_byok_rag async function."""

    @pytest.mark.asyncio
    async def test_byok_no_inline_ids(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when no inline BYOK sources are configured."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.configuration.rag.inline = []
        config_mock.configuration.byok_rag = []
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()
        rag_chunks, referenced_docs = await _fetch_byok_rag(client_mock, "test query")

        assert rag_chunks == []
        assert referenced_docs == []
        client_mock.vector_io.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_byok_enabled_success(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test successful BYOK RAG fetch when inline IDs are configured."""
        # Mock configuration
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_mock = mocker.Mock()
        byok_rag_mock.rag_id = "rag_1"
        byok_rag_mock.vector_db_id = "vs_1"
        config_mock.configuration.rag.inline = ["rag_1"]
        config_mock.configuration.byok_rag = [byok_rag_mock]
        config_mock.score_multiplier_mapping = {"vs_1": 1.5}
        config_mock.rag_id_mapping = {"vs_1": "rag_1"}
        mocker.patch("utils.vector_search.configuration", config_mock)

        # Mock search response
        chunk_mock = mocker.Mock()
        chunk_mock.content = "Test content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {
            "document_id": "doc_1",
            "title": "Test Doc",
            "reference_url": "https://example.com/doc",
        }

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.9]

        # Mock client
        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        rag_chunks, referenced_docs = await _fetch_byok_rag(client_mock, "test query")

        assert len(rag_chunks) > 0
        assert rag_chunks[0].content == "Test content"
        assert len(referenced_docs) > 0


class TestFetchSolrRag:
    """Tests for _fetch_solr_rag async function."""

    @pytest.mark.asyncio
    async def test_solr_disabled(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when Solr is disabled."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = False
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()
        rag_chunks, referenced_docs = await _fetch_solr_rag(client_mock, "test query")

        assert rag_chunks == []
        assert referenced_docs == []
        client_mock.vector_io.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_solr_enabled_success(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test successful Solr RAG fetch."""
        # Mock configuration
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = True
        config_mock.okp.offline = True
        mocker.patch("utils.vector_search.configuration", config_mock)

        # Mock chunk
        chunk_mock = mocker.Mock()
        chunk_mock.content = "Solr content"
        chunk_mock.metadata = {"parent_id": "parent_1", "title": "Solr Doc"}
        chunk_mock.chunk_metadata = None

        # Mock query response
        query_response = mocker.Mock()
        query_response.chunks = [chunk_mock]
        query_response.scores = [0.85]

        # Mock client
        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = query_response

        rag_chunks, _referenced_docs = await _fetch_solr_rag(client_mock, "test query")

        assert len(rag_chunks) > 0
        assert rag_chunks[0].content == "Solr content"
        assert rag_chunks[0].source == constants.OKP_RAG_ID


class TestBuildRagContext:
    """Tests for build_rag_context async function."""

    @pytest.mark.asyncio
    async def test_both_sources_disabled(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when both BYOK inline and Solr inline are not configured."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.configuration.rag.inline = []
        config_mock.configuration.byok_rag = []
        config_mock.inline_solr_enabled = False
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()
        context = await build_rag_context(client_mock, "test query", None)

        assert context.context_text == ""
        assert context.rag_chunks == []
        assert context.referenced_documents == []

    @pytest.mark.asyncio
    async def test_byok_enabled_only(self, mocker) -> None:  # type: ignore[no-untyped-def]
        """Test when only inline BYOK is configured."""
        # Mock configuration
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_mock = mocker.Mock()
        byok_rag_mock.rag_id = "rag_1"
        byok_rag_mock.vector_db_id = "vs_1"
        config_mock.configuration.rag.inline = ["rag_1"]
        config_mock.configuration.byok_rag = [byok_rag_mock]
        config_mock.inline_solr_enabled = False
        config_mock.score_multiplier_mapping = {"vs_1": 1.0}
        config_mock.rag_id_mapping = {"vs_1": "rag_1"}
        mocker.patch("utils.vector_search.configuration", config_mock)

        # Mock chunk
        chunk_mock = mocker.Mock()
        chunk_mock.content = "BYOK content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {"document_id": "doc_1"}

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.9]

        # Mock client
        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        context = await build_rag_context(client_mock, "test query", None)

        assert len(context.rag_chunks) > 0
        assert "BYOK content" in context.context_text
        assert "file_search found" in context.context_text
