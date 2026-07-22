"""MCP server metadata models shared by registration and list responses."""

from pydantic import BaseModel, Field


class MCPServerAuthInfo(BaseModel):
    """Information about MCP server client authentication options."""

    name: str = Field(..., description="MCP server name")
    client_auth_headers: list[str] = Field(
        ...,
        description="List of authentication header names for client-provided tokens",
    )


class MCPServerInfo(BaseModel):
    """Information about a registered MCP server.

    Attributes:
        name: Unique name of the MCP server.
        url: URL of the MCP server endpoint.
        provider_id: MCP provider identification.
        source: Whether the server was registered statically (config) or dynamically (api).
    """

    name: str = Field(..., description="MCP server name")
    url: str = Field(..., description="MCP server URL")
    provider_id: str = Field(..., description="MCP provider identification")
    source: str = Field(
        ...,
        description="How the server was registered: 'config' (static) or 'api' (dynamic)",
        examples=["config", "api"],
    )
