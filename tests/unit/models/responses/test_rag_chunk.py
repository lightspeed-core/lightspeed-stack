"""Unit tests for RAGChunk and ReferencedDocument models."""

from pydantic import AnyUrl

from models.responses import ReferencedDocument
from utils.types import RAGChunk


class TestRAGChunk:
    """Test cases for the RAGChunk model."""

    def test_constructor_with_content_only(self) -> None:
        """Test RAGChunk constructor with content only."""
        chunk = RAGChunk(content="Sample content")
        assert chunk.content == "Sample content"
        assert chunk.source is None
        assert chunk.score is None

    def test_constructor_with_all_fields(self) -> None:
        """Test RAGChunk constructor with all fields.

        Verify that providing content, source, and score assigns those values
        to the RAGChunk instance.

        Asserts that the chunk's `content`, `source`, and `score` fields equal
        the values passed to the constructor.
        """
        chunk = RAGChunk(
            content="Kubernetes is an open-source container orchestration system",
            source="kubernetes-docs/overview.md",
            score=0.95,
        )
        assert (
            chunk.content
            == "Kubernetes is an open-source container orchestration system"
        )
        assert chunk.source == "kubernetes-docs/overview.md"
        assert chunk.score == 0.95

    def test_constructor_with_content_and_source(self) -> None:
        """Test RAGChunk constructor with content and source."""
        chunk = RAGChunk(
            content="Container orchestration automates deployment",
            source="docs/concepts.md",
        )
        assert chunk.content == "Container orchestration automates deployment"
        assert chunk.source == "docs/concepts.md"
        assert chunk.score is None

    def test_constructor_with_content_and_score(self) -> None:
        """Test RAGChunk constructor with content and score."""
        chunk = RAGChunk(content="Pod is the smallest deployable unit", score=0.82)
        assert chunk.content == "Pod is the smallest deployable unit"
        assert chunk.source is None
        assert chunk.score == 0.82

    def test_score_range_validation(self) -> None:
        """Test that RAGChunk accepts valid score ranges."""
        # Test minimum score
        chunk_min = RAGChunk(content="Test content", score=0.0)
        assert chunk_min.score == 0.0

        # Test maximum score
        chunk_max = RAGChunk(content="Test content", score=1.0)
        assert chunk_max.score == 1.0

        # Test decimal score
        chunk_decimal = RAGChunk(content="Test content", score=0.751)
        assert chunk_decimal.score == 0.751

    def test_empty_content(self) -> None:
        """Test RAGChunk with empty content."""
        chunk = RAGChunk(content="")
        assert chunk.content == ""
        assert chunk.source is None
        assert chunk.score is None

    def test_multiline_content(self) -> None:
        """Test RAGChunk with multiline content.

        Verify that a RAGChunk preserves multiline content and stores the
        provided source and score.

        Asserts that the chunk's `content` equals the original multiline
        string, `source` equals "docs/multiline.md", and `score` equals 0.88.
        """
        multiline_content = """This is a multiline content
        that spans multiple lines
        and contains various information."""

        chunk = RAGChunk(
            content=multiline_content, source="docs/multiline.md", score=0.88
        )
        assert chunk.content == multiline_content
        assert chunk.source == "docs/multiline.md"
        assert chunk.score == 0.88

    def test_long_source_path(self) -> None:
        """Test RAGChunk with long source path."""
        long_source = (
            "very/deep/nested/directory/structure/with/many/levels/document.md"
        )
        chunk = RAGChunk(
            content="Content from deeply nested document", source=long_source
        )
        assert chunk.source == long_source

    def test_url_as_source(self) -> None:
        """Test RAGChunk with URL as source."""
        url_source = "https://docs.example.com/api/v1/documentation"
        chunk = RAGChunk(
            content="API documentation content", source=url_source, score=0.92
        )
        assert chunk.source == url_source
        assert chunk.score == 0.92


class TestReferencedDocument:
    """Test cases for the ReferencedDocument model."""

    def test_referenced_document_with_full_metadata(self) -> None:
        """Test ReferencedDocument construction with all fields."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"),
            doc_title="Test Document",
            document_id="doc-123",
            product_name="Red Hat OpenShift",
            product_version="4.15",
            source_path="/docs/install.md",
            score=0.95,
            chunk_metadata={"author": "Red Hat", "custom": "value"},
        )

        assert doc.doc_url == AnyUrl("https://example.com/doc")
        assert doc.doc_title == "Test Document"
        assert doc.document_id == "doc-123"
        assert doc.product_name == "Red Hat OpenShift"
        assert doc.product_version == "4.15"
        assert doc.source_path == "/docs/install.md"
        assert doc.score == 0.95
        assert doc.chunk_metadata is not None
        assert doc.chunk_metadata["author"] == "Red Hat"
        assert doc.chunk_metadata["custom"] == "value"

    def test_referenced_document_minimal_fields(self) -> None:
        """Test ReferencedDocument with minimal fields (backward compatibility)."""
        doc = ReferencedDocument()

        assert doc.doc_url is None
        assert doc.doc_title is None
        assert doc.document_id is None
        assert doc.product_name is None
        assert doc.product_version is None
        assert doc.source_path is None
        assert doc.score is None
        assert doc.chunk_metadata is None

    def test_referenced_document_backward_compatible(self) -> None:
        """Test that existing code using only doc_url and doc_title still works."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"), doc_title="Test Document"
        )

        assert doc.doc_url == AnyUrl("https://example.com/doc")
        assert doc.doc_title == "Test Document"
        # New fields default to None
        assert doc.document_id is None
        assert doc.product_name is None
        assert doc.product_version is None
        assert doc.source_path is None
        assert doc.score is None
        assert doc.chunk_metadata is None

    def test_referenced_document_with_product_metadata_only(self) -> None:
        """Test ReferencedDocument with only product metadata fields."""
        doc = ReferencedDocument(
            product_name="Red Hat OpenStack", product_version="17.1"
        )

        assert doc.product_name == "Red Hat OpenStack"
        assert doc.product_version == "17.1"
        assert doc.doc_url is None
        assert doc.doc_title is None
        assert doc.document_id is None
        assert doc.source_path is None
        assert doc.score is None
        assert doc.chunk_metadata is None

    def test_referenced_document_with_score(self) -> None:
        """Test ReferencedDocument with relevance score."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"),
            doc_title="Scored Document",
            score=0.87,
        )

        assert doc.score == 0.87
        assert doc.doc_url == AnyUrl("https://example.com/doc")
        assert doc.doc_title == "Scored Document"

    def test_referenced_document_empty_chunk_metadata(self) -> None:
        """Test ReferencedDocument with empty chunk_metadata dict."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"),
            doc_title="Test Document",
            chunk_metadata={},
        )

        assert doc.chunk_metadata == {}
        assert doc.doc_url == AnyUrl("https://example.com/doc")

    def test_referenced_document_with_document_id_and_source_path(self) -> None:
        """Test ReferencedDocument with document_id and source_path."""
        doc = ReferencedDocument(
            document_id="doc-456",
            source_path="/local/path/to/document.md",
            doc_title="Local Document",
        )

        assert doc.document_id == "doc-456"
        assert doc.source_path == "/local/path/to/document.md"
        assert doc.doc_title == "Local Document"
        assert doc.doc_url is None
