"""Integration tests for the /tools endpoint."""

from typing import Any, Generator

import pytest
from fastapi import HTTPException, Request, status
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

    When check_mcp_auth probes an MCP server and receives 401 with
    WWW-Authenticate, the handler raises 401 with that header so the
    client can perform OAuth.

    Verifies:
    - check_mcp_auth raises 401 with WWW-Authenticate
    - Response is 401 with WWW-Authenticate header
    """
    _ = test_config
    _ = mock_llama_stack_tools

    expected_www_auth = 'Bearer realm="oauth"'
    probe_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://url.com:1 requires OAuth"},
        headers={"WWW-Authenticate": expected_www_auth},
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

    When check_mcp_auth probes an MCP server and the probe times out
    (TimeoutError), the probe raises 401 without a WWW-Authenticate header.

    Verifies:
    - check_mcp_auth raises 401 without WWW-Authenticate (e.g. after timeout)
    - 401 is returned with no WWW-Authenticate header
    """
    _ = test_config
    _ = mock_llama_stack_tools

    probe_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"cause": "MCP server at http://url.com:1 requires OAuth"},
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
    assert (
        exc_info.value.headers is None
        or exc_info.value.headers.get("WWW-Authenticate") is None
    )
