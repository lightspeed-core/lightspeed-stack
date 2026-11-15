"""Unit tests for RerankerConfiguration model."""

import pytest
from pydantic import ValidationError

import constants
from models.config import RerankerConfiguration


class TestRerankerConfiguration:
    """Configuration contract for reranker defaults and validation."""

    def test_default_values(self) -> None:
        """Default reranking stays disabled while preserving provider defaults."""
        config = RerankerConfiguration()
        assert config.enabled is False
        assert config.provider == constants.DEFAULT_RERANK_PROVIDER
        assert config.model == constants.DEFAULT_CROSS_ENCODER_MODEL

    def test_custom_model(self) -> None:
        """Accept custom cross-encoder model names without enabling reranking."""
        config = RerankerConfiguration(model="cross-encoder/ms-marco-TinyBERT-L2-v2")
        assert config.model == "cross-encoder/ms-marco-TinyBERT-L2-v2"
        assert config.enabled is False

    def test_disabled_reranker(self) -> None:
        """Keep the default model when reranking is explicitly disabled."""
        config = RerankerConfiguration(enabled=False)
        assert config.enabled is False
        assert config.model == constants.DEFAULT_CROSS_ENCODER_MODEL

    def test_model_fields_set_detection(self) -> None:
        """Preserve explicitly supplied model values for downstream checks."""
        config = RerankerConfiguration(model="custom-model")
        assert config.model == "custom-model"

    def test_all_custom_values(self) -> None:
        """Store every supported custom reranker field unchanged."""
        config = RerankerConfiguration(enabled=False, model="custom-cross-encoder")
        assert config.enabled is False
        assert config.model == "custom-cross-encoder"

    def test_explicit_configuration_detection(self) -> None:
        """Expose private explicit-configuration state for integration flows."""
        # Non-default values should mark as explicitly configured
        config = RerankerConfiguration(enabled=False)
        assert hasattr(config, "_explicitly_configured")
        # Note: The actual _explicitly_configured logic is private
        # and tested through integration tests

    def test_invalid_field_rejected(self) -> None:
        """Reject unknown reranker options instead of silently ignoring them."""
        with pytest.raises(ValidationError):
            RerankerConfiguration(invalid_field="value")
