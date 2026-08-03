"""Unit tests for the /config REST API endpoint."""

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from lightspeed_stack.app.endpoints.config import config_endpoint_handler
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_config_endpoint_handler_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test the config endpoint handler when configuration is not loaded."""
    mock_authorization_resolvers(mocker)

    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("lightspeed_stack.app.endpoints.config.configuration", mock_config)

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

    mocker.patch("lightspeed_stack.app.endpoints.config.configuration", minimal_config)

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
