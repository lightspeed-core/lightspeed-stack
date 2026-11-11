"""Unit tests for FastAPI lifespan wiring of the inference provider registry."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI
from openai import APIConnectionError
from pytest_mock import MockerFixture

import app.main
from app.main import lifespan
from providers.inference.errors import ModelDiscoveryError
from providers.inference.registry import ProviderRegistry
from utils.types import Singleton


@pytest.fixture(autouse=True)
def _reset_provider_registry() -> Generator[None, None, None]:
    """Reset the singleton registry between startup unit tests."""
    # pylint: disable=protected-access
    Singleton._instances.pop(ProviderRegistry, None)

    yield

    Singleton._instances.pop(ProviderRegistry, None)
    # pylint: enable=protected-access


def _write_config(tmp_path: Path, *, inference: dict[str, Any]) -> Path:
    """Write a minimal LCS config with the given inference section."""
    config_path = tmp_path / "lightspeed-stack.yaml"
    payload: dict[str, Any] = {
        "name": "lifespan-test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "ogx": {
            "use_as_library_client": False,
            "url": "http://localhost:8321",
            "api_key": "xyzzy",
            "allow_degraded_mode": True,
        },
        "user_data_collection": {"feedback_enabled": False},
        "mcp_servers": [],
        "inference": inference,
    }
    config_path.write_text(yaml.dump(payload), encoding="utf-8")
    return config_path


def _openai_provider_entry(*, skip_model_discovery: bool) -> dict[str, Any]:
    """Build an OpenAI inference.providers[] entry for lifespan configs."""
    return {
        "type": "openai",
        "id": "openai",
        "skip_model_discovery": skip_model_discovery,
        "allowed_models": [
            {
                "name": "chat",
                "provider_model_id": "gpt-4o-mini",
                "model_type": "llm",
            }
        ],
        "config": {
            "api_key": "test-key",
            "base_url": "https://example.test/v1",
        },
    }


def _patch_lifespan_foreign_dependencies(mocker: MockerFixture) -> None:
    """Mock foreign startup dependencies outside the inference registry."""
    mocker.patch("app.main.initialize_sentry")
    mocker.patch("app.main.initialize_pyroscope")
    mock_holder = mocker.patch("app.main.AsyncOgxClientHolder")
    mock_holder_instance = mock_holder.return_value
    mock_holder_instance.load = mocker.AsyncMock()
    mock_holder_instance.get_client.return_value = mocker.AsyncMock()
    mocker.patch(
        "app.main.check_ogx_version",
        new=mocker.AsyncMock(return_value="0.2.22"),
    )
    mocker.patch("app.main.setup_model_metrics", new=mocker.AsyncMock())
    mocker.patch("app.main.initialize_database")
    mocker.patch("app.main.create_tables")
    mocker.patch("app.main.get_engine")
    mocker.patch(
        "app.main.shutdown_background_topic_summary_tasks",
        new=mocker.AsyncMock(),
    )
    mocker.patch("app.main.A2AStorageFactory.cleanup", new=mocker.AsyncMock())
    mocker.patch("app.main.sentry_sdk.flush")


@pytest.mark.asyncio
async def test_lifespan_initializes_inference_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Successful startup initializes the registry from inference.providers[]."""
    monkeypatch.setenv(
        "LIGHTSPEED_STACK_CONFIG_PATH",
        str(
            _write_config(
                tmp_path,
                inference={
                    "providers": [
                        _openai_provider_entry(skip_model_discovery=True),
                    ]
                },
            )
        ),
    )
    _patch_lifespan_foreign_dependencies(mocker)

    async with lifespan(FastAPI()):
        registry = ProviderRegistry()
        assert [provider.provider_id for provider in registry.list_providers()] == [
            "openai"
        ]
        assert [model.name for model in registry.list_models()] == ["chat"]


@pytest.mark.asyncio
async def test_lifespan_propagates_model_discovery_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """OpenAI models.list failure becomes ModelDiscoveryError and aborts startup."""
    monkeypatch.setenv(
        "LIGHTSPEED_STACK_CONFIG_PATH",
        str(
            _write_config(
                tmp_path,
                inference={
                    "providers": [
                        _openai_provider_entry(skip_model_discovery=False),
                    ]
                },
            )
        ),
    )
    _patch_lifespan_foreign_dependencies(mocker)
    mocker.patch(
        "openai.resources.models.AsyncModels.list",
        new=mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="connection failed",
                request=httpx.Request(  # pyright: ignore[reportArgumentType]
                    "GET", "https://example.test/v1/models"
                ),
            )
        ),
    )

    with pytest.raises(ModelDiscoveryError) as exc_info:
        async with lifespan(FastAPI()):
            pass

    assert exc_info.value.provider_id == "openai"
    assert ProviderRegistry().list_providers() == []


@pytest.mark.asyncio
async def test_lifespan_runs_startup_schema_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Startup runs schema migrations on the initialized database engine."""
    monkeypatch.setenv(
        "LIGHTSPEED_STACK_CONFIG_PATH",
        str(_write_config(tmp_path, inference={"providers": []})),
    )
    _patch_lifespan_foreign_dependencies(mocker)
    mock_run_migrations = mocker.patch("app.main.run_startup_migrations")

    async with lifespan(FastAPI()):
        pass

    mock_run_migrations.assert_called_once_with(app.main.get_engine.return_value)
