"""Unit tests for vector search utilities."""

# pylint: disable=too-many-lines

import pytest
from pydantic import AnyUrl
from pytest_mock import MockerFixture

import constants
from configuration import AppConfig
from models.common.query import SolrVectorSearchRequest
from models.common.turn_summary import RAGChunk
from utils.reranker import (
    _get_cross_encoder,
    apply_byok_rerank_boost,
    rerank_chunks_with_cross_encoder,
)
from utils.vector_search import (
    _build_document_url,
    _build_query_params,
    _convert_solr_chunks_to_rag_format,
    _extract_byok_rag_chunks,
    _extract_solr_document_metadata,
    _fetch_byok_rag,
    _fetch_solr_rag,
    _format_rag_context,
    _get_okp_base_url,
    _get_solr_vector_store_ids,
    _is_solr_enabled,
    build_rag_context,
)


class TestIsSolrEnabled:
    """Tests for _is_solr_enabled function."""

    def test_solr_enabled_true(self, mocker: MockerFixture) -> None:
        """Test when Solr is enabled in configuration."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = True
        mocker.patch("utils.vector_search.configuration", config_mock)
        assert _is_solr_enabled() is True

    def test_solr_enabled_false(self, mocker: MockerFixture) -> None:
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
        solr = SolrVectorSearchRequest.model_validate({"filter": "value"})
        params = _build_query_params(solr=solr)

        assert params["solr"] == {"filter": "value"}
        assert params["k"] == constants.SOLR_VECTOR_SEARCH_DEFAULT_K

    def test_custom_mode(self) -> None:
        """Request mode overrides the default Solr vector_io mode."""
        solr = SolrVectorSearchRequest(mode="lexical")
        params = _build_query_params(solr=solr)

        assert params["mode"] == "lexical"
        assert "solr" not in params

    def test_mode_with_solr_filters(self) -> None:
        """Custom mode is combined with solr filter payload."""
        solr = SolrVectorSearchRequest(
            mode="semantic", filters={"fq": ["product:*openshift*"]}
        )
        params = _build_query_params(solr=solr)

        assert params["mode"] == "semantic"
        assert params["solr"] == {"fq": ["product:*openshift*"]}

    def test_mode_with_only_filters(self) -> None:
        """Mode is set to default value when only filters are provided."""
        solr = SolrVectorSearchRequest(filters={"fq": ["product:*openshift*"]})
        params = _build_query_params(solr=solr)

        assert params["mode"] == constants.SOLR_VECTOR_SEARCH_DEFAULT_MODE
        assert params["solr"] == {"fq": ["product:*openshift*"]}


class TestExtractByokRagChunks:
    """Tests for _extract_byok_rag_chunks function."""

    def test_extract_chunks_with_metadata(self, mocker: MockerFixture) -> None:
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

    def test_extract_chunks_without_metadata(self, mocker: MockerFixture) -> None:
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

    def test_extract_from_dict_metadata(self, mocker: MockerFixture) -> None:
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

    def test_extract_from_chunk_metadata_object(self, mocker: MockerFixture) -> None:
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

    def test_extract_with_missing_fields(self, mocker: MockerFixture) -> None:
        """Test extraction when some fields are missing."""
        chunk = mocker.Mock()
        chunk.metadata = {"doc_id": "doc_789"}

        doc_id, title, reference_url = _extract_solr_document_metadata(chunk)

        assert doc_id == "doc_789"
        assert title is None
        assert reference_url is None


class TestGetOkpBaseUrl:
    """Tests for _get_okp_base_url function (config rhokp_url vs default)."""

    def test_returns_custom_host_when_rhokp_url_configured(
        self, mocker: MockerFixture
    ) -> None:
        """When rhokp_url is set in config, returned base URL uses that value."""
        custom = "https://custom.okp.example.com"
        config_mock = mocker.Mock()
        config_mock.okp.rhokp_url = custom
        mocker.patch("utils.vector_search.configuration", config_mock)
        assert _get_okp_base_url() == AnyUrl(custom)

    def test_returns_default_when_rhokp_url_unset(self, mocker: MockerFixture) -> None:
        """When rhokp_url is missing or empty, returned base URL uses default."""
        config_mock = mocker.Mock()
        config_mock.okp.rhokp_url = None
        mocker.patch("utils.vector_search.configuration", config_mock)
        assert _get_okp_base_url() == AnyUrl(constants.RH_SERVER_OKP_DEFAULT_URL)
        assert str(_get_okp_base_url()).startswith("http://")


class TestBuildDocumentUrl:
    """Tests for _build_document_url function."""

    def test_offline_mode_with_doc_id(self, mocker: MockerFixture) -> None:
        """Test URL building in offline mode with doc_id."""
        config_mock = mocker.Mock()
        config_mock.okp.rhokp_url = "https://mimir.test"
        mocker.patch("utils.vector_search.configuration", config_mock)
        doc_url, reference_doc = _build_document_url(
            offline=True, doc_id="doc_123", reference_url=None
        )
        assert doc_url == "https://mimir.test/doc_123"
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

    def test_online_mode_without_http(self, mocker: MockerFixture) -> None:
        """Test online mode when reference_url doesn't start with http."""
        config_mock = mocker.Mock()
        config_mock.okp.rhokp_url = "https://mimir.test"
        mocker.patch("utils.vector_search.configuration", config_mock)
        doc_url, reference_doc = _build_document_url(
            offline=False, doc_id="doc_123", reference_url="relative/path"
        )
        assert doc_url == "https://mimir.test/relative/path"
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

    def test_convert_with_metadata_offline(self, mocker: MockerFixture) -> None:
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
        assert result[0].attributes is not None
        assert "doc_url" in result[0].attributes
        assert "parent_123" in result[0].attributes["doc_url"]

    def test_convert_with_metadata_online(self, mocker: MockerFixture) -> None:
        """Test conversion with metadata in online mode."""
        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.metadata = {"reference_url": "https://example.com/doc"}
        chunk.chunk_metadata = None

        result = _convert_solr_chunks_to_rag_format([chunk], [0.75], offline=False)

        assert len(result) == 1
        assert result[0].attributes is not None
        assert result[0].attributes["doc_url"] == "https://example.com/doc"

    def test_convert_with_chunk_metadata(self, mocker: MockerFixture) -> None:
        """Test conversion with chunk_metadata object."""
        chunk_meta = mocker.Mock()
        chunk_meta.document_id = "doc_456"

        chunk = mocker.Mock()
        chunk.content = "Test content"
        chunk.metadata = {}
        chunk.chunk_metadata = chunk_meta

        result = _convert_solr_chunks_to_rag_format([chunk], [0.9], offline=True)

        assert len(result) == 1
        assert result[0].attributes is not None
        assert result[0].attributes["document_id"] == "doc_456"

    def test_convert_multiple_chunks(self, mocker: MockerFixture) -> None:
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
    async def test_byok_no_inline_ids(self, mocker: MockerFixture) -> None:
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
    async def test_byok_enabled_success(self, mocker: MockerFixture) -> None:
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

    @pytest.mark.asyncio
    async def test_user_facing_ids_translated_to_internal_ids(
        self, mocker: MockerFixture
    ) -> None:
        """Test that user-facing rag_ids (vector_store_ids) are translated to llama-stack ids."""
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_mock = mocker.Mock()
        byok_rag_mock.rag_id = "my-kb"
        byok_rag_mock.vector_db_id = "vs-internal-001"
        config_mock.configuration.byok_rag = [byok_rag_mock]
        config_mock.configuration.rag.inline = ["my-kb"]
        config_mock.score_multiplier_mapping = {"vs-internal-001": 1.0}
        config_mock.rag_id_mapping = {"vs-internal-001": "my-kb"}
        mocker.patch("utils.vector_search.configuration", config_mock)

        chunk_mock = mocker.Mock()
        chunk_mock.content = "Test content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {"document_id": "doc_1"}

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.9]

        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        # Pass user-facing rag_id "my-kb"
        await _fetch_byok_rag(client_mock, "test query", vector_store_ids=["my-kb"])

        # Must be called with the internal llama-stack ID, not the user-facing "my-kb"
        client_mock.vector_io.query.assert_called_once_with(
            vector_store_id="vs-internal-001",
            query="test query",
            params={"max_chunks": constants.BYOK_RAG_MAX_CHUNKS, "mode": "vector"},
        )

    @pytest.mark.asyncio
    async def test_multiple_user_facing_ids_each_translated(
        self, mocker: MockerFixture
    ) -> None:
        """Test that multiple user-facing rag_ids are each translated to their vector_store_id."""
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_1 = mocker.Mock()
        byok_rag_1.rag_id = "kb-part1"
        byok_rag_1.vector_db_id = "vs-aaa-111"
        byok_rag_2 = mocker.Mock()
        byok_rag_2.rag_id = "kb-part2"
        byok_rag_2.vector_db_id = "vs-bbb-222"
        config_mock.configuration.byok_rag = [byok_rag_1, byok_rag_2]
        config_mock.configuration.rag.inline = ["kb-part1", "kb-part2"]
        config_mock.score_multiplier_mapping = {"vs-aaa-111": 1.0, "vs-bbb-222": 1.0}
        config_mock.rag_id_mapping = {
            "vs-aaa-111": "kb-part1",
            "vs-bbb-222": "kb-part2",
        }
        mocker.patch("utils.vector_search.configuration", config_mock)

        chunk_mock = mocker.Mock()
        chunk_mock.content = "Content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {}

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.8]

        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        # Pass two user-facing rag_ids
        await _fetch_byok_rag(
            client_mock, "test query", vector_store_ids=["kb-part1", "kb-part2"]
        )

        # Each call must use the internal ID, not the user-facing name
        call_args = [
            call.kwargs["vector_store_id"]
            for call in client_mock.vector_io.query.call_args_list
        ]
        assert "vs-aaa-111" in call_args
        assert "vs-bbb-222" in call_args
        assert "kb-part1" not in call_args
        assert "kb-part2" not in call_args

    @pytest.mark.asyncio
    async def test_no_inline_rag_configured_skips_byok(
        self, mocker: MockerFixture
    ) -> None:
        """Test that BYOK inline RAG is skipped when rag.inline is empty."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.configuration.rag.inline = []
        config_mock.configuration.byok_rag = []
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()

        rag_chunks, referenced_docs = await _fetch_byok_rag(
            client_mock, "test query", vector_store_ids=["some-id"]
        )

        assert rag_chunks == []
        assert referenced_docs == []
        client_mock.vector_io.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_id_not_in_inline_config_skips_byok(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a request vector_store_id not registered in rag.inline is filtered out."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.configuration.rag.inline = ["registered-id"]
        config_mock.configuration.byok_rag = []
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()

        rag_chunks, referenced_docs = await _fetch_byok_rag(
            client_mock, "test query", vector_store_ids=["unregistered-id"]
        )

        assert rag_chunks == []
        assert referenced_docs == []
        client_mock.vector_io.query.assert_not_called()


class TestFetchSolrRag:
    """Tests for _fetch_solr_rag async function."""

    @pytest.mark.asyncio
    async def test_solr_disabled(self, mocker: MockerFixture) -> None:
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
    async def test_solr_enabled_success(self, mocker: MockerFixture) -> None:
        """Test successful Solr RAG fetch."""
        # Mock configuration
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = True
        config_mock.okp.offline = True
        config_mock.okp.rhokp_url = "https://okp.test"
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

    @pytest.mark.asyncio
    async def test_solr_enabled_passes_request_mode_to_vector_io(
        self, mocker: MockerFixture
    ) -> None:
        """OKP vector_io.query receives the mode from the API request."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.inline_solr_enabled = True
        config_mock.okp.offline = True
        config_mock.okp.rhokp_url = "https://okp.test"
        mocker.patch("utils.vector_search.configuration", config_mock)

        chunk_mock = mocker.Mock()
        chunk_mock.content = "Solr content"
        chunk_mock.metadata = {"parent_id": "parent_1", "title": "Solr Doc"}
        chunk_mock.chunk_metadata = None

        query_response = mocker.Mock()
        query_response.chunks = [chunk_mock]
        query_response.scores = [0.85]

        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = query_response

        await _fetch_solr_rag(
            client_mock,
            "test query",
            SolrVectorSearchRequest(mode="semantic", filters={"fq": ["x:y"]}),
        )

        client_mock.vector_io.query.assert_called_once()
        call_kwargs = client_mock.vector_io.query.call_args.kwargs
        assert call_kwargs["params"]["mode"] == "semantic"
        assert call_kwargs["params"]["solr"] == {"fq": ["x:y"]}


class TestBuildRagContext:
    """Tests for build_rag_context async function."""

    @pytest.mark.asyncio
    async def test_both_sources_disabled(self, mocker: MockerFixture) -> None:
        """Test when both BYOK inline and Solr inline are not configured."""
        config_mock = mocker.Mock(spec=AppConfig)
        config_mock.configuration.rag.inline = []
        config_mock.configuration.byok_rag = []
        config_mock.inline_solr_enabled = False
        mocker.patch("utils.vector_search.configuration", config_mock)

        client_mock = mocker.AsyncMock()
        context = await build_rag_context(client_mock, "passed", "test query", None)

        assert context.context_text == ""
        assert context.rag_chunks == []
        assert context.referenced_documents == []

    @pytest.mark.asyncio
    async def test_byok_enabled_only(self, mocker: MockerFixture) -> None:
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

        context = await build_rag_context(client_mock, "passed", "test query", None)

        assert len(context.rag_chunks) > 0
        assert "BYOK content" in context.context_text
        assert "file_search found" in context.context_text

    @pytest.mark.asyncio
    async def test_reranker_enabled_calls_cross_encoder(
        self, mocker: MockerFixture
    ) -> None:
        """Test that cross-encoder is called when reranker is enabled."""
        # Mock configuration with reranker enabled
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_mock = mocker.Mock()
        byok_rag_mock.rag_id = "rag_1"
        byok_rag_mock.vector_db_id = "vs_1"
        config_mock.configuration.rag.inline = ["rag_1"]
        config_mock.configuration.byok_rag = [byok_rag_mock]
        config_mock.inline_solr_enabled = False
        config_mock.score_multiplier_mapping = {"vs_1": 1.0}
        config_mock.rag_id_mapping = {"vs_1": "rag_1"}
        config_mock.reranker.enabled = True
        config_mock.reranker.model = "test-model"
        mocker.patch("utils.vector_search.configuration", config_mock)
        mocker.patch("utils.reranker.configuration", config_mock)

        # Mock BYOK search response
        chunk_mock = mocker.Mock()
        chunk_mock.content = "BYOK content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {"document_id": "doc_1"}

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.9]

        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        # Mock cross-encoder reranking function
        mock_rerank = mocker.patch(
            "utils.vector_search.rerank_chunks_with_cross_encoder"
        )
        mock_rerank.return_value = [
            RAGChunk(content="BYOK content", source="rag_1", score=0.95)
        ]

        context = await build_rag_context(client_mock, "passed", "test query", None)

        # Verify cross-encoder was called
        mock_rerank.assert_called_once()
        assert mock_rerank.call_args[0][0] == "test query"  # query parameter
        # Check that chunks were passed as second argument
        assert len(mock_rerank.call_args[0][1]) == 1  # chunks parameter

        assert len(context.rag_chunks) > 0

    @pytest.mark.asyncio
    async def test_reranker_disabled_skips_cross_encoder(
        self, mocker: MockerFixture
    ) -> None:
        """Test that cross-encoder is skipped when reranker is disabled."""
        # Mock configuration with reranker disabled
        config_mock = mocker.Mock(spec=AppConfig)
        byok_rag_mock = mocker.Mock()
        byok_rag_mock.rag_id = "rag_1"
        byok_rag_mock.vector_db_id = "vs_1"
        config_mock.configuration.rag.inline = ["rag_1"]
        config_mock.configuration.byok_rag = [byok_rag_mock]
        config_mock.inline_solr_enabled = False
        config_mock.score_multiplier_mapping = {"vs_1": 1.0}
        config_mock.rag_id_mapping = {"vs_1": "rag_1"}
        config_mock.reranker.enabled = False
        mocker.patch("utils.vector_search.configuration", config_mock)

        # Mock BYOK search response
        chunk_mock = mocker.Mock()
        chunk_mock.content = "BYOK content"
        chunk_mock.chunk_id = "chunk_1"
        chunk_mock.metadata = {"document_id": "doc_1"}

        search_response = mocker.Mock()
        search_response.chunks = [chunk_mock]
        search_response.scores = [0.9]

        client_mock = mocker.AsyncMock()
        client_mock.vector_io.query.return_value = search_response

        # Mock cross-encoder reranking function
        mock_rerank = mocker.patch("utils.reranker.rerank_chunks_with_cross_encoder")

        context = await build_rag_context(client_mock, "passed", "test query", None)

        # Verify cross-encoder was NOT called
        mock_rerank.assert_not_called()

        assert len(context.rag_chunks) > 0


class TestGetCrossEncoder:
    """Tests for _get_cross_encoder function."""

    @pytest.mark.asyncio
    async def test_loads_model_successfully(self, mocker: MockerFixture) -> None:
        """Test successful model loading and caching when reranker is enabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be enabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = True
        mocker.patch("utils.vector_search.configuration", mock_config)
        mocker.patch("utils.reranker.configuration", mock_config)

        # Mock the CrossEncoder class by patching the import
        mock_model_instance = mocker.Mock()
        mock_cross_encoder = mocker.Mock(return_value=mock_model_instance)

        # Patch the import at the module level where it happens
        mocker.patch.dict(
            "sys.modules",
            {"sentence_transformers": mocker.Mock(CrossEncoder=mock_cross_encoder)},
        )

        # Mock asyncio.to_thread
        mocker.patch("asyncio.to_thread", return_value=mock_model_instance)

        model = await _get_cross_encoder("test-model")

        assert model == mock_model_instance

    @pytest.mark.asyncio
    async def test_caches_loaded_model(self, mocker: MockerFixture) -> None:
        """Test that models are cached and not reloaded when reranker is enabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be enabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = True
        mocker.patch("utils.vector_search.configuration", mock_config)
        mocker.patch("utils.reranker.configuration", mock_config)

        mock_model_instance = mocker.Mock()
        mock_cross_encoder = mocker.Mock(return_value=mock_model_instance)

        # Patch the import at the module level where it happens
        mocker.patch.dict(
            "sys.modules",
            {"sentence_transformers": mocker.Mock(CrossEncoder=mock_cross_encoder)},
        )

        # Mock asyncio.to_thread
        mocker.patch("asyncio.to_thread", return_value=mock_model_instance)

        # First call should load the model
        model1 = await _get_cross_encoder("test-model")
        # Second call should return cached model
        model2 = await _get_cross_encoder("test-model")

        assert model1 == model2 == mock_model_instance

    @pytest.mark.asyncio
    async def test_handles_import_error(self, mocker: MockerFixture) -> None:
        """Test graceful handling of sentence_transformers import error when reranker is enabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be enabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = True
        mocker.patch("utils.vector_search.configuration", mock_config)
        mocker.patch("utils.reranker.configuration", mock_config)

        # Mock asyncio.to_thread to raise an exception
        mocker.patch("asyncio.to_thread", side_effect=Exception("Model loading failed"))

        model = await _get_cross_encoder("test-model")

        assert model is None

    @pytest.mark.asyncio
    async def test_handles_model_loading_error(self, mocker: MockerFixture) -> None:
        """Test graceful handling of model instantiation error when reranker is enabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be enabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = True
        mocker.patch("utils.vector_search.configuration", mock_config)
        mocker.patch("utils.reranker.configuration", mock_config)

        # Mock asyncio.to_thread to raise an exception
        mocker.patch("asyncio.to_thread", side_effect=Exception("Model loading failed"))

        model = await _get_cross_encoder("test-model")

        assert model is None

    @pytest.mark.asyncio
    async def test_returns_none_when_reranker_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test that _get_cross_encoder returns None when reranker is disabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be disabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = False
        mocker.patch("utils.vector_search.configuration", mock_config)

        # Mock the CrossEncoder class - should not be called since reranker is disabled
        mock_cross_encoder = mocker.Mock()
        mocker.patch.dict(
            "sys.modules",
            {"sentence_transformers": mocker.Mock(CrossEncoder=mock_cross_encoder)},
        )

        model = await _get_cross_encoder("test-model")

        assert model is None
        # Verify CrossEncoder was not instantiated since reranker is disabled
        mock_cross_encoder.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_cache_when_reranker_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test that no caching occurs when reranker is disabled."""
        # Clear the cache for testing
        # pylint: disable=import-outside-toplevel
        from utils.reranker import _cross_encoder_models

        _cross_encoder_models.clear()

        # Mock reranker configuration to be disabled
        mock_config = mocker.Mock()
        mock_config.reranker.enabled = False
        mocker.patch("utils.vector_search.configuration", mock_config)

        # Call multiple times
        model1 = await _get_cross_encoder("test-model")
        model2 = await _get_cross_encoder("test-model")

        assert model1 is None
        assert model2 is None
        # Verify cache remains empty
        assert "test-model" not in _cross_encoder_models


class TestRerankChunksWithCrossEncoder:
    """Tests for rerank_chunks_with_cross_encoder function."""

    @pytest.mark.asyncio
    async def test_empty_chunks(self) -> None:
        """Test reranking with empty chunks list."""
        result = await rerank_chunks_with_cross_encoder("test query", [], 5)
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_reranking(self, mocker: MockerFixture) -> None:
        """Test successful reranking with combined cross-encoder and original scores."""
        # Create test chunks
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.5),
            RAGChunk(content="Content 2", source="source_2", score=0.3),
            RAGChunk(content="Content 3", source="source_3", score=0.8),
        ]

        # Mock cross-encoder model and prediction
        mock_model = mocker.Mock()
        mock_model.predict.return_value = [2.5, 1.0, 3.0]  # Raw scores

        # Mock _get_cross_encoder to return our mock model
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 3)

        # Verify model was called with correct pairs
        expected_pairs = [
            ("test query", "Content 1"),
            ("test query", "Content 2"),
            ("test query", "Content 3"),
        ]
        mock_model.predict.assert_called_once_with(expected_pairs)

        # Verify results are sorted by combined scores (highest first)
        assert len(result) == 3
        assert result[0].content == "Content 3"  # Highest combined score
        assert result[1].content == "Content 1"  # Middle combined score
        assert result[2].content == "Content 2"  # Lowest combined score

        # Verify scores are combined (30% cross-encoder + 70% original weighted scores)
        # Content 3: 0.3 * 1.0 + 0.7 * 1.0 = 1.0
        # Content 1: 0.3 * 0.75 + 0.7 * 0.4 = 0.505 (approximately)
        # Content 2: 0.3 * 0.0 + 0.7 * 0.0 = 0.0
        assert result[0].score == 1.0
        assert abs(result[1].score - 0.505) < 0.01  # Allow small floating point errors
        assert result[2].score == 0.0

    @pytest.mark.asyncio
    async def test_top_k_limiting(self, mocker: MockerFixture) -> None:
        """Test that top_k limits the number of returned chunks."""
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.5),
            RAGChunk(content="Content 2", source="source_2", score=0.3),
            RAGChunk(content="Content 3", source="source_3", score=0.8),
        ]

        mock_model = mocker.Mock()
        mock_model.predict.return_value = [2.5, 1.0, 3.0]
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 2)

        assert len(result) == 2  # Limited to top_k=2
        assert result[0].content == "Content 3"
        assert result[1].content == "Content 1"

    @pytest.mark.asyncio
    async def test_identical_scores_normalization(self, mocker: MockerFixture) -> None:
        """Test normalization when all cross-encoder scores are identical."""
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.5),
            RAGChunk(content="Content 2", source="source_2", score=0.3),
        ]

        mock_model = mocker.Mock()
        mock_model.predict.return_value = [1.5, 1.5]  # Identical cross-encoder scores
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 2)

        # When cross-encoder scores are identical (both normalized to 0.5),
        # combined scores should favor original scores
        # Content 1: 0.3 * 0.5 + 0.7 * 1.0 = 0.85 (orig score 0.5 normalized to 1.0)
        # Content 2: 0.3 * 0.5 + 0.7 * 0.0 = 0.15 (orig score 0.3 normalized to 0.0)
        assert len(result) == 2
        assert result[0].content == "Content 1"  # Higher original score
        assert result[1].content == "Content 2"  # Lower original score
        assert result[0].score == 0.85
        assert result[1].score == 0.15

    @pytest.mark.asyncio
    async def test_single_chunk_normalization(self, mocker: MockerFixture) -> None:
        """Test normalization with single chunk."""
        chunks = [RAGChunk(content="Content 1", source="source_1", score=0.5)]

        mock_model = mocker.Mock()
        mock_model.predict.return_value = [2.5]
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 1)

        # Single chunk should get score 1.0
        assert len(result) == 1
        assert result[0].score == 1.0

    @pytest.mark.asyncio
    async def test_model_loading_failure_fallback(self, mocker: MockerFixture) -> None:
        """Test fallback to original scores when model loading fails."""
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.8),
            RAGChunk(content="Content 2", source="source_2", score=0.6),
        ]

        # Mock _get_cross_encoder to return None (loading failed)
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=None,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 2)

        # Should return chunks sorted by original scores
        assert len(result) == 2
        assert result[0].content == "Content 1"  # Higher original score
        assert result[1].content == "Content 2"
        assert result[0].score == 0.8  # Original scores preserved
        assert result[1].score == 0.6

    @pytest.mark.asyncio
    async def test_prediction_failure_fallback(self, mocker: MockerFixture) -> None:
        """Test fallback when model.predict() raises exception."""
        chunks = [
            RAGChunk(content="Content 1", source="source_1", score=0.9),
            RAGChunk(content="Content 2", source="source_2", score=0.7),
        ]

        mock_model = mocker.Mock()
        mock_model.predict.side_effect = Exception("Prediction failed")
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 2)

        # Should fallback to original scores
        assert len(result) == 2
        assert result[0].content == "Content 1"
        assert result[0].score == 0.9

    @pytest.mark.asyncio
    async def test_numpy_array_scores(self, mocker: MockerFixture) -> None:
        """Test handling of numpy array scores from model prediction."""
        chunks = [RAGChunk(content="Content 1", source="source_1", score=0.5)]

        # Mock numpy array with tolist() method
        mock_scores = mocker.Mock()
        mock_scores.tolist.return_value = [2.5]

        mock_model = mocker.Mock()
        mock_model.predict.return_value = mock_scores
        mocker.patch(
            "utils.reranker._get_cross_encoder",
            new_callable=mocker.AsyncMock,
            return_value=mock_model,
        )

        result = await rerank_chunks_with_cross_encoder("test query", chunks, 1)

        # Should successfully handle numpy array conversion
        assert len(result) == 1
        assert result[0].score == 1.0
        mock_scores.tolist.assert_called_once()


class TestApplyByokRerankBoost:
    """Tests for apply_byok_rerank_boost function."""

    def test_empty_chunks(self) -> None:
        """Test boost application with empty chunks list."""
        result = apply_byok_rerank_boost([])
        assert not result

    def test_boost_byok_chunks_only(self) -> None:
        """Test that only BYOK chunks (non-OKP) get boosted."""
        chunks = [
            RAGChunk(content="BYOK content", source="byok_store", score=0.8),
            RAGChunk(content="OKP content", source=constants.OKP_RAG_ID, score=0.6),
            RAGChunk(content="Another BYOK", source="another_store", score=0.7),
        ]

        result = apply_byok_rerank_boost(chunks, boost=2.0)

        assert len(result) == 3

        # Find chunks by content for assertion
        byok_chunk = next(c for c in result if c.content == "BYOK content")
        okp_chunk = next(c for c in result if c.content == "OKP content")
        another_byok = next(c for c in result if c.content == "Another BYOK")

        # BYOK chunks should be boosted
        assert byok_chunk.score == 1.6  # 0.8 * 2.0
        assert another_byok.score == 1.4  # 0.7 * 2.0

        # OKP chunk should remain unchanged
        assert okp_chunk.score == 0.6

    def test_sorting_by_boosted_scores(self) -> None:
        """Test that chunks are sorted by boosted scores in descending order."""
        chunks = [
            RAGChunk(content="Low BYOK", source="byok_store", score=0.5),
            RAGChunk(content="High OKP", source=constants.OKP_RAG_ID, score=0.9),
            RAGChunk(content="Mid BYOK", source="another_store", score=0.7),
        ]

        result = apply_byok_rerank_boost(chunks, boost=2.0)

        # After boosting: Low BYOK=1.0, High OKP=0.9, Mid BYOK=1.4
        # Sorted order should be: Mid BYOK (1.4), Low BYOK (1.0), High OKP (0.9)
        assert result[0].content == "Mid BYOK"
        assert result[1].content == "Low BYOK"
        assert result[2].content == "High OKP"

    def test_default_boost_factor(self) -> None:
        """Test that default boost factor is applied correctly."""
        chunks = [RAGChunk(content="BYOK content", source="byok_store", score=0.8)]

        result = apply_byok_rerank_boost(chunks)  # Using default boost

        # Default boost should be constants.BYOK_RAG_RERANK_BOOST (1.2)
        assert result[0].score == 0.8 * constants.BYOK_RAG_RERANK_BOOST

    def test_none_scores_handled(self) -> None:
        """Test handling of chunks with None scores."""
        chunks = [
            RAGChunk(content="BYOK with score", source="byok_store", score=0.8),
            RAGChunk(content="BYOK no score", source="byok_store", score=None),
            RAGChunk(content="OKP no score", source=constants.OKP_RAG_ID, score=None),
        ]

        result = apply_byok_rerank_boost(chunks, boost=2.0)

        assert len(result) == 3

        # Chunks with None scores should be treated as negative infinity for sorting
        # but actual score calculation should handle None -> float("-inf") conversion
        byok_with_score = next(c for c in result if c.content == "BYOK with score")
        assert byok_with_score.score == 1.6  # 0.8 * 2.0

    def test_preserves_chunk_attributes(self) -> None:
        """Test that chunk attributes are preserved during boosting."""
        chunks = [
            RAGChunk(
                content="Test content",
                source="byok_store",
                score=0.8,
                attributes={"title": "Test Doc", "url": "http://example.com"},
            )
        ]

        result = apply_byok_rerank_boost(chunks, boost=1.5)

        assert len(result) == 1
        assert result[0].content == "Test content"
        assert result[0].source == "byok_store"
        assert abs(result[0].score - 1.2) < 1e-10  # 0.8 * 1.5
        assert result[0].attributes == {
            "title": "Test Doc",
            "url": "http://example.com",
        }
