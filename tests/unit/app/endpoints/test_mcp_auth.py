# pylint: disable=protected-access,redefined-outer-name
# pyright: reportCallIssue=false

"""Unit tests for MCP auth endpoint."""

from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pytest_mock import MockerFixture

# Import the function directly to bypass decorators
from app.endpoints import mcp_auth
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import MCPClientAuthOptionsResponse
from models.config import (
    Configuration,
    ModelContextProtocolServer,
    OgxConfiguration,
    ServiceConfiguration,
    UserDataCollection,
)

# Shared mock auth tuple with 4 fields as expected by the application
MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


@pytest.fixture
def mock_configuration_with_client_auth() -> Configuration:
    """Create a mock configuration with MCP servers that have client auth."""
    return Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[
            ModelContextProtocolServer(
                name="github",
                provider_id="model-context-protocol",
                url="http://github-mcp:8080",
                authorization_headers={"Authorization": "client"},
            ),
            ModelContextProtocolServer(
                name="gitlab",
                provider_id="model-context-protocol",
                url="http://gitlab-mcp:8080",
                authorization_headers={
                    "Authorization": "client",
                    "X-API-Key": "client",
                },
            ),
        ],
    )  # type: ignore[call-arg]


@pytest.fixture
def mock_configuration_mixed_auth() -> Configuration:
    """Create a mock configuration with mixed auth types."""
    return Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[
            ModelContextProtocolServer(
                name="github",
                provider_id="model-context-protocol",
                url="http://github-mcp:8080",
                authorization_headers={"Authorization": "client"},
            ),
            ModelContextProtocolServer(
                name="k8s_mgmt",
                provider_id="model-context-protocol",
                url="http://k8s-mcp:8080",
                authorization_headers={"Authorization": "kubernetes"},
            ),
            ModelContextProtocolServer(
                name="public_server",
                provider_id="model-context-protocol",
                url="http://public-mcp:8080",
                # No authorization headers
            ),
        ],
    )  # type: ignore[call-arg]


@pytest.fixture
def mock_configuration_no_client_auth() -> Configuration:
    """Create a mock configuration with no client auth servers."""
    return Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[
            ModelContextProtocolServer(
                name="k8s_mgmt",
                provider_id="model-context-protocol",
                url="http://k8s-mcp:8080",
                authorization_headers={"Authorization": "kubernetes"},
            ),
            ModelContextProtocolServer(
                name="public_server",
                provider_id="model-context-protocol",
                url="http://public-mcp:8080",
                # No authorization headers
            ),
        ],
    )  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_success(
    mocker: MockerFixture,
    mock_configuration_with_client_auth: Configuration,
) -> None:
    """Test successful retrieval of MCP servers with client auth options."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration_with_client_auth
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 2

    # Verify github server
    github = next(s for s in response.servers if s.name == "github")
    assert github.client_auth_headers == ["Authorization"]

    # Verify gitlab server
    gitlab = next(s for s in response.servers if s.name == "gitlab")
    assert set(gitlab.client_auth_headers) == {"Authorization", "X-API-Key"}


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_mixed_auth(
    mocker: MockerFixture,
    mock_configuration_mixed_auth: Configuration,
) -> None:
    """Test retrieval with mixed auth types - should only return client auth servers."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration_mixed_auth
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response - should only have github server, not k8s_mgmt or public_server
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 1

    assert response.servers[0].name == "github"
    assert response.servers[0].client_auth_headers == ["Authorization"]

    # Verify k8s_mgmt and public_server are not in the response
    assert not any(s.name == "k8s_mgmt" for s in response.servers)
    assert not any(s.name == "public_server" for s in response.servers)


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_no_client_auth(
    mocker: MockerFixture,
    mock_configuration_no_client_auth: Configuration,
) -> None:
    """Test retrieval when no servers have client auth - should return empty list."""
    # Mock configuration - wrap in AppConfig
    app_config = AppConfig()
    app_config._configuration = mock_configuration_no_client_auth
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response - should be empty
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 0


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_empty_config(
    mocker: MockerFixture,
) -> None:
    """Test retrieval when no MCP servers are configured."""
    # Mock configuration with no MCP servers - wrap in AppConfig
    mock_config = Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[],
    )  # type: ignore[call-arg]
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response - should be empty
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 0


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_whitespace_handling(
    mocker: MockerFixture,
) -> None:
    """Test that whitespace in authorization header values is handled correctly."""
    # Mock configuration with whitespace in values - wrap in AppConfig
    mock_config = Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[
            ModelContextProtocolServer(
                name="server1",
                provider_id="model-context-protocol",
                url="http://server1:8080",
                authorization_headers={"Authorization": "  client  "},  # With spaces
            ),
            ModelContextProtocolServer(
                name="server2",
                provider_id="model-context-protocol",
                url="http://server2:8080",
                authorization_headers={"Authorization": "kubernetes  "},  # With spaces
            ),
        ],
    )  # type: ignore[call-arg]
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response - should have server1 (with spaces around "client")
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 1
    assert response.servers[0].name == "server1"


@pytest.mark.asyncio
async def test_get_mcp_client_auth_options_multiple_headers_single_server(
    mocker: MockerFixture,
) -> None:
    """Test server with multiple client auth headers."""
    # Mock configuration - wrap in AppConfig
    mock_config = Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        ogx=OgxConfiguration(url="http://localhost:8321"),  # type: ignore[call-arg]
        user_data_collection=UserDataCollection(feedback_enabled=False),  # type: ignore[call-arg]
        mcp_servers=[
            ModelContextProtocolServer(
                name="multi_auth",
                provider_id="model-context-protocol",
                url="http://multi:8080",
                authorization_headers={
                    "Authorization": "client",
                    "X-API-Key": "client",
                    "X-Custom-Token": "client",
                },
            ),
        ],
    )  # type: ignore[call-arg]
    app_config = AppConfig()
    app_config._configuration = mock_config
    mocker.patch("app.endpoints.mcp_auth.configuration", app_config)

    # Mock authorization decorator to bypass it
    mocker.patch("app.endpoints.mcp_auth.authorize", lambda action: lambda func: func)

    # Mock request and auth
    mock_request = mocker.Mock()
    mock_auth = MOCK_AUTH

    # Call the endpoint
    response = await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
        mock_request, mock_auth
    )

    # Verify response
    assert isinstance(response, MCPClientAuthOptionsResponse)
    assert len(response.servers) == 1
    assert response.servers[0].name == "multi_auth"
    assert set(response.servers[0].client_auth_headers) == {
        "Authorization",
        "X-API-Key",
        "X-Custom-Token",
    }


class TestMcpAuthOtelSpans:
    """OTEL instrumentation tests for the /mcp-auth endpoints."""

    @pytest.mark.asyncio
    async def test_get_client_options_span_attributes(
        self,
        mocker: MockerFixture,
        mock_configuration_with_client_auth: Configuration,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test that get_mcp_client_auth_options emits a span with correct attributes."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.mcp_auth.tracer", tracer)

        app_config = AppConfig()
        app_config._configuration = mock_configuration_with_client_auth
        mocker.patch("app.endpoints.mcp_auth.configuration", app_config)
        mocker.patch(
            "app.endpoints.mcp_auth.authorize",
            lambda action: lambda func: func,
        )

        mock_request = mocker.Mock()
        await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
            mock_request, MOCK_AUTH
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "mcp_auth.get_client_options"
        attrs = dict(span.attributes or {})
        assert attrs["mcp.operation"] == "get_client_options"
        assert attrs["mcp.servers.count"] == 2

    @pytest.mark.asyncio
    async def test_get_client_options_span_empty_result(
        self,
        mocker: MockerFixture,
        mock_configuration_no_client_auth: Configuration,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Test span when no servers have client auth — count should be 0."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.mcp_auth.tracer", tracer)

        app_config = AppConfig()
        app_config._configuration = mock_configuration_no_client_auth
        mocker.patch("app.endpoints.mcp_auth.configuration", app_config)
        mocker.patch(
            "app.endpoints.mcp_auth.authorize",
            lambda action: lambda func: func,
        )

        mock_request = mocker.Mock()
        await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
            mock_request, MOCK_AUTH
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes or {})
        assert attrs["mcp.servers.count"] == 0

    @pytest.mark.asyncio
    async def test_get_client_options_span_no_secrets(
        self,
        mocker: MockerFixture,
        mock_configuration_with_client_auth: Configuration,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """Verify that no auth tokens, headers, or secrets appear in span attributes."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.mcp_auth.tracer", tracer)

        app_config = AppConfig()
        app_config._configuration = mock_configuration_with_client_auth
        mocker.patch("app.endpoints.mcp_auth.configuration", app_config)
        mocker.patch(
            "app.endpoints.mcp_auth.authorize",
            lambda action: lambda func: func,
        )

        mock_request = mocker.Mock()
        await mcp_auth.get_mcp_client_auth_options.__wrapped__(  # type: ignore
            mock_request, MOCK_AUTH
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes or {})
        forbidden_keys = {"authorization", "token", "secret", "header", "key"}
        for attr_key in attrs:
            assert not any(
                word in str(attr_key).lower() for word in forbidden_keys
            ), f"Span attribute '{attr_key}' may contain sensitive data"
        for attr_val in attrs.values():
            val_lower = str(attr_val).lower()
            assert "bearer" not in val_lower
            assert "client" not in val_lower or attr_val == "get_client_options"
