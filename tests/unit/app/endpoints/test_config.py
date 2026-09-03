"""Unit tests for the /config REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode
from pytest_mock import MockerFixture

from app.endpoints.config import config_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_config_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the config endpoint handler when configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.config.configuration", mock_config)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as exc_info:
        await config_endpoint_handler(
            auth=auth,
            request=request,  # pyright:ignore[reportArgumentType]
        )
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Configuration is not loaded"  # type: ignore[index]
    assert detail["cause"] == (  # type: ignore[index]
        "Lightspeed Stack configuration has not been initialized."
    )


@pytest.mark.asyncio
async def test_config_endpoint_handler_configuration_loaded(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """Test the config endpoint handler when configuration is loaded."""
    mock_authorization_resolvers(mocker)

    mocker.patch("app.endpoints.config.configuration", minimal_config)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await config_endpoint_handler(
        auth=auth,
        request=request,  # pyright:ignore[reportArgumentType]
    )
    assert response is not None
    assert response.configuration == minimal_config.configuration


class TestConfigEndpointOtel:
    """OTEL instrumentation tests for the /config endpoint."""

    @pytest.mark.asyncio
    async def test_emits_span_on_success(
        self,
        mocker: MockerFixture,
        minimal_config: AppConfig,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that a successful /config request emits a span."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.config.tracer", tracer)
        mock_authorization_resolvers(mocker)
        mocker.patch("app.endpoints.config.configuration", minimal_config)

        request = Request(scope={"type": "http"})
        auth: AuthTuple = ("uid", "uname", True, "tok")

        await config_endpoint_handler(
            auth=auth, request=request  # pyright:ignore[reportArgumentType]
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "config.handle_request"

    @pytest.mark.asyncio
    async def test_span_records_error_when_config_not_loaded(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that the span records an error when configuration is not loaded."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.config.tracer", tracer)
        mock_authorization_resolvers(mocker)

        mock_config = AppConfig()
        mock_config._configuration = None  # pylint: disable=protected-access
        mocker.patch("app.endpoints.config.configuration", mock_config)

        request = Request(scope={"type": "http"})
        auth: AuthTuple = ("uid", "uname", True, "tok")

        with pytest.raises(HTTPException):
            await config_endpoint_handler(
                auth=auth, request=request  # pyright:ignore[reportArgumentType]
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "config.handle_request"
        assert span.status.status_code == StatusCode.ERROR
