"""Unit tests for RAG, OKP, retrieval, and BYOK configuration models."""

# pylint: disable=no-member
# Pydantic Field(default_factory=...) pattern confuses pylint's static analysis

import warnings

import pytest
from pydantic import ValidationError

import constants
from models.config import (
    ByokConfiguration,
    ByokRag,
    OkpConfiguration,
    RagConfiguration,
    RetrievalConfiguration,
    RetrievalInlineConfiguration,
    RetrievalToolConfiguration,
)


class TestRetrievalInlineConfiguration:
    """Tests for RetrievalInlineConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RetrievalInlineConfiguration has correct default values."""
        config = RetrievalInlineConfiguration()
        assert config.sources == []
        assert config.max_chunks == constants.INLINE_RAG_MAX_CHUNKS

    def test_custom_sources(self) -> None:
        """Test inline sources with custom IDs."""
        config = RetrievalInlineConfiguration(sources=["store-1", "store-2"])
        assert config.sources == ["store-1", "store-2"]

    def test_custom_max_chunks(self) -> None:
        """Test custom max_chunks value."""
        config = RetrievalInlineConfiguration(max_chunks=20)
        assert config.max_chunks == 20

    def test_max_chunks_must_be_positive(self) -> None:
        """Test that max_chunks must be a positive integer."""
        with pytest.raises(ValidationError, match="greater than 0"):
            RetrievalInlineConfiguration(max_chunks=0)

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RetrievalInlineConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RetrievalInlineConfiguration(unknown_field="value")  # type: ignore[call-arg]


class TestRetrievalToolConfiguration:
    """Tests for RetrievalToolConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RetrievalToolConfiguration has correct default values."""
        config = RetrievalToolConfiguration()
        assert config.sources == []
        assert config.max_chunks == constants.TOOL_RAG_MAX_CHUNKS

    def test_custom_sources(self) -> None:
        """Test tool sources with custom IDs."""
        config = RetrievalToolConfiguration(sources=[constants.OKP_RAG_ID, "store-1"])
        assert config.sources == [constants.OKP_RAG_ID, "store-1"]

    def test_custom_max_chunks(self) -> None:
        """Test custom max_chunks value."""
        config = RetrievalToolConfiguration(max_chunks=15)
        assert config.max_chunks == 15

    def test_max_chunks_must_be_positive(self) -> None:
        """Test that max_chunks must be a positive integer."""
        with pytest.raises(ValidationError, match="greater than 0"):
            RetrievalToolConfiguration(max_chunks=0)

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RetrievalToolConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RetrievalToolConfiguration(unknown_field="value")  # type: ignore[call-arg]


class TestRetrievalConfiguration:
    """Tests for RetrievalConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RetrievalConfiguration has correct default values."""
        config = RetrievalConfiguration()
        assert config.inline.sources == []
        assert config.inline.max_chunks == constants.INLINE_RAG_MAX_CHUNKS
        assert config.tool.sources == []
        assert config.tool.max_chunks == constants.TOOL_RAG_MAX_CHUNKS

    def test_custom_inline_and_tool(self) -> None:
        """Test RetrievalConfiguration with custom inline and tool settings."""
        config = RetrievalConfiguration(
            inline=RetrievalInlineConfiguration(sources=["store-1"], max_chunks=20),
            tool=RetrievalToolConfiguration(sources=["store-2"], max_chunks=15),
        )
        assert config.inline.sources == ["store-1"]
        assert config.inline.max_chunks == 20
        assert config.tool.sources == ["store-2"]
        assert config.tool.max_chunks == 15

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RetrievalConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RetrievalConfiguration(unknown_field="value")  # type: ignore[call-arg]


class TestByokConfiguration:
    """Tests for ByokConfiguration model."""

    def test_default_values(self) -> None:
        """Test that ByokConfiguration has correct default values."""
        config = ByokConfiguration()
        assert config.max_chunks == constants.BYOK_RAG_MAX_CHUNKS
        assert config.stores == []

    def test_custom_max_chunks(self) -> None:
        """Test custom max_chunks value."""
        config = ByokConfiguration(max_chunks=20)
        assert config.max_chunks == 20

    def test_max_chunks_must_be_positive(self) -> None:
        """Test that max_chunks must be a positive integer."""
        with pytest.raises(ValidationError, match="greater than 0"):
            ByokConfiguration(max_chunks=0)

    def test_with_stores(self) -> None:
        """Test ByokConfiguration with BYOK stores."""
        store = ByokRag(
            rag_id="test-store",
            backend="faiss",
            vector_db_id="vs_123",
            db_path="/tmp/test.faiss",
        )
        config = ByokConfiguration(stores=[store])
        assert len(config.stores) == 1
        assert config.stores[0].rag_id == "test-store"

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that ByokConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ByokConfiguration(unknown_field="value")  # type: ignore[call-arg]


class TestRagConfiguration:
    """Tests for RagConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RagConfiguration has correct default values."""
        config = RagConfiguration()
        assert config.byok.stores == []
        assert config.byok.max_chunks == constants.BYOK_RAG_MAX_CHUNKS
        assert config.okp.offline is True
        assert config.okp.max_chunks == constants.OKP_RAG_MAX_CHUNKS
        assert config.retrieval.inline.sources == []
        assert config.retrieval.inline.max_chunks == constants.INLINE_RAG_MAX_CHUNKS
        assert config.retrieval.tool.sources == []
        assert config.retrieval.tool.max_chunks == constants.TOOL_RAG_MAX_CHUNKS

    def test_deprecated_inline_field_migrated(self) -> None:
        """Test that deprecated 'inline' field is migrated to retrieval.inline.sources."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = RagConfiguration(inline=["store-1", "store-2"])
            assert config.retrieval.inline.sources == ["store-1", "store-2"]
            assert config.inline is None
            assert len(w) == 1
            assert "deprecated" in str(w[0].message).lower()

    def test_deprecated_tool_field_migrated(self) -> None:
        """Test that deprecated 'tool' field is migrated to retrieval.tool.sources."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = RagConfiguration(tool=[constants.OKP_RAG_ID, "store-1"])
            assert config.retrieval.tool.sources == [constants.OKP_RAG_ID, "store-1"]
            assert config.tool is None
            assert len(w) == 1
            assert "deprecated" in str(w[0].message).lower()

    def test_deprecated_inline_and_tool_both_migrated(self) -> None:
        """Test that both deprecated fields are migrated together."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = RagConfiguration(
                inline=["store-1"],
                tool=[constants.OKP_RAG_ID],
            )
            assert config.retrieval.inline.sources == ["store-1"]
            assert config.retrieval.tool.sources == [constants.OKP_RAG_ID]
            assert len(w) == 2

    def test_new_format_retrieval(self) -> None:
        """Test RagConfiguration with new retrieval format."""
        config = RagConfiguration(
            retrieval=RetrievalConfiguration(
                inline=RetrievalInlineConfiguration(
                    sources=["store-1", constants.OKP_RAG_ID],
                    max_chunks=20,
                ),
                tool=RetrievalToolConfiguration(
                    sources=["store-1"],
                    max_chunks=15,
                ),
            ),
        )
        assert config.retrieval.inline.sources == ["store-1", constants.OKP_RAG_ID]
        assert config.retrieval.inline.max_chunks == 20
        assert config.retrieval.tool.sources == ["store-1"]
        assert config.retrieval.tool.max_chunks == 15

    def test_new_format_byok(self) -> None:
        """Test RagConfiguration with new byok format."""
        store = ByokRag(
            rag_id="ocp-docs",
            backend="faiss",
            vector_db_id="vs_123",
            db_path="/tmp/ocp.faiss",
        )
        config = RagConfiguration(
            byok=ByokConfiguration(max_chunks=15, stores=[store]),
        )
        assert config.byok.max_chunks == 15
        assert len(config.byok.stores) == 1
        assert config.byok.stores[0].rag_id == "ocp-docs"

    def test_new_format_okp(self) -> None:
        """Test RagConfiguration with new okp format."""
        config = RagConfiguration(
            okp=OkpConfiguration(
                offline=False,
                chunk_filter_query="product:*openshift*",
                max_chunks=8,
            ),
        )
        assert config.okp.offline is False
        assert config.okp.chunk_filter_query == "product:*openshift*"
        assert config.okp.max_chunks == 8

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RagConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RagConfiguration(unknown_field="value")  # type: ignore[call-arg]

    def test_fully_custom_config(self) -> None:
        """Test RagConfiguration with all sections set."""
        store = ByokRag(
            rag_id="kb",
            backend="faiss",
            vector_db_id="vs_456",
            db_path="/tmp/kb.faiss",
        )
        config = RagConfiguration(
            byok=ByokConfiguration(max_chunks=12, stores=[store]),
            okp=OkpConfiguration(offline=True, max_chunks=7),
            retrieval=RetrievalConfiguration(
                inline=RetrievalInlineConfiguration(
                    sources=[constants.OKP_RAG_ID, "kb"],
                    max_chunks=15,
                ),
                tool=RetrievalToolConfiguration(
                    sources=["kb"],
                    max_chunks=8,
                ),
            ),
        )
        assert config.byok.max_chunks == 12
        assert len(config.byok.stores) == 1
        assert config.okp.max_chunks == 7
        assert config.retrieval.inline.max_chunks == 15
        assert config.retrieval.tool.max_chunks == 8


class TestOkpConfiguration:
    """Tests for OkpConfiguration model."""

    def test_default_values(self) -> None:
        """Test that OkpConfiguration has correct default values."""
        config = OkpConfiguration()
        assert config.offline is True
        assert config.chunk_filter_query is None
        assert config.max_chunks == constants.OKP_RAG_MAX_CHUNKS

    def test_offline_false(self) -> None:
        """Test offline can be set to False (online mode)."""
        config = OkpConfiguration(offline=False)
        assert config.offline is False

    def test_custom_chunk_filter_query(self) -> None:
        """Test that chunk_filter_query can be customised."""
        config = OkpConfiguration(chunk_filter_query="product:*openshift*")
        assert config.chunk_filter_query == "product:*openshift*"

    def test_custom_max_chunks(self) -> None:
        """Test that max_chunks can be customised."""
        config = OkpConfiguration(max_chunks=8)
        assert config.max_chunks == 8

    def test_max_chunks_must_be_positive(self) -> None:
        """Test that max_chunks must be a positive integer."""
        with pytest.raises(ValidationError, match="greater than 0"):
            OkpConfiguration(max_chunks=0)

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that OkpConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            OkpConfiguration(unknown_field="value")  # type: ignore[call-arg]
