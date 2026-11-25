"""Tools the model may call, and how it should choose among them."""

from enum import StrEnum
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field


class InputToolFunction(BaseModel):
    """Function the model can ask the client to run."""

    type: Literal["function"] = "function"
    name: str
    description: Optional[str] = None
    parameters: Optional[dict[str, Any]]
    strict: Optional[bool] = None


class InputToolFileSearch(BaseModel):
    """Search over vector stores attached to the request."""

    type: Literal["file_search"] = "file_search"
    vector_store_ids: list[str]
    max_num_results: Optional[int] = Field(default=10, ge=1, le=50)


class ApprovalFilter(BaseModel):
    """MCP tools that always or never need human approval."""

    always: Optional[list[str]] = None
    never: Optional[list[str]] = None


class AllowedToolsFilter(BaseModel):
    """MCP tools the model is allowed to use."""

    tool_names: Optional[list[str]] = None


class InputToolMCP(BaseModel):
    """Remote MCP server the model may call.

    Authorization is sent on the request so Lightspeed can authenticate to the
    server.
    """

    type: Literal["mcp"] = "mcp"
    server_label: str
    server_url: str
    headers: Optional[dict[str, Any]] = None
    authorization: Optional[str] = None
    require_approval: Literal["always", "never"] | ApprovalFilter = "never"
    allowed_tools: Optional[list[str] | AllowedToolsFilter] = None


InputTool = Annotated[
    InputToolFileSearch | InputToolFunction | InputToolMCP,
    Field(discriminator="type"),
]


class OutputToolMCP(BaseModel):
    """MCP server echoed on a response, without connection secrets."""

    type: Literal["mcp"] = "mcp"
    server_label: str
    allowed_tools: Optional[list[str] | AllowedToolsFilter] = None


OutputTool = Annotated[
    InputToolFileSearch | InputToolFunction | OutputToolMCP,
    Field(discriminator="type"),
]


class ToolChoiceAllowedTools(BaseModel):
    """Limit the model to a listed set of tools."""

    type: Literal["allowed_tools"] = "allowed_tools"
    mode: Literal["auto", "required"] = "auto"
    tools: list[dict[str, Any]]


class ToolChoiceFileSearch(BaseModel):
    """Require the model to use file search."""

    type: Literal["file_search"] = "file_search"


class ToolChoiceFunction(BaseModel):
    """Require the model to call a named function."""

    type: Literal["function"] = "function"
    name: str


class ToolChoiceMCP(BaseModel):
    """Require the model to call an MCP tool."""

    type: Literal["mcp"] = "mcp"
    server_label: str
    name: Optional[str] = None


class ToolChoiceMode(StrEnum):
    """Whether the model may, must, or must not call tools."""

    AUTO = "auto"
    REQUIRED = "required"
    NONE = "none"


ToolChoiceObject = Annotated[
    ToolChoiceAllowedTools | ToolChoiceFileSearch | ToolChoiceFunction | ToolChoiceMCP,
    Field(discriminator="type"),
]

type ToolChoice = ToolChoiceMode | ToolChoiceObject
