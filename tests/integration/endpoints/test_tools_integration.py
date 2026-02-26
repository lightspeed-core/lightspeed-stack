"""Integration tests for the /tools endpoint."""

from typing import Any, Generator

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import AuthenticationError
from pytest_mock import MockerFixture

from app.endpoints import tools
from authentication.interface import AuthTuple
from configuration import AppConfig


@pytest.fixture(name="mock_llama_stack_tools")
def mock_llama_stack_tools_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock the Llama Stack client for tools endpoint.

    Returns:
        Mock client with toolgroups.list and tools.list configured.
    """
    mock_holder_class = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_holder_class.return_value.get_client.return_value = mock_client
    yield mock_client


@pytest.mark.asyncio
async def test_tools_endpoint_returns_401_with_www_authenticate_when_mcp_oauth_required(
    test_config: AppConfig,
    mock_llama_stack_tools: Any,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test GET /tools returns 401 with WWW-Authenticate when MCP server requires OAuth.

    When tools.list raises AuthenticationError and the toolgroup has an
    mcp_endpoint, the handler calls probe_mcp_oauth_and_raise_401 and
    raises 401 with WWW-Authenticate so the client can perform OAuth.

    Verifies:
    - AuthenticationError from first toolgroup triggers OAuth probe
    - Response is 401 with WWW-Authenticate header
    """
    _ = test_config

    mock_toolgroup = mocker.Mock()
    mock_toolgroup.identifier = "server1"
    mock_toolgroup.mcp_endpoint = mocker.Mock()
    mock_toolgroup.mcp_endpoint.uri = "http://url.com:1"
    mock_llama_stack_tools.toolgroups.list.return_value = [mock_toolgroup]

    auth_error = AuthenticationError(
        message="MCP server requires OAuth",
        response=mocker.Mock(request=None),
        body=None,
    )
    mock_llama_stack_tools.tools.list.side_effect = auth_error

    expected_www_auth = 'Bearer realm="oauth"'
    probe_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://url.com:1 requires OAuth"},
        headers={"WWW-Authenticate": expected_www_auth},
    )
    mocker.patch(
        "app.endpoints.tools.probe_mcp_oauth_and_raise_401",
        new_callable=mocker.AsyncMock,
        side_effect=probe_exception,
    )

    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler(request=test_request, auth=test_auth)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("WWW-Authenticate") == expected_www_auth


@pytest.mark.asyncio
async def test_tools_endpoint_returns_401_when_oauth_probe_times_out(
    test_config: AppConfig,
    mock_llama_stack_tools: Any,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test GET /tools returns 401 when OAuth probe times out.

    When tools.list raises AuthenticationError and the toolgroup has an
    mcp_endpoint, the handler calls probe_mcp_oauth_and_raise_401. If the probe
    times out (TimeoutError), the probe raises 401 without a WWW-Authenticate
    header.

    Verifies:
    - Real probe runs and hits a timeout (aiohttp session.get raises TimeoutError)
    - 401 is returned with no WWW-Authenticate header
    """
    _ = test_config

    mock_toolgroup = mocker.Mock()
    mock_toolgroup.identifier = "server1"
    mock_toolgroup.mcp_endpoint = mocker.Mock()
    mock_toolgroup.mcp_endpoint.uri = "http://url.com:1"
    mock_llama_stack_tools.toolgroups.list.return_value = [mock_toolgroup]

    auth_error = AuthenticationError(
        message="MCP server requires OAuth",
        response=mocker.Mock(request=None),
        body=None,
    )
    mock_llama_stack_tools.tools.list.side_effect = auth_error

    # Simulate timeout: session.get() raises TimeoutError; real probe catches it and raises 401.
    mock_session = mocker.Mock()
    mock_session.get = mocker.Mock(side_effect=TimeoutError("OAuth probe timed out"))
    mock_session_cm = mocker.AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session
    mock_session_cm.__aexit__.return_value = None
    mocker.patch(
        "utils.mcp_oauth_probe.aiohttp.ClientSession", return_value=mock_session_cm
    )

    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler(request=test_request, auth=test_auth)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        exc_info.value.headers is None
        or exc_info.value.headers.get("WWW-Authenticate") is None
    )
