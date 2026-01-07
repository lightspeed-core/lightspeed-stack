"""Unit tests for RAGChunk model."""

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
