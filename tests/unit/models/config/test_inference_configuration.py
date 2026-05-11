"""Unit tests for InferenceConfiguration model."""

import pytest

from models.config import InferenceConfiguration


def test_inference_constructor() -> None:
    """
    Test the InferenceConfiguration constructor with valid
    parameters.
    """
    # Test with no default provider or model, as they are optional
    inference_config = InferenceConfiguration()  # pyright: ignore[reportCallIssue]
    assert inference_config is not None
    assert inference_config.default_provider is None
    assert inference_config.default_model is None

    # Test with default provider and model
    inference_config = InferenceConfiguration(
        default_provider="default_provider",
        default_model="default_model",
    )
    assert inference_config is not None
    assert inference_config.default_provider == "default_provider"
    assert inference_config.default_model == "default_model"


def test_inference_default_model_missing() -> None:
    """
    Test case where only default provider is set, should fail
    """
    with pytest.raises(
        ValueError,
        match="Default model must be specified when default provider is set",
    ):
        InferenceConfiguration(
            default_provider="default_provider",
        )  # pyright: ignore[reportCallIssue]


def test_inference_default_provider_missing() -> None:
    """
    Test case where only default model is set, should fail.

    Checks that constructing InferenceConfiguration with only `default_model`
    set raises a ValueError.

    Asserts the error message equals "Default provider must be specified when
    default model is set".
    """
    with pytest.raises(
        ValueError,
        match="Default provider must be specified when default model is set",
    ):
        InferenceConfiguration(
            default_model="default_model",
        )  # pyright: ignore[reportCallIssue]


def test_context_windows_default_empty() -> None:
    """Test the context_windows field defaults to an empty dict."""
    inference_config = InferenceConfiguration()  # pyright: ignore[reportCallIssue]
    assert inference_config.context_windows == {}


def test_context_windows_accepts_model_to_size_map() -> None:
    """Test context_windows accepts a populated model-to-window map."""
    inference_config = InferenceConfiguration(
        context_windows={
            "openai/gpt-4o-mini": 128000,
            "openai/gpt-4o": 128000,
        },
    )  # pyright: ignore[reportCallIssue]
    assert inference_config.context_windows["openai/gpt-4o-mini"] == 128000
    assert inference_config.context_windows["openai/gpt-4o"] == 128000


def test_context_windows_rejects_non_positive_size() -> None:
    """Test that a non-positive window size is rejected by Pydantic."""
    with pytest.raises(ValueError):
        InferenceConfiguration(
            context_windows={"openai/gpt-4o-mini": 0},
        )  # pyright: ignore[reportCallIssue]


def test_context_windows_rejects_negative_size() -> None:
    """Test that a negative window size is rejected by Pydantic."""
    with pytest.raises(ValueError):
        InferenceConfiguration(
            context_windows={"openai/gpt-4o-mini": -1},
        )  # pyright: ignore[reportCallIssue]
