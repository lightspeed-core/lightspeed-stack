# pylint: disable=protected-access,redefined-outer-name

"""Unit tests for tools endpoint."""

from pathlib import Path
from typing import Optional

import pytest
from pydantic import AnyHttpUrl, SecretStr
from pytest_mock import MockerFixture

from app.endpoints import tools
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import ToolsResponse
from models.common.tools import ListedMcpTool
from models.config import (
    Configuration,
    CORSConfiguration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    SkillsConfiguration,
    TLSConfiguration,
    UserDataCollection,
)
from utils.builtin_tools import FILE_SEARCH_CATALOG_TOOLS

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


def _mock_file_search_tools(
    mocker: MockerFixture, file_search_tools: Optional[list] = None
) -> None:
    """Patch LLS file-search discovery for tools tests."""
    mocker.patch("app.endpoints.tools.AsyncOgxClientHolder")
    mocker.patch(
        "app.endpoints.tools.get_file_search_tools",
        new_callable=mocker.AsyncMock,
        return_value=(
            FILE_SEARCH_CATALOG_TOOLS
            if file_search_tools is None
            else file_search_tools
        ),
    )


def _make_app_config(mocker: MockerFixture, config: Configuration) -> AppConfig:
    """Create an AppConfig with the given configuration and patch it."""
    app_config = AppConfig()
    app_config._configuration = config
    mocker.patch("app.endpoints.tools.configuration", app_config)
    return app_config


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
async def test_tools_lists_builtin_and_mcp_tools(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Return file-search tools from LLS plus MCP tools discovered locally."""
    _make_app_config(mocker, mock_configuration)
    mocker.patch(
        "app.endpoints.tools.check_configuration_loaded",
        return_value=None,
    )
    mocker.patch(
        "app.endpoints.tools.build_mcp_headers",
        return_value={"filesystem-tools": {}, "git-tools": {}},
    )
    mocker.patch("app.endpoints.tools.check_mcp_auth", return_value=None)
    mocker.patch(
        "app.endpoints.tools.get_agent_capability_tools",
        return_value=[],
    )
    _mock_file_search_tools(mocker)
    mock_list = mocker.patch(
        "app.endpoints.tools.list_mcp_tools",
        side_effect=[
            [
                ListedMcpTool(
                    name="filesystem_read",
                    description="Read contents of a file from the filesystem",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file to read",
                            }
                        },
                        "required": ["path"],
                    },
                )
            ],
            [
                ListedMcpTool(
                    name="git_status",
                    description="Show working tree status",
                    input_schema=None,
                )
            ],
        ],
    )

    request = mocker.Mock()
    request.headers = {}

    response = await tools.tools_endpoint_handler(
        request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    assert isinstance(response, ToolsResponse)
    assert mock_list.call_count == 2
    identifiers = {tool.identifier for tool in response.tools}
    assert "insert_into_memory" in identifiers
    assert "file_search" in identifiers
    assert "filesystem_read" in identifiers
    assert "git_status" in identifiers


@pytest.mark.asyncio
async def test_tools_skips_server_with_unresolved_auth(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Skip MCP servers when required auth headers cannot be resolved."""
    mock_configuration.mcp_servers = [
        ModelContextProtocolServer(
            name="secure-tools",
            provider_id="model-context-protocol",
            url="http://localhost:3002",
            authorization_headers={"Authorization": "client"},
        )
    ]
    _make_app_config(mocker, mock_configuration)
    mocker.patch(
        "app.endpoints.tools.check_configuration_loaded",
        return_value=None,
    )
    mocker.patch(
        "app.endpoints.tools.build_mcp_headers",
        return_value={},
    )
    mocker.patch("app.endpoints.tools.check_mcp_auth", return_value=None)
    mocker.patch(
        "app.endpoints.tools.get_agent_capability_tools",
        return_value=[],
    )
    _mock_file_search_tools(mocker)
    mock_list = mocker.patch("app.endpoints.tools.list_mcp_tools")

    request = mocker.Mock()
    request.headers = {}

    response = await tools.tools_endpoint_handler(
        request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    mock_list.assert_not_called()
    identifiers = {tool.identifier for tool in response.tools}
    assert identifiers == {"insert_into_memory", "file_search"}


@pytest.mark.asyncio
async def test_tools_continues_when_mcp_list_returns_empty(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Skip MCP servers that fail discovery without failing the request."""
    mock_configuration.mcp_servers = [
        ModelContextProtocolServer(
            name="broken-tools",
            provider_id="model-context-protocol",
            url="http://localhost:3999",
        )
    ]
    _make_app_config(mocker, mock_configuration)
    mocker.patch(
        "app.endpoints.tools.check_configuration_loaded",
        return_value=None,
    )
    mocker.patch(
        "app.endpoints.tools.build_mcp_headers",
        return_value={"broken-tools": {}},
    )
    mocker.patch("app.endpoints.tools.check_mcp_auth", return_value=None)
    mocker.patch(
        "app.endpoints.tools.get_agent_capability_tools",
        return_value=[],
    )
    _mock_file_search_tools(mocker)
    mocker.patch(
        "app.endpoints.tools.list_mcp_tools",
        return_value=[],
    )

    request = mocker.Mock()
    request.headers = {}

    response = await tools.tools_endpoint_handler(
        request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    identifiers = {tool.identifier for tool in response.tools}
    assert "filesystem_read" not in identifiers
    assert "insert_into_memory" in identifiers


@pytest.mark.asyncio
async def test_tools_skips_mcp_server_when_discovery_returns_no_tools(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Skip MCP servers that return no tools without failing the request."""
    mock_configuration.mcp_servers = [
        ModelContextProtocolServer(
            name="oauth-tools",
            provider_id="model-context-protocol",
            url="http://localhost:3003",
        )
    ]
    _make_app_config(mocker, mock_configuration)
    mocker.patch(
        "app.endpoints.tools.check_configuration_loaded",
        return_value=None,
    )
    mocker.patch(
        "app.endpoints.tools.build_mcp_headers",
        return_value={"oauth-tools": {}},
    )
    mocker.patch("app.endpoints.tools.check_mcp_auth", return_value=None)
    mocker.patch(
        "app.endpoints.tools.get_agent_capability_tools",
        return_value=[],
    )
    _mock_file_search_tools(mocker)
    mocker.patch(
        "app.endpoints.tools.list_mcp_tools",
        return_value=[],
    )

    request = mocker.Mock()
    request.headers = {}

    response = await tools.tools_endpoint_handler(
        request,
        auth=MOCK_AUTH,
        mcp_headers={},
    )

    identifiers = {tool.identifier for tool in response.tools}
    assert identifiers == {"insert_into_memory", "file_search"}


@pytest.mark.asyncio
async def test_tools_endpoint_includes_agent_capability_tools(
    mocker: MockerFixture,
    mock_configuration: Configuration,  # pylint: disable=redefined-outer-name
    mock_skills_configuration: SkillsConfiguration,
) -> None:
    """Test that configured pydantic-ai capabilities appear in /tools output."""
    config_with_skills = mock_configuration.model_copy(
        update={"skills": mock_skills_configuration}
    )
    app_config = AppConfig()
    app_config._configuration = config_with_skills
    mocker.patch("app.endpoints.tools.configuration", app_config)
    mocker.patch("app.endpoints.tools.authorize", lambda _: lambda func: func)

    mock_client_holder = mocker.patch("app.endpoints.tools.AsyncOgxClientHolder")
    mock_client = mocker.AsyncMock()
    mock_client_holder.return_value.get_client.return_value = mock_client
    mock_client.toolgroups.list.return_value = []

    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    response = await tools.tools_endpoint_handler.__wrapped__(
        mock_request, mock_auth, {}
    )  # pyright: ignore[reportFunctionMemberAccess]

    tool_ids = [tool["identifier"] for tool in response.tools]
    assert "list_skills" in tool_ids
    assert "load_skill" in tool_ids
    assert "read_skill_resource" in tool_ids
    assert "run_skill_script" in tool_ids

    list_skills = next(
        tool for tool in response.tools if tool["identifier"] == "list_skills"
    )
    assert list_skills["provider_id"] == "agent-skills"
    assert list_skills["toolgroup_id"] == "builtin::agent-skills"
    assert list_skills["server_source"] == "builtin"
