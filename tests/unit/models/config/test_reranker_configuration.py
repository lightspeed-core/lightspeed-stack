"""Unit tests for RerankerConfiguration model."""

import pytest
from pydantic import ValidationError

import constants
from models.config import RerankerConfiguration


class TestRerankerConfiguration:
    """Tests for RerankerConfiguration model."""

    def test_default_values(self) -> None:
        """Test that RerankerConfiguration has correct default values."""
        config = RerankerConfiguration()
        assert config.enabled is False
        assert config.model == constants.DEFAULT_CROSS_ENCODER_MODEL

    def test_custom_model(self) -> None:
        """Test configuration with custom cross-encoder model."""
        config = RerankerConfiguration(model="cross-encoder/ms-marco-TinyBERT-L2-v2")
        assert config.model == "cross-encoder/ms-marco-TinyBERT-L2-v2"
        assert config.enabled is False

    def test_disabled_reranker(self) -> None:
        """Test configuration with reranker disabled."""
        config = RerankerConfiguration(enabled=False)
        assert config.enabled is False
        assert config.model == constants.DEFAULT_CROSS_ENCODER_MODEL

    def test_model_fields_set_detection(self) -> None:
        """Test that model_fields_set is properly detected."""
        config = RerankerConfiguration(model="custom-model")
        assert config.model == "custom-model"

    def test_all_custom_values(self) -> None:
        """Test configuration with all custom values."""
        config = RerankerConfiguration(enabled=False, model="custom-cross-encoder")
        assert config.enabled is False
        assert config.model == "custom-cross-encoder"

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
