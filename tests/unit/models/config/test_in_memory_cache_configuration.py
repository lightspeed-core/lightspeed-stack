"""Unit tests for InMemoryCache model."""

import pytest
from pydantic import ValidationError

from lightspeed_stack.models.config import InMemoryCacheConfig


def test_in_memory_cache_configuration() -> None:
    """Test the in memory cache configuration."""
    c = InMemoryCacheConfig(max_entries=100)
    assert c is not None
    assert c.max_entries == 100


def test_in_memory_cache_incorrect_configuration_zero_max_entries() -> None:
    """Test the in memory cache incorrect configuration handling."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        InMemoryCacheConfig(max_entries=0)


def test_in_memory_cache_incorrect_configuration_negative_max_entries() -> None:
    """Test the in memory cache incorrect configuration handling."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        InMemoryCacheConfig(max_entries=-100)


def test_in_memory_cache_incorrect_configuration_no_max_entries() -> None:
    """Test the in memory cache incorrect configuration handling."""
    with pytest.raises(ValidationError, match="Field required"):
        InMemoryCacheConfig()  # pyright: ignore[reportCallIssue]
