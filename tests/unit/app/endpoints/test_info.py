"""Unit tests for the /info REST API endpoint."""

from typing import TYPE_CHECKING, Any

import pytest
from fastapi import Request
from ogx_client import ApiException
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.info import info_endpoint_handler
from configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from version import __version__

if TYPE_CHECKING:
    from authentication.interface import AuthTuple


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

    # The handler must not touch the OGX client
    mock_lsc = mocker.patch("client.ogx.AsyncOgxClientHolder.get_client")
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
    assert response.model_dump() == {"name": "foo", "service_version": __version__}
    mock_lsc.assert_not_called()


@pytest.mark.asyncio
async def test_info_endpoint_does_not_depend_on_ogx(mocker: MockerFixture) -> None:
    """Test that the info endpoint answers while OGX is unreachable.

    Makes any use of the OGX client fail and asserts the handler still
    returns the service identity, because /info does not need OGX.
    """
    mock_authorization_resolvers(mocker)

    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "foo",
            "service": {"host": "localhost", "port": 8080},
            "ogx": {
                "api_key": "xyzzy",
                "url": "http://x.y.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {"feedback_enabled": False},
            "authorization": {"access_rules": []},
            "authentication": {"module": "noop"},
        }
    )
    mocker.patch("configuration.configuration", cfg)

    # Any attempt to reach OGX fails
    mocker.patch(
        "client.ogx.AsyncOgxClientHolder.get_client",
        side_effect=ApiException(status=None),  # type: ignore
    )

    # HTTP request mock required by URL endpoint handler
    request = Request(scope={"type": "http"})

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await info_endpoint_handler(auth=auth, request=request)
    assert response.model_dump() == {"name": "foo", "service_version": __version__}


@pytest.mark.asyncio
async def test_info_endpoint_emits_span_on_success(
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
