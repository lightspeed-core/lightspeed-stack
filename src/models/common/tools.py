"""Backend-agnostic tool listing models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ListedMcpTool(BaseModel):
    """Tool metadata returned from an MCP ``tools/list`` call."""

    name: str
    description: Optional[str] = None
    input_schema: Optional[dict[str, Any]] = None


class CatalogToolParameter(BaseModel):
    """Parameter entry for a tool in the ``/tools`` catalog response."""

    name: str
    description: str
    parameter_type: str
    required: bool = False
    default: Optional[Any] = None


class CatalogTool(BaseModel):
    """Tool entry in the ``/tools`` catalog response."""

    identifier: str
    description: str
    parameters: list[CatalogToolParameter]
    provider_id: str
    toolgroup_id: str
    server_source: str
    type: str = "tool"
