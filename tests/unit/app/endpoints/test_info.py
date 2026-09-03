"""Unit tests for the /info REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from ogx_client import ApiException
from ogx_client.models.version_info import VersionInfo
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode
from pytest_mock import MockerFixture

from app.endpoints.info import info_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_info_endpoint(mocker: MockerFixture) -> None:
    """Test the info endpoint handler."""
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[Any, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "ogx": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock the OGX client
    mock_client = mocker.AsyncMock()
    mock_client.inspect.version.return_value = VersionInfo(version="0.1.2")
    mock_lsc = mocker.patch("client.ogx.AsyncOgxClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    # Mock configuration
    mocker.patch("configuration.configuration", cfg)

    mock_authorization_resolvers(mocker)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await info_endpoint_handler(auth=auth, request=request)
    assert response is not None
    assert response.name is not None
    assert response.service_version is not None
    assert response.ogx_version == "0.1.2"


@pytest.mark.asyncio
async def test_info_endpoint_connection_error(mocker: MockerFixture) -> None:
    """Test the info endpoint handler.

    Verify that info_endpoint_handler raises an HTTPException with
    status 503 when the OGX client cannot connect.

    Sets up application configuration and patches the OGX
    client so that calling its version inspection raises an
    ApiException, then asserts the raised HTTPException has
    status code 503 and a detail payload containing a "response" of
    "Service unavailable" and a "cause" that includes "Unable to
    connect to OGX".
    """
    mock_authorization_resolvers(mocker)

    # configuration for tests
    config_dict: dict[Any, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "ogx": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
        },
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # Mock the OGX client
    mock_client = mocker.AsyncMock()
    mock_client.inspect.version.side_effect = ApiException(status=None)  # type: ignore
    mock_lsc = mocker.patch("client.ogx.AsyncOgxClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_config = mocker.Mock()
    mocker.patch("app.endpoints.models.configuration", mock_config)

    # Mock configuration
    mocker.patch("configuration.configuration", cfg)

    mock_authorization_resolvers(mocker)

    # HTTP request mock required by URL endpoint handler
    request = Request(
        scope={
            "type": "http",
        }
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await info_endpoint_handler(auth=auth, request=request)
        assert e.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert e.value.detail["response"] == "Service unavailable"  # type: ignore
        assert (
            "Connection error while trying to reach backend service."
            in e.value.detail["cause"]
        )  # type: ignore


class TestInfoEndpointOtel:
    """OTEL instrumentation tests for the /info endpoint."""

    @pytest.mark.asyncio
    async def test_emits_span_on_success(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that a successful /info request emits a span with service metadata."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.info.tracer", tracer)
        mock_authorization_resolvers(mocker)

        cfg = AppConfig()
        cfg.init_from_dict(
            {
                "name": "test-service",
                "service": {"host": "localhost", "port": 8080},
                "ogx": {
                    "api_key": "k",
                    "url": "http://x:1234",
                    "use_as_library_client": False,
                },
                "user_data_collection": {},
                "authorization": {"access_rules": []},
                "authentication": {"module": "noop"},
            }
        )
        mocker.patch("configuration.configuration", cfg)

        mock_client = mocker.AsyncMock()
        mock_client.inspect.version.return_value = VersionInfo(version="0.1.2")
        mocker.patch(
            "client.ogx.AsyncOgxClientHolder.get_client", return_value=mock_client
        )

        request = Request(scope={"type": "http"})
        auth: AuthTuple = ("uid", "uname", True, "tok")

        await info_endpoint_handler(auth=auth, request=request)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "info.handle_request"
        assert span.attributes is not None
        assert span.attributes["service.name"] == "test-service"
        assert span.attributes["service.version"] is not None

    @pytest.mark.asyncio
    async def test_span_records_error_on_connection_failure(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that the span records an error when OGX is unreachable."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.info.tracer", tracer)
        mock_authorization_resolvers(mocker)

        cfg = AppConfig()
        cfg.init_from_dict(
            {
                "name": "test-service",
                "service": {"host": "localhost", "port": 8080},
                "ogx": {
                    "api_key": "k",
                    "url": "http://x:1234",
                    "use_as_library_client": False,
                },
                "user_data_collection": {},
                "authorization": {"access_rules": []},
                "authentication": {"module": "noop"},
            }
        )
        mocker.patch("configuration.configuration", cfg)

        mock_client = mocker.AsyncMock()
        mock_client.inspect.version.side_effect = ApiException(status=None)
        mocker.patch(
            "client.ogx.AsyncOgxClientHolder.get_client", return_value=mock_client
        )

        request = Request(scope={"type": "http"})
        auth: AuthTuple = ("uid", "uname", True, "tok")

        with pytest.raises(HTTPException):
            await info_endpoint_handler(auth=auth, request=request)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "info.handle_request"
        assert span.status.status_code == StatusCode.ERROR
