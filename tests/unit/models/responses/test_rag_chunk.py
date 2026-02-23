"""Unit tests for RAGChunk and RAGContext models."""

from utils.types import RAGChunk, RAGContext
from models.responses import ReferencedDocument


class TestRAGChunk:
    """Test cases for the RAGChunk model."""

    def test_constructor_with_content_only(self) -> None:
        """Test RAGChunk constructor with content only."""
        chunk = RAGChunk(content="Sample content")  # pyright: ignore[reportCallIssue]
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

    def test_attributes_field(self) -> None:
        """Test RAGChunk with attributes field."""
        attributes = {
            "doc_url": "https://example.com/doc",
            "title": "Example Document",
            "author": "John Doe",
        }
        chunk = RAGChunk(
            content="Test content", source="test-source", attributes=attributes
        )
        assert chunk.attributes == attributes
        assert chunk.attributes["doc_url"] == "https://example.com/doc"

    def test_attributes_none(self) -> None:
        """Test RAGChunk with attributes=None."""
        chunk = RAGChunk(content="Test content", attributes=None)
        assert chunk.attributes is None


class TestRAGContext:
    """Test cases for the RAGContext model."""

    def test_default_values(self) -> None:
        """Test RAGContext with default values."""
        context = RAGContext()
        assert context.context_text == ""
        assert context.rag_chunks == []
        assert context.referenced_documents == []

    def test_with_context_text(self) -> None:
        """Test RAGContext with context text."""
        context = RAGContext(context_text="Test context")
        assert context.context_text == "Test context"
        assert context.rag_chunks == []
        assert context.referenced_documents == []

    def test_with_rag_chunks(self) -> None:
        """Test RAGContext with RAG chunks."""
        chunks = [
            RAGChunk(content="Chunk 1", source="source1", score=0.9),
            RAGChunk(content="Chunk 2", source="source2", score=0.8),
        ]
        context = RAGContext(rag_chunks=chunks)
        assert len(context.rag_chunks) == 2
        assert context.rag_chunks[0].content == "Chunk 1"
        assert context.rag_chunks[1].content == "Chunk 2"

    def test_with_referenced_documents(self) -> None:
        """Test RAGContext with referenced documents."""
        docs = [
            ReferencedDocument(
                doc_title="Doc 1",
                doc_url="https://example.com/doc1",
                source="source1",
            ),
            ReferencedDocument(
                doc_title="Doc 2",
                doc_url="https://example.com/doc2",
                source="source2",
            ),
        ]
        context = RAGContext(referenced_documents=docs)
        assert len(context.referenced_documents) == 2
        assert context.referenced_documents[0].doc_title == "Doc 1"
        assert context.referenced_documents[1].doc_title == "Doc 2"

    def test_fully_populated(self) -> None:
        """Test RAGContext with all fields populated."""
        chunks = [RAGChunk(content="Test chunk", source="source1", score=0.95)]
        docs = [
            ReferencedDocument(doc_title="Test Doc", doc_url="https://example.com/doc")
        ]
        context = RAGContext(
            context_text="Formatted context",
            rag_chunks=chunks,
            referenced_documents=docs,
        )
        assert context.context_text == "Formatted context"
        assert len(context.rag_chunks) == 1
        assert len(context.referenced_documents) == 1
