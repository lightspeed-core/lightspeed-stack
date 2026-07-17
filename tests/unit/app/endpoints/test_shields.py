"""Unit tests for the /shields REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from lightspeed_stack.app.endpoints.shields import shields_endpoint_handler
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.models.api.responses.successful import ShieldsResponse
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

    # configuration for tests
    config_dict: dict[str, Any] = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
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

    mocker.patch("lightspeed_stack.app.endpoints.shields.configuration", cfg)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("lightspeed_stack.app.endpoints.shields.configuration", mock_config)

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

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_client.shields.list.return_value = []
    mock_lsc = mocker.patch("lightspeed_stack.client.AsyncOgxClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mocker.patch("lightspeed_stack.app.endpoints.shields.configuration", cfg)

    request, auth = _auth_request()

    response = await shields_endpoint_handler(request=request, auth=auth)
    assert isinstance(response, ShieldsResponse)
    assert response.shields == []


@pytest.mark.asyncio
async def test_shields_endpoint_handler_success_with_shields_data(
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
    mocker.patch("lightspeed_stack.client.AsyncOgxClientHolder.get_client")
    cfg.init_from_dict(config_dict)
    mocker.patch("lightspeed_stack.app.endpoints.shields.configuration", cfg)

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
