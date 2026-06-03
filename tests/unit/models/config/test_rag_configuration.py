"""Unit tests for RAG and OKP configuration models."""

# pylint: disable=no-member
# Pydantic Field(default_factory=...) pattern confuses pylint's static analysis

import pytest
from pydantic import ValidationError

import constants
from models.config import (
    ByokConfiguration,
    OkpConfiguration,
    RagConfiguration,
    RagStore,
    RetrievalConfiguration,
    RetrievalStrategyConfiguration,
)


class TestRetrievalStrategyConfiguration:
    """Tests for RetrievalStrategyConfiguration model."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = RetrievalStrategyConfiguration()
        assert config.sources == []
        assert config.max_chunks == constants.DEFAULT_INLINE_RAG_MAX_CHUNKS

    def test_custom_values(self) -> None:
        """Test custom sources and max_chunks."""
        config = RetrievalStrategyConfiguration(
            sources=["store-1", "okp"], max_chunks=20
        )
        assert config.sources == ["store-1", "okp"]
        assert config.max_chunks == 20


class TestRetrievalConfiguration:
    """Tests for RetrievalConfiguration model."""

    def test_default_values(self) -> None:
        """Test default inline and tool strategies."""
        config = RetrievalConfiguration()
        assert config.inline.sources == []
        assert config.inline.max_chunks == constants.DEFAULT_INLINE_RAG_MAX_CHUNKS
        assert config.tool.sources == []
        assert config.tool.max_chunks == constants.DEFAULT_TOOL_RAG_MAX_CHUNKS

    def test_custom_values(self) -> None:
        """Test custom inline and tool strategies."""
        config = RetrievalConfiguration(
            inline=RetrievalStrategyConfiguration(
                sources=["store-1", "okp"], max_chunks=8
            ),
            tool=RetrievalStrategyConfiguration(sources=["store-1"], max_chunks=12),
        )
        assert config.inline.sources == ["store-1", "okp"]
        assert config.inline.max_chunks == 8
        assert config.tool.sources == ["store-1"]
        assert config.tool.max_chunks == 12


class TestByokConfiguration:
    """Tests for ByokConfiguration model."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = ByokConfiguration()
        assert config.stores == []
        assert config.max_chunks == constants.DEFAULT_BYOK_RAG_MAX_CHUNKS

    def test_with_stores(self) -> None:
        """Test with store entries."""
        store = RagStore(
            rag_id="test",
            vector_db_id="vs_123",
            db_path="/tmp/test.db",
        )
        config = ByokConfiguration(stores=[store], max_chunks=15)
        assert len(config.stores) == 1
        assert config.stores[0].rag_id == "test"
        assert config.max_chunks == 15


class TestRagConfiguration:
    """Tests for RagConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RagConfiguration has correct default values."""
        config = RagConfiguration()
        assert config.byok.stores == []
        assert config.byok.max_chunks == constants.DEFAULT_BYOK_RAG_MAX_CHUNKS
        assert config.okp.offline is True
        assert config.okp.max_chunks == constants.DEFAULT_OKP_RAG_MAX_CHUNKS
        assert config.retrieval.inline.sources == []
        assert config.retrieval.tool.sources == []

    def test_inline_with_byok_ids(self) -> None:
        """Test inline sources with BYOK rag IDs."""
        stores = [
            RagStore(rag_id="store-1", vector_db_id="vs_1", db_path="/tmp/s1.db"),
            RagStore(rag_id="store-2", vector_db_id="vs_2", db_path="/tmp/s2.db"),
        ]
        config = RagConfiguration(
            byok=ByokConfiguration(stores=stores),
            retrieval=RetrievalConfiguration(
                inline=RetrievalStrategyConfiguration(sources=["store-1", "store-2"]),
            ),
        )
        assert config.retrieval.inline.sources == ["store-1", "store-2"]
        assert config.retrieval.tool.sources == []

    def test_inline_with_okp_rag(self) -> None:
        """Test inline sources including the special OKP ID."""
        store = RagStore(rag_id="store-1", vector_db_id="vs_1", db_path="/tmp/s1.db")
        config = RagConfiguration(
            byok=ByokConfiguration(stores=[store]),
            retrieval=RetrievalConfiguration(
                inline=RetrievalStrategyConfiguration(
                    sources=[constants.OKP_RAG_ID, "store-1"]
                ),
            ),
        )
        assert constants.OKP_RAG_ID in config.retrieval.inline.sources
        assert "store-1" in config.retrieval.inline.sources

    def test_tool_with_okp_rag_and_byok(self) -> None:
        """Test tool sources with OKP and BYOK IDs."""
        store = RagStore(rag_id="store-1", vector_db_id="vs_1", db_path="/tmp/s1.db")
        config = RagConfiguration(
            byok=ByokConfiguration(stores=[store]),
            retrieval=RetrievalConfiguration(
                inline=RetrievalStrategyConfiguration(sources=["store-1"]),
                tool=RetrievalStrategyConfiguration(
                    sources=[constants.OKP_RAG_ID, "store-1"]
                ),
            ),
        )
        assert config.retrieval.inline.sources == ["store-1"]
        assert config.retrieval.tool.sources == [constants.OKP_RAG_ID, "store-1"]

    def test_tool_empty_list(self) -> None:
        """Test that an explicit empty tool sources list disables tool RAG."""
        config = RagConfiguration(
            retrieval=RetrievalConfiguration(
                tool=RetrievalStrategyConfiguration(sources=[]),
            ),
        )
        assert config.retrieval.tool.sources == []

    def test_tool_default_is_empty_list(self) -> None:
        """Test that tool sources defaults to an empty list."""
        config = RagConfiguration()
        assert config.retrieval.tool.sources == []

    def test_unknown_inline_source_rejected(self) -> None:
        """Test that inline sources referencing undeclared rag_ids are rejected."""
        store = RagStore(rag_id="store-1", vector_db_id="vs_1", db_path="/tmp/s1.db")
        with pytest.raises(ValidationError, match="unknown RAG IDs"):
            RagConfiguration(
                byok=ByokConfiguration(stores=[store]),
                retrieval=RetrievalConfiguration(
                    inline=RetrievalStrategyConfiguration(
                        sources=["store-1", "nonexistent"]
                    ),
                ),
            )

    def test_unknown_tool_source_rejected(self) -> None:
        """Test that tool sources referencing undeclared rag_ids are rejected."""
        with pytest.raises(ValidationError, match="unknown RAG IDs"):
            RagConfiguration(
                retrieval=RetrievalConfiguration(
                    tool=RetrievalStrategyConfiguration(sources=["missing-store"]),
                ),
            )

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RagConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RagConfiguration(unknown_field="value")  # type: ignore[call-arg]

    def test_fully_custom_config(self) -> None:
        """Test RagConfiguration with all fields set."""
        store = RagStore(
            rag_id="store-1",
            vector_db_id="vs_123",
            db_path="/tmp/test.db",
        )
        config = RagConfiguration(
            byok=ByokConfiguration(stores=[store], max_chunks=15),
            okp=OkpConfiguration(offline=False, max_chunks=3),
            retrieval=RetrievalConfiguration(
                inline=RetrievalStrategyConfiguration(
                    sources=[constants.OKP_RAG_ID, "store-1"], max_chunks=8
                ),
                tool=RetrievalStrategyConfiguration(sources=["store-1"], max_chunks=12),
            ),
        )
        assert constants.OKP_RAG_ID in config.retrieval.inline.sources
        assert "store-1" in config.retrieval.inline.sources
        assert config.retrieval.tool.sources == ["store-1"]
        assert config.byok.max_chunks == 15
        assert config.okp.max_chunks == 3
        assert config.retrieval.inline.max_chunks == 8
        assert config.retrieval.tool.max_chunks == 12


class TestOkpConfiguration:
    """Tests for OkpConfiguration model."""

    def test_default_values(self) -> None:
        """Test that OkpConfiguration has correct default values."""
        config = OkpConfiguration()
        assert config.offline is True
        assert config.chunk_filter_query is None
        assert config.max_chunks == constants.DEFAULT_OKP_RAG_MAX_CHUNKS

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
        config = OkpConfiguration(max_chunks=3)
        assert config.max_chunks == 3

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that OkpConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            OkpConfiguration(unknown_field="value")  # type: ignore[call-arg]
