"""Unit tests for RerankerConfiguration model."""

import pytest
from pydantic import ValidationError

from models.config import RerankerConfiguration


class TestRerankerConfiguration:
    """Tests for RerankerConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RerankerConfiguration has correct default values."""
        config = RerankerConfiguration()
        assert config.enabled is True
        assert config.model == "cross-encoder/ms-marco-MiniLM-L6-v2"
        assert config.top_k_multiplier == 2.0
        assert config.byok_boost == 1.2
        assert config.okp_boost == 1.0

    def test_custom_model(self) -> None:
        """Test configuration with custom cross-encoder model."""
        config = RerankerConfiguration(
            model="cross-encoder/ms-marco-TinyBERT-L2-v2"
        )
        assert config.model == "cross-encoder/ms-marco-TinyBERT-L2-v2"
        assert config.enabled is True

    def test_disabled_reranker(self) -> None:
        """Test configuration with reranker disabled."""
        config = RerankerConfiguration(enabled=False)
        assert config.enabled is False
        assert config.model == "cross-encoder/ms-marco-MiniLM-L6-v2"

    def test_custom_boost_factors(self) -> None:
        """Test configuration with custom boost factors."""
        config = RerankerConfiguration(
            byok_boost=1.5,
            okp_boost=0.8
        )
        assert config.byok_boost == 1.5
        assert config.okp_boost == 0.8

    def test_custom_top_k_multiplier(self) -> None:
        """Test configuration with custom top_k_multiplier."""
        config = RerankerConfiguration(top_k_multiplier=3.0)
        assert config.top_k_multiplier == 3.0

    def test_all_custom_values(self) -> None:
        """Test configuration with all custom values."""
        config = RerankerConfiguration(
            enabled=False,
            model="custom-cross-encoder",
            top_k_multiplier=1.5,
            byok_boost=2.0,
            okp_boost=0.5
        )
        assert config.enabled is False
        assert config.model == "custom-cross-encoder"
        assert config.top_k_multiplier == 1.5
        assert config.byok_boost == 2.0
        assert config.okp_boost == 0.5

    def test_explicit_configuration_detection(self) -> None:
        """Test that explicitly configured values are detected."""
        # Non-default values should mark as explicitly configured
        config = RerankerConfiguration(enabled=False)
        assert hasattr(config, "_explicitly_configured")
        # Note: The actual _explicitly_configured logic is private
        # and tested through integration tests

    def test_invalid_field_rejected(self) -> None:
        """Test that invalid fields are rejected due to extra='forbid'."""
        with pytest.raises(ValidationError):
            RerankerConfiguration(invalid_field="value")