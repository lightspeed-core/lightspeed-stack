"""Fixtures for inference registry startup integration tests."""

from collections.abc import Generator

import pytest

from providers.inference.registry import ProviderRegistry
from utils.types import Singleton


@pytest.fixture(autouse=True)
def _reset_provider_registry() -> Generator[None, None, None]:
    """Reset the singleton registry between integration tests."""
    # pylint: disable=protected-access
    Singleton._instances.pop(ProviderRegistry, None)

    yield

    Singleton._instances.pop(ProviderRegistry, None)
    # pylint: enable=protected-access
