"""Request models for MCP server registration."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from constants import MCP_AUTH_CLIENT, MCP_AUTH_KUBERNETES, MCP_AUTH_OAUTH


class MCPServerRegistrationRequest(BaseModel):
    """Request model for dynamically registering an MCP server.

    Attributes:
        name: Unique name for the MCP server.
        url: URL of the MCP server endpoint.
        provider_id: MCP provider identification (defaults to "model-context-protocol").
        authorization_headers: Optional headers to send to the MCP server.
        headers: Optional list of HTTP header names to forward from incoming requests.
        timeout: Optional request timeout in seconds.
    """

    name: str = Field(
        ...,
        description="Unique name for the MCP server",
        examples=["my-mcp-tools"],
        min_length=1,
        max_length=256,
    )

    url: str = Field(
        ...,
        description="URL of the MCP server endpoint",
        examples=["http://host.docker.internal:7008/api/mcp-actions/v1"],
    )

    provider_id: str = Field(
        "model-context-protocol",
        description="MCP provider identification",
        examples=["model-context-protocol"],
    )

    authorization_headers: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Headers to send to the MCP server. Values must be one of the "
            "supported token resolution keywords: "
            "'client' - forward the caller's token provided via MCP-HEADERS, "
            "'kubernetes' - use the authenticated user's Kubernetes token, "
            "'oauth' - use an OAuth token provided via MCP-HEADERS. "
            "File-path based secrets (used in static YAML config) are not "
            "supported for dynamically registered servers."
        ),
        examples=[
            {"Authorization": "client"},
            {"Authorization": "kubernetes"},
            {"Authorization": "oauth"},
        ],
    )

    headers: Optional[list[str]] = Field(
        default=None,
        description="List of HTTP header names to forward from incoming requests",
        examples=[["x-rh-identity"]],
    )

    timeout: Optional[int] = Field(
        default=None,
        description="Request timeout in seconds for the MCP server",
        gt=0,
        examples=[30],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "mcp-integration-tools",
                    "url": "http://host.docker.internal:7008/api/mcp-actions/v1",
                    "authorization_headers": {"Authorization": "client"},
                },
                {
                    "name": "k8s-internal-service",
                    "url": "http://internal-mcp.default.svc.cluster.local:8080",
                    "authorization_headers": {"Authorization": "kubernetes"},
                },
                {
                    "name": "oauth-mcp-server",
                    "url": "https://mcp.example.com/api",
                    "authorization_headers": {"Authorization": "oauth"},
                },
                {
                    "name": "test-mcp-server",
                    "url": "http://host.docker.internal:8888/mcp",
                    "provider_id": "model-context-protocol",
                    "headers": ["x-rh-identity"],
                    "timeout": 30,
                },
            ]
        },
    }

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Validate that URL uses http or https scheme.

        Args:
            value: The URL string to validate.

        Returns:
            The validated URL string.

        Raises:
            ValueError: If URL does not start with http:// or https://.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must use http:// or https:// scheme")
        return value

    @field_validator("authorization_headers")
    @classmethod
    def validate_authorization_header_values(
        cls, value: Optional[dict[str, str]]
    ) -> Optional[dict[str, str]]:
        """Validate that authorization header values use supported keywords.

        Dynamic registration only supports the token resolution keywords
        client, kubernetes, and oauth. File-path based secrets are rejected
        since the API client cannot guarantee files exist on the server
        filesystem.

        Args:
            value: The authorization headers dict to validate.

        Returns:
            The validated authorization headers dict.

        Raises:
            ValueError: If any header value is not a supported keyword.
        """
        if value is None:
            return value
        allowed = {MCP_AUTH_CLIENT, MCP_AUTH_KUBERNETES, MCP_AUTH_OAUTH}
        for header_name, header_value in value.items():
            stripped = header_value.strip()
            if stripped not in allowed:
                raise ValueError(
                    f"Authorization header '{header_name}' has unsupported value "
                    f"'{stripped}'. Dynamic registration only supports: "
                    f"{', '.join(sorted(allowed))}. "
                    "File-path based secrets are only supported in static YAML config."
                )
        return value
