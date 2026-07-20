"""Unit tests for the /shields REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from app.endpoints.shields import shields_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import ShieldsResponse
from models.common.shields import CatalogShield
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


def _base_config_dict(
    shields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal AppConfig dict for shields endpoint tests."""
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
        "shields": shields or [],
        "customization": None,
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }


@pytest.mark.asyncio
async def test_shields_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the shields endpoint handler if configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.shields.configuration", mock_config)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as e:
        await shields_endpoint_handler(request=request, auth=auth)
    assert e.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert e.value.detail["response"] == "Configuration is not loaded"  # type: ignore


@pytest.mark.asyncio
async def test_shields_endpoint_handler_empty_list(mocker: MockerFixture) -> None:
    """Return an empty shields list when none are configured."""
    mock_authorization_resolvers(mocker)

    cfg = AppConfig()
    cfg.init_from_dict(_base_config_dict())
    mocker.patch("app.endpoints.shields.configuration", cfg)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await shields_endpoint_handler(request=request, auth=auth)
    assert isinstance(response, ShieldsResponse)
    assert response.shields == []


@pytest.mark.asyncio
async def test_shields_endpoint_handler_success_with_shields_data(
    mocker: MockerFixture,
) -> None:
    """Return configured shields in catalog shape."""
    mock_authorization_resolvers(mocker)

    cfg = AppConfig()
    cfg.init_from_dict(
        _base_config_dict(
            shields=[
                {
                    "shield_id": "lightspeed_question_validity",
                    "provider_id": "lightspeed_question_validity",
                    "provider_shield_id": "gpt-4o-mini",
                },
                {
                    "shield_id": "lightspeed_pii_redaction",
                    "provider_id": "lightspeed_pii_redaction",
                    "provider_shield_id": "lightspeed_pii_redaction",
                    "params": {
                        "rules": [
                            {
                                "pattern": r"secret",
                                "replacement": "[REDACTED]",
                            }
                        ]
                    },
                },
            ]
        )
    )
    mocker.patch("app.endpoints.shields.configuration", cfg)

    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    response = await shields_endpoint_handler(request=request, auth=auth)

    assert len(response.shields) == 2
    assert response.shields[0] == CatalogShield(
        identifier="lightspeed_question_validity",
        provider_resource_id="gpt-4o-mini",
        provider_id="lightspeed_question_validity",
        type="shield",
        params={},
    )
    assert response.shields[1].identifier == "lightspeed_pii_redaction"
    assert "rules" in response.shields[1].params
