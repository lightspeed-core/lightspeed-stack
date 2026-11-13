"""Integration tests for the /tools endpoint."""

import pytest
from fastapi import HTTPException, Request, status
from pytest_mock import MockerFixture

from app.endpoints import tools
from authentication.interface import AuthTuple
from configuration import AppConfig

TOOLS_OAUTH_401_TEST_CASES = [
    pytest.param(
        {
            "www_authenticate": 'Bearer realm="oauth"',
            "expect_www_authenticate": True,
        },
        id="with_www_authenticate_when_mcp_oauth_required",
    ),
    pytest.param(
        {
            "www_authenticate": None,
            "expect_www_authenticate": False,
        },
        id="without_www_authenticate_when_oauth_probe_times_out",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", TOOLS_OAUTH_401_TEST_CASES)
async def test_tools_endpoint_returns_401_for_mcp_oauth(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    test_case: dict,
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Tests for tools endpoint MCP OAuth 401 responses.

    Tests different OAuth failure scenarios:
    - MCP server requires OAuth with WWW-Authenticate header
    - OAuth probe times out without WWW-Authenticate header

    When check_mcp_auth raises 401 (with or without WWW-Authenticate),
    the tools handler should propagate that response to the client.

    Parameters:
        test_case: Dictionary containing test parameters (www_authenticate, expect_www_authenticate)
        test_config: Test configuration
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture

    """
    _ = test_config

    www_authenticate = test_case["www_authenticate"]
    expect_www_authenticate = test_case["expect_www_authenticate"]

    # Build 401 exception with or without WWW-Authenticate header
    probe_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://url.com:1 requires OAuth"},
        headers={"WWW-Authenticate": www_authenticate} if www_authenticate else None,
    )
    mocker.patch(
        "app.endpoints.tools.check_mcp_auth",
        new_callable=mocker.AsyncMock,
        side_effect=probe_exception,
    )

    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler(
            request=test_request, auth=test_auth, mcp_headers={}
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    if expect_www_authenticate:
        assert exc_info.value.headers is not None
        assert exc_info.value.headers.get("WWW-Authenticate") == www_authenticate
    else:
        assert (
            exc_info.value.headers is None
            or exc_info.value.headers.get("WWW-Authenticate") is None
        )
