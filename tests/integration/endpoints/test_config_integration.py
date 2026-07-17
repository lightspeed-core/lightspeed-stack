"""Integration tests for the /config endpoint."""

from typing import cast

import pytest
from fastapi import HTTPException, Request, status

from lightspeed_stack.app.endpoints.config import config_endpoint_handler
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig


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
    current_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that observability config collects OTEL_* environment variables.

    This integration test verifies the full endpoint integration:
    - OTEL_* environment variables are collected into observability.otel
    - Configuration reload picks up new environment variables
    - Endpoint response includes the updated observability configuration

    Parameters:
    ----------
        current_config (AppConfig): Loads root configuration
        test_request (Request): FastAPI request
        test_auth (AuthTuple): noop authentication tuple
        monkeypatch (pytest.MonkeyPatch): Fixture to modify environment variables
    """
    # pylint: disable=import-outside-toplevel
    from pathlib import Path

    # Set OTEL environment variables
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Reload configuration to pick up new env vars
    # The observability field is populated via from_environment() during config load
    config_path = Path(__file__).parent.parent.parent.parent / "lightspeed-stack.yaml"
    current_config.load_configuration(str(config_path))

    # Call the actual endpoint handler to test full integration
    response = await config_endpoint_handler(auth=test_auth, request=test_request)

    # Verify that the endpoint response includes observability configuration
    assert hasattr(response.configuration, "observability")
    assert response.configuration.observability is not None
    assert hasattr(response.configuration.observability, "otel")

    # Verify OTEL vars are present in the endpoint response
    otel_config = response.configuration.observability.otel
    assert "OTEL_SDK_DISABLED" in otel_config
    assert otel_config["OTEL_SDK_DISABLED"] == "true"
    assert "OTEL_SERVICE_NAME" in otel_config
    assert otel_config["OTEL_SERVICE_NAME"] == "test-service"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in otel_config
    assert otel_config["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4317"
