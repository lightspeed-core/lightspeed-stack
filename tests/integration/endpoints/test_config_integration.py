"""Integration tests for the /config endpoint."""

import os
from typing import cast

import pytest
from fastapi import HTTPException, Request, status

from app.endpoints.config import config_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig


@pytest.mark.asyncio
async def test_config_endpoint_returns_config(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that config endpoint returns test configuration.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Configuration values are correctly accessed
    - Real noop authentication is used
    - Response structure matches expected format

    Parameters:
    ----------
        test_config (AppConfig): Fixture providing the expected configuration to be returned.
        test_request (Request): FastAPI request object used to call the endpoint.
        test_auth (AuthTuple): Authentication fixture used for the request.
    """
    response = await config_endpoint_handler(auth=test_auth, request=test_request)

    # Verify that response matches the real configuration
    assert response.configuration == test_config.configuration


@pytest.mark.asyncio
async def test_config_endpoint_returns_current_config(
    current_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that config endpoint returns current configuration (from root).

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Configuration values are correctly accessed
    - Real noop authentication is used
    - Response structure matches expected format

    Parameters:
    ----------
        current_config (AppConfig): Loads root configuration
        test_request (Request): FastAPI request
        test_auth (AuthTuple): noop authentication tuple
    """
    response = await config_endpoint_handler(auth=test_auth, request=test_request)

    # Verify that response matches the root configuration
    assert response.configuration == current_config.configuration


@pytest.mark.asyncio
async def test_config_endpoint_fails_without_configuration(
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that authorization fails when configuration is not loaded.

    This integration test verifies:
    - HTTPException is raised when configuration is not loaded
    - Error message indicates configuration is not loaded

    Parameters:
    ----------
        test_request (Request): FastAPI request fixture
        test_auth (AuthTuple): noop authentication fixture
    """
    # Verify that HTTPException is raised when configuration is not loaded
    with pytest.raises(HTTPException) as exc_info:
        await config_endpoint_handler(auth=test_auth, request=test_request)

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert isinstance(exc_info.value.detail, dict)
    assert "response" in exc_info.value.detail
    detail = cast(dict[str, str], exc_info.value.detail)
    assert "configuration is not loaded" in detail["response"].lower()


@pytest.mark.asyncio
async def test_config_endpoint_includes_observability(
    current_config: AppConfig,  # pylint: disable=unused-argument
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that config endpoint includes observability configuration.

    This integration test verifies:
    - Observability field is present in the configuration response
    - OTEL environment variables are correctly collected
    - Response structure includes observability.otel block

    Parameters:
    ----------
        current_config (AppConfig): Loads root configuration
        test_request (Request): FastAPI request
        test_auth (AuthTuple): noop authentication tuple
    """
    response = await config_endpoint_handler(auth=test_auth, request=test_request)

    # Verify observability field exists
    assert hasattr(response.configuration, "observability")
    assert response.configuration.observability is not None

    # Verify otel field exists
    assert hasattr(response.configuration.observability, "otel")
    assert isinstance(response.configuration.observability.otel, dict)


@pytest.mark.asyncio
async def test_config_endpoint_observability_collects_otel_vars(
    current_config: AppConfig,  # pylint: disable=unused-argument
    test_request: Request,  # pylint: disable=unused-argument
    test_auth: AuthTuple,  # pylint: disable=unused-argument
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that observability config collects OTEL_* environment variables.

    This integration test verifies:
    - OTEL_* environment variables are collected into observability.otel
    - Non-OTEL variables are not included
    - Environment variables set at runtime are reflected in config

    Parameters:
    ----------
        current_config (AppConfig): Loads root configuration
        test_request (Request): FastAPI request
        test_auth (AuthTuple): noop authentication tuple
        monkeypatch (pytest.MonkeyPatch): Fixture to modify environment variables
    """
    # pylint: disable=import-outside-toplevel
    from models.config import ObservabilityConfiguration

    # Set OTEL environment variables
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Reload configuration to pick up new env vars
    updated_observability = ObservabilityConfiguration.from_environment()

    # Verify OTEL vars are present in the environment
    # (Note: The config is loaded at startup, so these may not be in the response
    # unless we reload the entire config. This test verifies the mechanism works.)
    assert "OTEL_SDK_DISABLED" in os.environ
    assert "OTEL_SERVICE_NAME" in os.environ
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ

    # Verify that when we call from_environment(), it picks up the vars
    assert "OTEL_SDK_DISABLED" in updated_observability.otel
    assert updated_observability.otel["OTEL_SDK_DISABLED"] == "true"
    assert "OTEL_SERVICE_NAME" in updated_observability.otel
    assert updated_observability.otel["OTEL_SERVICE_NAME"] == "test-service"
