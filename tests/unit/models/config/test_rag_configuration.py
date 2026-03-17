"""Unit tests for RAG and OKP configuration models."""

# pylint: disable=no-member
# Pydantic Field(default_factory=...) pattern confuses pylint's static analysis

import pytest
from pydantic import ValidationError

import constants
from models.config import OkpConfiguration, RagConfiguration


class TestRagConfiguration:
    """Tests for RagConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RagConfiguration has correct default values."""
        config = RagConfiguration()
        assert config.inline == []
        assert config.tool == []

    def test_inline_with_byok_ids(self) -> None:
        """Test inline list with BYOK rag IDs."""
        config = RagConfiguration(inline=["store-1", "store-2"])
        assert config.inline == ["store-1", "store-2"]
        assert config.tool == []

    def test_inline_with_okp_rag(self) -> None:
        """Test inline list including the special OKP ID."""
        config = RagConfiguration(inline=[constants.OKP_RAG_ID, "store-1"])
        assert constants.OKP_RAG_ID in config.inline
        assert "store-1" in config.inline

    def test_tool_with_okp_rag_and_byok(self) -> None:
        """Test tool list with OKP and BYOK IDs."""
        config = RagConfiguration(
            inline=["store-1"],
            tool=[constants.OKP_RAG_ID, "store-1"],
        )
        assert config.inline == ["store-1"]
        assert config.tool == [constants.OKP_RAG_ID, "store-1"]

    def test_tool_empty_list(self) -> None:
        """Test that an explicit empty tool list disables tool RAG."""
        config = RagConfiguration(tool=[])
        assert config.tool == []

    def test_tool_default_is_empty_list(self) -> None:
        """Test that tool defaults to an empty list."""
        config = RagConfiguration()
        assert config.tool == []

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that RagConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RagConfiguration(unknown_field="value")  # type: ignore[call-arg]

    def test_fully_custom_config(self) -> None:
        """Test RagConfiguration with all fields set."""
        config = RagConfiguration(
            inline=[constants.OKP_RAG_ID, "store-1"],
            tool=["store-1"],
        )
        assert constants.OKP_RAG_ID in config.inline
        assert "store-1" in config.inline
        assert config.tool == ["store-1"]


class TestOkpConfiguration:
    """Tests for OkpConfiguration model."""

    def test_default_values(self) -> None:
        """Test that OkpConfiguration has correct default values."""
        config = OkpConfiguration()
        assert config.offline is True
        assert config.chunk_filter_query is None

    def test_offline_false(self) -> None:
        """Test offline can be set to False (online mode)."""
        config = OkpConfiguration(offline=False)
        assert config.offline is False

    def test_custom_chunk_filter_query(self) -> None:
        """Test that chunk_filter_query can be customised."""
        config = OkpConfiguration(chunk_filter_query="product:*openshift*")
        assert config.chunk_filter_query == "product:*openshift*"

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that OkpConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            OkpConfiguration(unknown_field="value")  # type: ignore[call-arg]
