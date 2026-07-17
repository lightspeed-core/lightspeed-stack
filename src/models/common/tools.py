"""Backend-agnostic tool listing models."""

from __future__ import annotations

from typing import Any, Optional

from ogx_client import BaseModel as OgxBaseModel
from pydantic import BaseModel, Field


class ToolDef(OgxBaseModel):
    """Tool definition from a tools listing API."""

    name: str
    description: Optional[str] = None
    toolgroup_id: Optional[str] = None
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class ListToolDefsResponse(OgxBaseModel):
    """Response payload for a tools listing API."""

    data: list[ToolDef]


class ListedMcpTool(BaseModel):
    """Tool metadata returned from an MCP ``tools/list`` call."""

    name: str
    description: Optional[str] = None
    input_schema: Optional[dict[str, Any]] = None


class CatalogToolParameter(BaseModel):
    """Parameter entry for a tool in the ``/tools`` catalog response."""

    name: str
    description: str = ""
    parameter_type: str = "string"
    required: bool = False
    default: Optional[Any] = None


class CatalogTool(BaseModel):
    """Tool entry in the ``/tools`` catalog response."""

    identifier: str
    description: str = ""
    parameters: list[CatalogToolParameter] = Field(default_factory=list)
    provider_id: str = ""
    toolgroup_id: str = ""
    server_source: str = ""
    type: str = "tool"
