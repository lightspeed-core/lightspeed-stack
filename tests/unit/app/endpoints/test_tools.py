# pylint: disable=protected-access,too-many-lines

"""Unit tests for tools endpoint."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, AnyHttpUrl
from fastapi import HTTPException
from llama_stack_client import APIConnectionError, BadRequestError
from pytest_mock import MockerFixture, MockType

# Import the function directly to bypass decorators
from app.endpoints import tools
from app.endpoints.tools import _input_schema_to_parameters
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.config import (
    Configuration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    UserDataCollection,
    TLSConfiguration,
    CORSConfiguration,
)
from models.responses import ToolsResponse

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


def _make_tool_def_mock(mocker: MockerFixture, fields: dict[str, Any]) -> MockType:
    """Create a mock ToolDef object matching Llama Stack's tools.list() output.

    The mock supports ``dict()`` conversion so the endpoint can do
    ``tool_dict = dict(tool)`` and get a plain dict back.
    """
    mock = mocker.Mock()
    mock.__dict__.update(fields)
    mock.keys.return_value = fields.keys()
    mock.__getitem__ = lambda self, key: self.__dict__[key]
    mock.__iter__ = lambda self: iter(self.__dict__)
    return mock


@pytest.fixture
def mock_tools_response(mocker: MockerFixture) -> list[MockType]:
    """Create mock tools response matching Llama Stack ToolDef format.

    Each mock uses ToolDef field names: ``name`` (not ``identifier``),
    ``input_schema`` (not ``parameters``), and no ``provider_id`` or ``type``
    (those live on the toolgroup, not on individual tools).

    Returns:
        list[MockType]: Two mock ToolDef objects for filesystem and git tools.
    """
    tool1 = _make_tool_def_mock(
        mocker,
        {
            "name": "filesystem_read",
            "description": "Read contents of a file from the filesystem",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    }
                },
                "required": ["path"],
            },
            "toolgroup_id": "filesystem-tools",
            "metadata": {},
            "output_schema": None,
        },
    )

    tool2 = _make_tool_def_mock(
        mocker,
        {
            "name": "git_status",
            "description": "Get the status of a git repository",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repository_path": {
                        "type": "string",
                        "description": "Path to the git repository",
                    }
                },
                "required": ["repository_path"],
            },
            "toolgroup_id": "git-tools",
            "metadata": {},
            "output_schema": None,
        },
    )

    return [tool1, tool2]


@pytest.mark.asyncio
async def test_tools_endpoint_success(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
    mock_tools_response: list[MockType],  # pylint: disable=redefined-outer-name
) -> None:
    """Test successful tools endpoint response."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response (toolgroups carry provider_id and type)
    mock_toolgroup1 = mocker.Mock()
    mock_toolgroup1.identifier = "filesystem-tools"
    mock_toolgroup1.provider_id = "model-context-protocol"
    mock_toolgroup1.type = "tool_group"
    mock_toolgroup2 = mocker.Mock()
    mock_toolgroup2.identifier = "git-tools"
    mock_toolgroup2.provider_id = "model-context-protocol"
    mock_toolgroup2.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup1, mock_toolgroup2]

    # Mock tools.list responses for each MCP server
    mock_client.tools.list.side_effect = [
        [mock_tools_response[0]],  # filesystem-tools response
        [mock_tools_response[1]],  # git-tools response
    ]

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    # Verify response
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 2

    # Verify first tool
    tool1 = response.tools[0]
    assert tool1["identifier"] == "filesystem_read"
    assert tool1["description"] == "Read contents of a file from the filesystem"
    assert tool1["server_source"] == "http://localhost:3000"
    assert tool1["toolgroup_id"] == "filesystem-tools"
    assert tool1["provider_id"] == "model-context-protocol"
    assert tool1["type"] == "tool_group"
    assert len(tool1["parameters"]) == 1
    assert tool1["parameters"][0]["name"] == "path"
    assert tool1["parameters"][0]["required"] is True

    # Verify second tool
    tool2 = response.tools[1]
    assert tool2["identifier"] == "git_status"
    assert tool2["description"] == "Get the status of a git repository"
    assert tool2["server_source"] == "http://localhost:3001"
    assert tool2["toolgroup_id"] == "git-tools"
    assert tool2["provider_id"] == "model-context-protocol"

    # Verify client calls
    assert mock_client.tools.list.call_count == 2
    mock_client.tools.list.assert_any_call(
        toolgroup_id="filesystem-tools",
        extra_headers={},
        extra_query={"authorization": None},
    )
    mock_client.tools.list.assert_any_call(
        toolgroup_id="git-tools",
        extra_headers={},
        extra_query={"authorization": None},
    )


@pytest.mark.asyncio
async def test_tools_endpoint_no_mcp_servers(mocker: MockerFixture) -> None:
    """Test tools endpoint with no MCP servers configured."""
    # Mock configuration with no MCP servers - wrap in AppConfig
    mock_config = Configuration(
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
        mcp_servers=[],
        customization=None,
        authorization=None,
        deployment_environment=".",
    )
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response - empty for no MCP servers
    mock_client.toolgroups.list.return_value = []

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    # Verify response
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 0


@pytest.mark.asyncio
async def test_tools_endpoint_api_connection_error(
    mocker: MockerFixture,  # pylint: disable=redefined-outer-name
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
) -> None:
    """Test tools endpoint with API connection error from individual servers."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response
    mock_toolgroup1 = mocker.Mock()
    mock_toolgroup1.identifier = "filesystem-tools"
    mock_toolgroup1.provider_id = "model-context-protocol"
    mock_toolgroup1.type = "tool_group"
    mock_toolgroup2 = mocker.Mock()
    mock_toolgroup2.identifier = "git-tools"
    mock_toolgroup2.provider_id = "model-context-protocol"
    mock_toolgroup2.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup1, mock_toolgroup2]

    # Mock API connection error - create a proper APIConnectionError
    api_error = APIConnectionError(request=mocker.Mock())
    mock_client.tools.list.side_effect = api_error

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint - should raise HTTPException when APIConnectionError occurs
    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
            mock_request, mock_auth, {}
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_partial_failure(  # pylint: disable=redefined-outer-name
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test tools endpoint with one MCP server failing with APIConnectionError."""
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    mock_toolgroup1 = mocker.Mock()
    mock_toolgroup1.identifier = "filesystem-tools"
    mock_toolgroup1.provider_id = "model-context-protocol"
    mock_toolgroup1.type = "tool_group"
    mock_toolgroup2 = mocker.Mock()
    mock_toolgroup2.identifier = "git-tools"
    mock_toolgroup2.provider_id = "model-context-protocol"
    mock_toolgroup2.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup1, mock_toolgroup2]

    api_error = APIConnectionError(request=mocker.Mock())
    mock_client.tools.list.side_effect = api_error

    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
            mock_request, mock_auth, {}
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_toolgroup_not_found(  # pylint: disable=redefined-outer-name
    mocker: MockerFixture,
    mock_configuration: Configuration,
    mock_tools_response: list[MockType],
) -> None:
    """Test tools endpoint when a toolgroup is not found (BadRequestError)."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response
    mock_toolgroup1 = mocker.Mock()
    mock_toolgroup1.identifier = "filesystem-tools"
    mock_toolgroup1.provider_id = "model-context-protocol"
    mock_toolgroup1.type = "tool_group"
    mock_toolgroup2 = mocker.Mock()
    mock_toolgroup2.identifier = "git-tools"
    mock_toolgroup2.provider_id = "model-context-protocol"
    mock_toolgroup2.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup1, mock_toolgroup2]

    # Mock tools.list responses - first succeeds, second raises BadRequestError
    bad_request_error = BadRequestError(
        message="Toolgroup not found",
        response=mocker.Mock(request=None),
        body=None,
    )
    mock_client.tools.list.side_effect = [
        [mock_tools_response[0]],  # filesystem-tools response
        bad_request_error,  # git-tools not found
    ]

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint - should continue processing and return tools from successful toolgroups
    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    # Verify response - should have only one tool from the first successful toolgroup
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 1
    assert response.tools[0]["identifier"] == "filesystem_read"
    assert response.tools[0]["server_source"] == "http://localhost:3000"
    assert response.tools[0]["provider_id"] == "model-context-protocol"

    # Verify that tools.list was called for both toolgroups
    assert mock_client.tools.list.call_count == 2
    mock_client.tools.list.assert_any_call(
        toolgroup_id="filesystem-tools",
        extra_headers={},
        extra_query={"authorization": None},
    )
    mock_client.tools.list.assert_any_call(
        toolgroup_id="git-tools",
        extra_headers={},
        extra_query={"authorization": None},
    )


@pytest.mark.asyncio
async def test_tools_endpoint_builtin_toolgroup(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
) -> None:
    """Test tools endpoint with built-in toolgroups."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response with built-in toolgroup
    mock_toolgroup = mocker.Mock()
    mock_toolgroup.identifier = "builtin-tools"  # Not in MCP server names
    mock_toolgroup.provider_id = "rag-runtime"
    mock_toolgroup.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup]

    # Mock tools.list response for built-in toolgroup (ToolDef format)
    mock_tool = _make_tool_def_mock(
        mocker,
        {
            "name": "builtin_tool",
            "description": "A built-in tool",
            "input_schema": None,
            "toolgroup_id": "builtin-tools",
            "metadata": {},
            "output_schema": None,
        },
    )

    mock_client.tools.list.return_value = [mock_tool]

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    # Verify response — identifier mapped from name, provider_id from toolgroup
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 1
    assert response.tools[0]["identifier"] == "builtin_tool"
    assert response.tools[0]["server_source"] == "builtin"
    assert response.tools[0]["provider_id"] == "rag-runtime"
    assert response.tools[0]["type"] == "tool_group"
    assert response.tools[0]["parameters"] == []


@pytest.mark.asyncio
async def test_tools_endpoint_mixed_toolgroups(mocker: MockerFixture) -> None:
    """Test tools endpoint with both MCP and built-in toolgroups."""
    # Mock configuration with MCP servers - wrap in AppConfig
    mock_config = Configuration(
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
        ],
        customization=None,
        authorization=None,
        deployment_environment=".",
    )
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list response with both MCP and built-in toolgroups
    mock_toolgroup1 = mocker.Mock()
    mock_toolgroup1.identifier = "filesystem-tools"  # MCP server toolgroup
    mock_toolgroup1.provider_id = "model-context-protocol"
    mock_toolgroup1.type = "tool_group"
    mock_toolgroup2 = mocker.Mock()
    mock_toolgroup2.identifier = "builtin-tools"  # Built-in toolgroup
    mock_toolgroup2.provider_id = "rag-runtime"
    mock_toolgroup2.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup1, mock_toolgroup2]

    # Mock tools.list responses (ToolDef format)
    mock_tool1 = _make_tool_def_mock(
        mocker,
        {
            "name": "filesystem_read",
            "description": "Read file",
            "input_schema": None,
            "toolgroup_id": "filesystem-tools",
            "metadata": {},
            "output_schema": None,
        },
    )

    mock_tool2 = _make_tool_def_mock(
        mocker,
        {
            "name": "builtin_tool",
            "description": "Built-in tool",
            "input_schema": None,
            "toolgroup_id": "builtin-tools",
            "metadata": {},
            "output_schema": None,
        },
    )

    mock_client.tools.list.side_effect = [[mock_tool1], [mock_tool2]]

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    # Verify response - should have both tools with correct server sources
    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 2

    # Find tools by identifier to avoid order dependency
    mcp_tool = next(t for t in response.tools if t["identifier"] == "filesystem_read")
    builtin_tool = next(t for t in response.tools if t["identifier"] == "builtin_tool")

    assert mcp_tool["server_source"] == "http://localhost:3000"
    assert mcp_tool["provider_id"] == "model-context-protocol"
    assert builtin_tool["server_source"] == "builtin"
    assert builtin_tool["provider_id"] == "rag-runtime"


@pytest.mark.asyncio
async def test_tools_endpoint_value_attribute_error(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
) -> None:
    """Test tools endpoint with ValueError/AttributeError in toolgroups.list."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list to raise ValueError
    mock_client.toolgroups.list.side_effect = ValueError("Invalid response format")

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpointt - should raise exception since toolgroups.list failed
    with pytest.raises(ValueError, match="Invalid response format"):
        await tools.tools_endpoint_handler.__wrapped__(mock_request, mock_auth, {})  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_apiconnection_error_toolgroups(  # pylint: disable=redefined-outer-name
    mocker: MockerFixture, mock_configuration: Configuration
) -> None:
    """Test tools endpoint with APIConnectionError in toolgroups.list."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder and clien
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Mock toolgroups.list to raise APIConnectionError
    api_error = APIConnectionError(request=mocker.Mock())
    mock_client.toolgroups.list.side_effect = api_error

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpointt and expect HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler.__wrapped__(mock_request, mock_auth, {})  # type: ignore

    assert exc_info.value.status_code == 503

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_client_holder_apiconnection_error(  # pylint: disable=redefined-outer-name
    mocker: MockerFixture, mock_configuration: Configuration
) -> None:
    """Test tools endpoint with APIConnectionError in client holder."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder to raise APIConnectionError
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    api_error = APIConnectionError(request=None)  # type: ignore
    mock_client_holder.return_value.get_client.side_effect = api_error

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpointt and expect HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler.__wrapped__(mock_request, mock_auth, {})  # type: ignore

    assert exc_info.value.status_code == 503

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Unable to connect to Llama Stack"  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_general_exception(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
) -> None:
    """Test tools endpoint with general exception."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)

    # Mock authorization decorator to bypass i
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    # Mock client holder to raise exception
    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client_holder.return_value.get_client.side_effect = Exception(
        "Unexpected error"
    )

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpointt and expect the exception to propagate (not caught)
    with pytest.raises(Exception, match="Unexpected error"):
        await tools.tools_endpoint_handler.__wrapped__(mock_request, mock_auth, {})  # type: ignore


@pytest.mark.asyncio
async def test_tools_endpoint_authentication_error_with_mcp_endpoint(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
) -> None:
    """Test tools endpoint raises 401 with WWW-Authenticate when check_mcp_auth requires OAuth."""
    app_config = AppConfig()
    app_config._configuration = mock_configuration
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")

    expected_headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'}
    probe_exception = HTTPException(
        status_code=401,
        detail={"cause": "MCP server at http://localhost:3000 requires OAuth"},
        headers=expected_headers,
    )
    mocker.patch(
        "app.endpoints.tools.check_mcp_auth",
        new_callable=mocker.AsyncMock,
        side_effect=probe_exception,
    )

    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    with pytest.raises(HTTPException) as exc_info:
        await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
            mock_request, mock_auth, {}
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers is not None
    assert (
        exc_info.value.headers.get("WWW-Authenticate") == 'Bearer error="invalid_token"'
    )


class TestInputSchemaToParameters:
    """Tests for _input_schema_to_parameters conversion."""

    def test_none_schema(self) -> None:
        """Test that None schema returns empty list."""
        assert _input_schema_to_parameters(None) == []

    def test_empty_schema(self) -> None:
        """Test that empty dict returns empty list."""
        assert _input_schema_to_parameters({}) == []

    def test_schema_without_properties(self) -> None:
        """Test that schema without properties returns empty list."""
        assert _input_schema_to_parameters({"type": "object"}) == []

    def test_single_required_param(self) -> None:
        """Test conversion of a single required parameter."""
        schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                }
            },
            "required": ["query"],
        }
        result = _input_schema_to_parameters(schema)
        assert len(result) == 1
        assert result[0]["name"] == "query"
        assert result[0]["description"] == "The search query"
        assert result[0]["parameter_type"] == "string"
        assert result[0]["required"] is True
        assert result[0]["default"] is None

    def test_optional_param_with_default(self) -> None:
        """Test conversion of an optional parameter with a default value."""
        schema = {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10,
                }
            },
            "required": [],
        }
        result = _input_schema_to_parameters(schema)
        assert len(result) == 1
        assert result[0]["name"] == "limit"
        assert result[0]["parameter_type"] == "integer"
        assert result[0]["required"] is False
        assert result[0]["default"] == 10

    def test_multiple_params_mixed_required(self) -> None:
        """Test conversion with a mix of required and optional parameters."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        }
        result = _input_schema_to_parameters(schema)
        assert len(result) == 2
        by_name = {p["name"]: p for p in result}
        assert by_name["query"]["required"] is True
        assert by_name["limit"]["required"] is False


@pytest.mark.asyncio
async def test_tools_endpoint_rag_builtin_toolgroup(mocker: MockerFixture) -> None:
    """Test that builtin::rag tools have correct fields (LCORE-1211 regression).

    Reproduces the exact scenario from LCORE-1211: Llama Stack returns RAG
    tools via the builtin::rag toolgroup using the ToolDef format.
    Previously, identifier, provider_id, parameters, and type were all
    returned as empty strings/lists.
    """
    mock_config = Configuration(
        name="test",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            host="localhost",
            port=8080,
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
        mcp_servers=[],
        customization=None,
        authorization=None,
        deployment_environment=".",
    )
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    # Toolgroup matching the real Llama Stack builtin::rag
    mock_toolgroup = mocker.Mock()
    mock_toolgroup.identifier = "builtin::rag"
    mock_toolgroup.provider_id = "rag-runtime"
    mock_toolgroup.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup]

    # Tools matching real Llama Stack ToolDef output
    rag_tool = _make_tool_def_mock(
        mocker,
        {
            "name": "knowledge_search",
            "description": "Search for information in a database.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for.",
                    }
                },
                "required": ["query"],
            },
            "toolgroup_id": "builtin::rag",
            "metadata": None,
            "output_schema": None,
        },
    )
    mock_client.tools.list.return_value = [rag_tool]

    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 1

    tool = response.tools[0]
    assert tool["identifier"] == "knowledge_search"
    assert tool["provider_id"] == "rag-runtime"
    assert tool["type"] == "tool_group"
    assert tool["server_source"] == "builtin"
    assert tool["toolgroup_id"] == "builtin::rag"

    # Parameters converted from input_schema
    assert len(tool["parameters"]) == 1
    assert tool["parameters"][0]["name"] == "query"
    assert tool["parameters"][0]["parameter_type"] == "string"
    assert tool["parameters"][0]["required"] is True


@pytest.mark.asyncio
async def test_tools_endpoint_empty_legacy_fields_overridden(
    mocker: MockerFixture,
) -> None:
    """Test that empty legacy fields are overridden by ToolDef fields.

    Regression variant: when a tool dict contains both new fields (name,
    input_schema) AND empty legacy fields (identifier="", parameters=[],
    provider_id="", type=""), the endpoint must populate from the new sources.
    """
    mock_config = Configuration(
        name="test",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            host="localhost",
            port=8080,
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
        mcp_servers=[],
        customization=None,
        authorization=None,
        deployment_environment=".",
    )
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client

    mock_toolgroup = mocker.Mock()
    mock_toolgroup.identifier = "builtin::rag"
    mock_toolgroup.provider_id = "rag-runtime"
    mock_toolgroup.type = "tool_group"
    mock_client.toolgroups.list.return_value = [mock_toolgroup]

    # Tool with both new fields AND empty legacy fields
    rag_tool = _make_tool_def_mock(
        mocker,
        {
            "name": "knowledge_search",
            "identifier": "",
            "description": "Search for information in a database.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for.",
                    }
                },
                "required": ["query"],
            },
            "parameters": [],
            "provider_id": "",
            "type": "",
            "toolgroup_id": "builtin::rag",
            "metadata": None,
            "output_schema": None,
        },
    )
    mock_client.tools.list.return_value = [rag_tool]

    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    response = await tools.tools_endpoint_handler.__wrapped__(  # pyright: ignore
        mock_request, mock_auth, {}
    )

    assert isinstance(response, ToolsResponse)
    assert len(response.tools) == 1

    tool = response.tools[0]
    # Empty legacy fields must be overridden by new sources
    assert tool["identifier"] == "knowledge_search"
    assert tool["provider_id"] == "rag-runtime"
    assert tool["type"] == "tool_group"
    assert tool["server_source"] == "builtin"
    assert tool["toolgroup_id"] == "builtin::rag"

    # Parameters populated from input_schema, not empty legacy list
    assert len(tool["parameters"]) == 1
    assert tool["parameters"][0]["name"] == "query"
    assert tool["parameters"][0]["parameter_type"] == "string"
    assert tool["parameters"][0]["required"] is True
