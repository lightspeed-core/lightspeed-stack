"""Unit tests for the / endpoint handler."""

from typing import Any

import pytest
from fastapi import Request
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

from app.endpoints.root import root_endpoint_handler
from authentication.interface import AuthTuple
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_root_endpoint(mocker: MockerFixture) -> None:
    """Test the root endpoint handler."""
    mock_authorization_resolvers(mocker)

    auth = AuthTuple(("test_user_id", "test_user_name", False, "token"))
    request = Request(
        scope={
            "type": "http",
        }
    )
    response = await root_endpoint_handler(auth=auth, request=request)
    assert response is not None


@pytest.mark.asyncio
async def test_root_emits_otel_span(
    mocker: MockerFixture,
    otel: tuple[Any, InMemorySpanExporter],
) -> None:
    """Test that the root handler emits a lightweight span with HTTP status."""
    tracer, exporter = otel
    mocker.patch("app.endpoints.root.tracer", tracer)
    mock_authorization_resolvers(mocker)

    auth = AuthTuple(("test_user_id", "test_user_name", False, "token"))
    request = Request(scope={"type": "http"})

    await root_endpoint_handler(auth=auth, request=request)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "root.handle_request"
    assert span.attributes is not None
    assert span.attributes["http.status_code"] == 200
