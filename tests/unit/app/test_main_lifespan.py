"""Unit tests for the startup sequence of the FastAPI application."""

from typing import Any

import pytest
from pytest_mock import MockerFixture, MockType

import constants
from app.main import app, lifespan
from cache.cache_error import CacheError


@pytest.fixture(name="configuration_mock")
def configuration_mock_fixture(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> MockType:
    """Replace everything the startup sequence talks to except the configuration.

    Returns:
        The mock that stands for the configuration singleton in `app.main`.

    """
    monkeypatch.setenv("LIGHTSPEED_STACK_CONFIG_PATH", "unused.yaml")
    for name in (
        "initialize_sentry",
        "initialize_pyroscope",
        "initialize_database",
        "create_tables",
        "sentry_sdk",
    ):
        mocker.patch(f"app.main.{name}")
    holder = mocker.patch("app.main.AsyncOgxClientHolder")
    holder.return_value.load = mocker.AsyncMock()
    for name in (
        "check_ogx_version",
        "setup_model_metrics",
        "shutdown_background_topic_summary_tasks",
        "A2AStorageFactory.cleanup",
    ):
        mocker.patch(f"app.main.{name}", new=mocker.AsyncMock())
    config = mocker.patch("app.main.configuration")
    config.configuration.azure_entra_id = None
    return config


def set_conversation_cache_type(
    mocker: MockerFixture, config: MockType, cache_type: str | None, **kwargs: Any
) -> MockType:
    """Configure the cache type and return the mock of the cache property."""
    config.conversation_cache_configuration.type = cache_type
    cache_property = mocker.PropertyMock(**kwargs)
    type(config).conversation_cache = cache_property
    return cache_property


async def test_startup_opens_sqlite_conversation_cache(
    mocker: MockerFixture, configuration_mock: MockType
) -> None:
    """Test that the SQLite conversation cache is opened during startup."""
    cache_property = set_conversation_cache_type(
        mocker, configuration_mock, constants.CACHE_TYPE_SQLITE
    )

    async with lifespan(app):
        cache_property.assert_called_once()


async def test_startup_fails_when_sqlite_conversation_cache_cannot_be_opened(
    mocker: MockerFixture, configuration_mock: MockType
) -> None:
    """Test that an unusable SQLite conversation cache stops the startup."""
    set_conversation_cache_type(
        mocker,
        configuration_mock,
        constants.CACHE_TYPE_SQLITE,
        side_effect=CacheError("Cannot create directory"),
    )

    with pytest.raises(CacheError, match="Cannot create directory"):
        async with lifespan(app):
            pass


@pytest.mark.parametrize(
    "cache_type",
    [
        None,
        constants.CACHE_TYPE_NOOP,
        constants.CACHE_TYPE_MEMORY,
        constants.CACHE_TYPE_POSTGRES,
    ],
)
async def test_startup_leaves_other_conversation_caches_closed(
    mocker: MockerFixture, configuration_mock: MockType, cache_type: str | None
) -> None:
    """Test that other cache types are still opened by their first request."""
    cache_property = set_conversation_cache_type(mocker, configuration_mock, cache_type)

    async with lifespan(app):
        cache_property.assert_not_called()
