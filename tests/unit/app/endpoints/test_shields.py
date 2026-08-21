"""Unit tests for the /shields REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode
from pytest_mock import MockerFixture

from app.endpoints.shields import shields_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import ShieldsResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


def _base_config_dict() -> dict[str, Any]:
    """Return a minimal valid AppConfig dictionary."""
    return {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }


def _auth_request() -> tuple[Request, AuthTuple]:
    """Return a dummy request and auth tuple for the shields handler."""
    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")
    return request, auth


@pytest.mark.asyncio
async def test_shields_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.shields.configuration", mock_config)

    request, auth = _auth_request()

    with pytest.raises(HTTPException) as e:
        await shields_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_shields_endpoint_handler_empty_shields(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint returns an empty list when none are configured."""
    mock_authorization_resolvers(mocker)

    cfg = AppConfig()
    cfg.init_from_dict(_base_config_dict())
    mocker.patch("app.endpoints.shields.configuration", cfg)

    request, auth = _auth_request()

    response = await shields_endpoint_handler(request=request, auth=auth)
    assert isinstance(response, ShieldsResponse)
    assert response.shields == []


@pytest.mark.asyncio
async def test_shields_endpoint_handler_configured_shields(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint lists shields from LCS configuration."""
    mock_authorization_resolvers(mocker)

    config_dict = _base_config_dict()
    config_dict["shields"] = [
        {
            "name": "question-validity",
            "provider_id": "question_validity",
            "config": {
                "model_id": "openai/gpt-4o-mini",
                "model_prompt": "Is this question valid?",
                "invalid_question_response": "I can only answer product questions.",
            },
        },
        {
            "name": "pii-redaction",
            "provider_id": "redaction",
            "config": {
                "rules": [
                    {
                        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                        "replacement": "[REDACTED]",
                    }
                ],
                "case_sensitive": False,
            },
        },
    ]
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    mocker.patch("app.endpoints.shields.configuration", cfg)

    request, auth = _auth_request()

    response = await shields_endpoint_handler(request=request, auth=auth)

    assert isinstance(response, ShieldsResponse)
    assert len(response.shields) == 2
    assert response.shields[0].name == "question-validity"
    assert response.shields[0].provider_id == "question_validity"
    assert response.shields[0].type == "shield"
    assert response.shields[0].config["model_id"] == "openai/gpt-4o-mini"
    assert response.shields[1].name == "pii-redaction"
    assert response.shields[1].provider_id == "redaction"
    assert response.shields[1].type == "shield"
    assert response.shields[1].config["rules"][0]["replacement"] == "[REDACTED]"


class TestShieldsEndpointOtel:
    """OTEL instrumentation tests for the /shields endpoint."""

    @pytest.mark.asyncio
    async def test_emits_span_with_shield_count(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that a successful /shields request emits a span with shields.count."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.shields.tracer", tracer)
        mock_authorization_resolvers(mocker)

        cfg = AppConfig()
        cfg.init_from_dict(_base_config_dict())
        mocker.patch("app.endpoints.shields.configuration", cfg)

        request, auth = _auth_request()

        await shields_endpoint_handler(request=request, auth=auth)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "shields.list"
        assert span.attributes is not None
        assert span.attributes["shields.count"] == 0

    @pytest.mark.asyncio
    async def test_span_records_error_when_config_not_loaded(
        self,
        mocker: MockerFixture,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that the span records an error when configuration is not loaded."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.shields.tracer", tracer)
        mock_authorization_resolvers(mocker)

        mock_config = AppConfig()
        mock_config._configuration = None  # pylint: disable=protected-access
        mocker.patch("app.endpoints.shields.configuration", mock_config)

        request, auth = _auth_request()

        with pytest.raises(HTTPException):
            await shields_endpoint_handler(request=request, auth=auth)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "shields.list"
        assert spans[0].status.status_code == StatusCode.ERROR
