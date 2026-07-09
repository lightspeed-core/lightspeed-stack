# pylint: disable=protected-access,too-many-lines

"""Unit tests for tools endpoint."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from llama_stack_client import APIConnectionError, BadRequestError
from pydantic import AnyHttpUrl, SecretStr
from pytest_mock import MockerFixture, MockType

# Import the function directly to bypass decorators
from app.endpoints import tools
from app.endpoints.tools import _input_schema_to_parameters
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import ToolsResponse
from models.config import (
    Configuration,
    CORSConfiguration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    TLSConfiguration,
    UserDataCollection,
)

# Shared mock auth tuple with 4 fields as expected by the application
MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


@pytest.fixture
def mock_configuration() -> Configuration:
    """Create a mock configuration with MCP servers."""
    return Configuration(
        name="test",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["foo_origin", "bar_origin", "baz_origin"],
                allow_credentials=False,
                allow_methods=["foo_method", "bar_method", "baz_method"],
                allow_headers=["foo_header", "bar_header", "baz_header"],
            ),
            host="localhost",
            port=1234,
            base_url=".",
            auth_enabled=False,
            workers=1,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            url=AnyHttpUrl("http://localhost:8321"),
            api_key=SecretStr("xyzzy"),
            use_as_library_client=False,
            library_client_config_path=".",
            timeout=10,
        ),
        user_data_collection=UserDataCollection(
            transcripts_enabled=False,
            feedback_enabled=False,
            transcripts_storage=".",
            feedback_storage=".",
        ),
        mcp_servers=[
            ModelContextProtocolServer(
                name="filesystem-tools",
                provider_id="model-context-protocol",
                url="http://localhost:3000",
            ),
            ModelContextProtocolServer(
                name="git-tools",
                provider_id="model-context-protocol",
                url="http://localhost:3001",
            ),
        ],
        customization=None,
        authorization=None,
        deployment_environment=".",
    )


@pytest.mark.asyncio
async def test_tools_endpoint_success(
    mocker: MockerFixture, mock_configuration: Configuration
) -> None:
    """Test successful tools endpoint response with multiple MCP servers."""
    # Mock configuration
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock Llama Stack client
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.get_client.return_value = mock_client

    # Mock HTTP GET /v1/tools response for each MCP server
    async def mock_get(path: str, **kwargs: Any) -> dict[str, Any]:
        params = kwargs.get("options", {}).get("params", {})
        toolgroup_id = params.get("toolgroup_id")

        if toolgroup_id == "filesystem-tools":
            return {
                "tools": [
                    {
                        "name": "filesystem_read",
                        "description": "Read file contents",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "File path"}
                            },
                            "required": ["path"],
                        },
                    }
                ]
            }
        if toolgroup_id == "git-tools":
            return {
                "tools": [
                    {
                        "name": "git_status",
                        "description": "Get git status",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "repo": {"type": "string", "description": "Repo path"}
                            },
                            "required": ["repo"],
                        },
                    }
                ]
            }
        return {"tools": []}

    mock_client.get.side_effect = mock_get

    # Mock request
    mock_request = mocker.Mock()
    mock_mcp_headers = mocker.Mock()
    mock_mcp_headers.authorization = None
    mock_mcp_headers.x_api_key = None

    # Call endpoint
    response = await tools.tools_endpoint_handler(
        request=mock_request, auth=MOCK_AUTH, mcp_headers=mock_mcp_headers
    )

    # Verify response
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 2
    assert response.tools[0]["identifier"] == "filesystem_read"
    assert response.tools[1]["identifier"] == "git_status"


@pytest.mark.asyncio
async def test_tools_endpoint_no_mcp_servers(mocker: MockerFixture) -> None:
    """Test tools endpoint with no MCP servers configured."""
    # Mock configuration with empty MCP servers
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=".",
            auth_enabled=False,
            workers=1,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            url=AnyHttpUrl("http://localhost:8321"),
            use_as_library_client=False,
            library_client_config_path=".",
            timeout=10,
        ),
        user_data_collection=UserDataCollection(
            transcripts_enabled=False,
            feedback_enabled=False,
            transcripts_storage=".",
            feedback_storage=".",
        ),
        mcp_servers=[],
        customization=None,
    )  # pyright: ignore[reportCallIssue]

    app_config = AppConfig()
    app_config._configuration = config
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock request
    mock_request = mocker.Mock()
    mock_mcp_headers = mocker.Mock()
    mock_mcp_headers.authorization = None
    mock_mcp_headers.x_api_key = None

    # Call endpoint
    response = await tools.tools_endpoint_handler(
        request=mock_request, auth=MOCK_AUTH, mcp_headers=mock_mcp_headers
    )

    # Verify empty response
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 0


@pytest.mark.asyncio
async def test_tools_endpoint_api_connection_error(
    mocker: MockerFixture, mock_configuration: Configuration
) -> None:
    """Test tools endpoint when Llama Stack is unreachable."""
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client to raise APIConnectionError
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client.get.side_effect = APIConnectionError(request=mocker.Mock())
    mock_client_holder.get_client.return_value = mock_client

    mock_request = mocker.Mock()
    mock_mcp_headers = mocker.Mock()
    mock_mcp_headers.authorization = None
    mock_mcp_headers.x_api_key = None

    # Should still succeed but with empty tools list
    response = await tools.tools_endpoint_handler(
        request=mock_request, auth=MOCK_AUTH, mcp_headers=mock_mcp_headers
    )

    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 0


@pytest.mark.asyncio
async def test_tools_endpoint_toolgroup_not_found(
    mocker: MockerFixture, mock_configuration: Configuration
) -> None:
    """Test tools endpoint when a toolgroup is not found (400 error)."""
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()

    # First toolgroup not found, second succeeds
    call_count = 0

    async def mock_get(path: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise BadRequestError(
                "Toolgroup not found", response=mocker.Mock(), body={}
            )
        return {
            "tools": [
                {
                    "name": "git_status",
                    "description": "Get git status",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ]
        }

    mock_client.get.side_effect = mock_get
    mock_client_holder.get_client.return_value = mock_client

    mock_request = mocker.Mock()
    mock_mcp_headers = mocker.Mock()
    mock_mcp_headers.authorization = None
    mock_mcp_headers.x_api_key = None

    response = await tools.tools_endpoint_handler(
        request=mock_request, auth=MOCK_AUTH, mcp_headers=mock_mcp_headers
    )

    # Should get tools from the second server only
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 1
    assert response.tools[0]["identifier"] == "git_status"


class TestInputSchemaToParameters:
    """Test suite for _input_schema_to_parameters function."""

    def test_none_schema(self) -> None:
        """Test conversion with None input schema."""
        assert _input_schema_to_parameters(None) is None

    def test_empty_schema(self) -> None:
        """Test conversion with empty schema."""
        result = _input_schema_to_parameters({})
        assert result == {"type": "object", "properties": {}}

    def test_schema_without_properties(self) -> None:
        """Test conversion with schema without properties."""
        schema = {"type": "object"}
        result = _input_schema_to_parameters(schema)
        assert result == {"type": "object", "properties": {}}

    def test_single_required_param(self) -> None:
        """Test conversion with single required parameter."""
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        }
        result = _input_schema_to_parameters(schema)
        assert result == {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        }

    def test_optional_param_with_default(self) -> None:
        """Test conversion with optional parameter."""
        schema = {
            "type": "object",
            "properties": {
                "timeout": {"type": "number", "description": "Timeout", "default": 30}
            },
        }
        result = _input_schema_to_parameters(schema)
        assert result == {
            "type": "object",
            "properties": {
                "timeout": {"type": "number", "description": "Timeout", "default": 30}
            },
        }

    def test_multiple_params_mixed_required(self) -> None:
        """Test conversion with multiple parameters, some required."""
        schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "mode": {"type": "string", "default": "read"},
            },
            "required": ["path"],
        }
        result = _input_schema_to_parameters(schema)
        assert result == {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "mode": {"type": "string", "default": "read"},
            },
            "required": ["path"],
        }
