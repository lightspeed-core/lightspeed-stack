"""Type definitions for Responses API input/output structures.

This module mirrors the type structure from llama_stack_client.types.response_create_params
to provide strongly typed models for the LCORE Responses API.
"""

from typing import Dict, Iterable, List, Literal, Optional, Union
from typing_extensions import Required, TypeAlias, TypedDict


# Content item types for message input
class InputMessageContentText(TypedDict, total=False):
    """Text content for input messages in OpenAI response format."""

    text: Required[str]
    type: Literal["input_text"]


class InputMessageContentImage(TypedDict, total=False):
    """Image content for input messages in OpenAI response format."""

    detail: Literal["low", "high", "auto"]
    file_id: Optional[str]
    image_url: Optional[str]
    type: Literal["input_image"]


class InputMessageContentFile(TypedDict, total=False):
    """File content for input messages in OpenAI response format."""

    file_data: Optional[str]
    file_id: Optional[str]
    file_url: Optional[str]
    filename: Optional[str]
    type: Literal["input_file"]


InputMessageContent: TypeAlias = Union[
    InputMessageContentText,
    InputMessageContentImage,
    InputMessageContentFile,
]


# Annotation types for output text
class OutputTextAnnotationFileCitation(TypedDict, total=False):
    """File citation annotation for referencing specific files in response content."""

    file_id: str
    filename: str
    index: int
    type: Literal["file_citation"]


class OutputTextAnnotationCitation(TypedDict, total=False):
    """URL citation annotation for referencing external web resources."""

    end_index: int
    start_index: int
    title: str
    url: str
    type: Literal["url_citation"]


class OutputTextAnnotationContainerFileCitation(TypedDict, total=False):
    """Container file citation annotation."""

    container_id: str
    end_index: int
    file_id: str
    filename: str
    start_index: int
    type: Literal["container_file_citation"]


class OutputTextAnnotationFilePath(TypedDict, total=False):
    """File path annotation."""

    file_id: str
    index: int
    type: Literal["file_path"]


OutputTextAnnotation: TypeAlias = Union[
    OutputTextAnnotationFileCitation,
    OutputTextAnnotationCitation,
    OutputTextAnnotationContainerFileCitation,
    OutputTextAnnotationFilePath,
]


# Log probability types
class OutputTextLogprobTopLogprob(TypedDict, total=False):
    """The top log probability for a token from an OpenAI-compatible chat completion response."""

    token: str
    logprob: float
    bytes: Optional[Iterable[int]]


class OutputTextLogprob(TypedDict, total=False):
    """The log probability for a token from an OpenAI-compatible chat completion response."""

    token: str
    logprob: float
    bytes: Optional[Iterable[int]]
    top_logprobs: Optional[Iterable[OutputTextLogprobTopLogprob]]


# Output text content types
class OutputTextContent(TypedDict, total=False):
    """Output text content with annotations and logprobs."""

    text: Required[str]
    annotations: Optional[Iterable[OutputTextAnnotation]]
    logprobs: Optional[Iterable[OutputTextLogprob]]
    type: Literal["output_text"]


class RefusalContent(TypedDict, total=False):
    """Refusal content within a streamed response part."""

    refusal: Required[str]
    type: Literal["refusal"]


OutputMessageContent: TypeAlias = Union[
    OutputTextContent,
    RefusalContent,
]


# Message input type
class MessageInput(TypedDict, total=False):
    """
    Message input type for Responses API.
    
    Corresponds to the various Message types in the Responses API.
    They are all under one type because the Responses API gives them all
    the same "type" value, and there is no way to tell them apart in certain
    scenarios.
    """

    content: Required[
        Union[
            str,
            Iterable[InputMessageContent],
            Iterable[OutputMessageContent],
        ]
    ]
    role: Required[Literal["system", "developer", "user", "assistant"]]
    id: Optional[str]
    status: Optional[str]
    type: Literal["message"]


# Tool call output types
class WebSearchToolCall(TypedDict, total=False):
    """Web search tool call output message for OpenAI responses."""

    id: Required[str]
    status: Required[str]
    type: Literal["web_search_call"]


class FileSearchToolCallResult(TypedDict, total=False):
    """Search results returned by the file search operation."""

    attributes: Required[Dict[str, object]]
    file_id: Required[str]
    filename: Required[str]
    score: Required[float]
    text: Required[str]


class FileSearchToolCall(TypedDict, total=False):
    """File search tool call output message for OpenAI responses."""

    id: Required[str]
    queries: Required[List[str]]
    status: Required[str]
    results: Optional[Iterable[FileSearchToolCallResult]]
    type: Literal["file_search_call"]


class FunctionToolCall(TypedDict, total=False):
    """Function tool call output message for OpenAI responses."""

    arguments: Required[str]
    call_id: Required[str]
    name: Required[str]
    id: Optional[str]
    status: Optional[str]
    type: Literal["function_call"]


class McpCall(TypedDict, total=False):
    """Model Context Protocol (MCP) call output message for OpenAI responses."""

    id: Required[str]
    arguments: Required[str]
    name: Optional[str]
    server_label: Optional[str]
    status: Optional[str]
    type: Literal["mcp_call"]


class McpListToolsTool(TypedDict, total=False):
    """Tool definition returned by MCP list tools operation."""

    input_schema: Dict[str, object]
    name: str


class McpListTools(TypedDict, total=False):
    """MCP list tools output message containing available tools from an MCP server."""

    id: Required[str]
    server_label: Required[str]
    tools: Optional[Iterable[McpListToolsTool]]
    type: Literal["mcp_list_tools"]


class McpApprovalRequest(TypedDict, total=False):
    """A request for human approval of a tool invocation."""

    id: Required[str]
    arguments: Required[str]
    name: Optional[str]
    reason: Optional[str]
    server_label: Optional[str]
    type: Literal["mcp_approval_request"]


class FunctionToolCallOutput(TypedDict, total=False):
    """Function tool call output."""

    call_id: Required[str]
    name: Required[str]
    output: Optional[str]
    type: Literal["function_call_output"]


class McpApprovalResponse(TypedDict, total=False):
    """Response to an MCP approval request."""

    id: Optional[str]
    reason: Optional[str]
    type: Literal["mcp_approval_response"]


# Union type for all input items
ResponseInputItem: TypeAlias = Union[
    MessageInput,
    WebSearchToolCall,
    FileSearchToolCall,
    FunctionToolCall,
    McpCall,
    McpListTools,
    McpApprovalRequest,
    FunctionToolCallOutput,
    McpApprovalResponse,
]


# Main input type - matches llama_stack_client signature
ResponseInput: TypeAlias = Union[
    str,
    Iterable[ResponseInputItem],
]


# Prompt variables types
class PromptVariablesText(TypedDict, total=False):
    """Text content for prompt variables."""

    text: Required[str]
    type: Literal["input_text"]


class PromptVariablesImage(TypedDict, total=False):
    """Image content for prompt variables."""

    detail: Literal["low", "high", "auto"]
    file_id: Optional[str]
    image_url: Optional[str]
    type: Literal["input_image"]


class PromptVariablesFile(TypedDict, total=False):
    """File content for prompt variables."""

    file_data: Optional[str]
    file_id: Optional[str]
    file_url: Optional[str]
    filename: Optional[str]
    type: Literal["input_file"]


PromptVariables: TypeAlias = Union[
    PromptVariablesText,
    PromptVariablesImage,
    PromptVariablesFile,
]


# Prompt type
class Prompt(TypedDict, total=False):
    """OpenAI compatible Prompt object that is used in OpenAI responses."""

    id: Required[str]
    variables: Optional[Dict[str, PromptVariables]]
    version: Optional[str]


# Text format and text types
class TextFormat(TypedDict, total=False):
    """Configuration for Responses API text format."""

    description: Optional[str]
    name: Optional[str]
    schema: Optional[Dict[str, object]]
    strict: Optional[bool]
    type: Literal["text", "json_schema", "json_object"]


class Text(TypedDict, total=False):
    """Text response configuration for OpenAI responses."""

    format: Optional[TextFormat]


# Tool choice types
class ToolChoiceAllowedTools(TypedDict, total=False):
    """Constrains the tools available to the model to a pre-defined set."""

    tools: Required[Iterable[Dict[str, str]]]
    mode: Literal["auto", "required"]
    type: Literal["allowed_tools"]


class ToolChoiceFileSearch(TypedDict, total=False):
    """Indicates that the model should use file search to generate a response."""

    type: Literal["file_search"]


class ToolChoiceWebSearch(TypedDict, total=False):
    """Indicates that the model should use web search to generate a response."""

    type: Literal[
        "web_search",
        "web_search_preview",
        "web_search_preview_2025_03_11",
        "web_search_2025_08_26",
    ]


class ToolChoiceFunctionTool(TypedDict, total=False):
    """Forces the model to call a specific function."""

    name: Required[str]
    type: Literal["function"]


class ToolChoiceMcpTool(TypedDict, total=False):
    """Forces the model to call a specific tool on a remote MCP server."""

    server_label: Required[str]
    name: Optional[str]
    type: Literal["mcp"]


class ToolChoiceCustomTool(TypedDict, total=False):
    """Forces the model to call a custom tool."""

    name: Required[str]
    type: Literal["custom"]


ToolChoice: TypeAlias = Union[
    Literal["auto", "required", "none"],
    ToolChoiceAllowedTools,
    ToolChoiceFileSearch,
    ToolChoiceWebSearch,
    ToolChoiceFunctionTool,
    ToolChoiceMcpTool,
    ToolChoiceCustomTool,
]


# Tool types
class ToolWebSearch(TypedDict, total=False):
    """Web search tool configuration for OpenAI response inputs."""

    search_context_size: Optional[str]
    type: Literal[
        "web_search",
        "web_search_preview",
        "web_search_preview_2025_03_11",
        "web_search_2025_08_26",
    ]


class ToolFileSearchRankingOptions(TypedDict, total=False):
    """Options for ranking and filtering search results."""

    ranker: Optional[str]
    score_threshold: Optional[float]


class ToolFileSearch(TypedDict, total=False):
    """File search tool configuration for OpenAI response inputs."""

    vector_store_ids: Required[List[str]]
    filters: Optional[Dict[str, object]]
    max_num_results: Optional[int]
    ranking_options: Optional[ToolFileSearchRankingOptions]
    type: Literal["file_search"]


class ToolFunction(TypedDict, total=False):
    """Function tool configuration for OpenAI response inputs."""

    name: Required[str]
    parameters: Required[Optional[Dict[str, object]]]
    description: Optional[str]
    strict: Optional[bool]
    type: Literal["function"]


class ToolMcpAllowedToolsFilter(TypedDict, total=False):
    """Filter configuration for restricting which MCP tools can be used."""

    tool_names: Optional[List[str]]


ToolMcpAllowedTools: TypeAlias = Union[List[str], ToolMcpAllowedToolsFilter]


class ToolMcpRequireApprovalFilter(TypedDict, total=False):
    """Filter configuration for MCP tool approval requirements."""

    always: Optional[List[str]]
    never: Optional[List[str]]


ToolMcpRequireApproval: TypeAlias = Union[
    Literal["always", "never"], ToolMcpRequireApprovalFilter
]


class ToolMcp(TypedDict, total=False):
    """Model Context Protocol (MCP) tool configuration for OpenAI response inputs."""

    server_label: Required[str]
    server_url: Required[str]
    allowed_tools: Optional[ToolMcpAllowedTools]
    authorization: Optional[str]
    headers: Optional[Dict[str, object]]
    require_approval: ToolMcpRequireApproval
    type: Literal["mcp"]


Tool: TypeAlias = Union[
    ToolWebSearch,
    ToolFileSearch,
    ToolFunction,
    ToolMcp,
]


# Include parameter type
IncludeParameter: TypeAlias = Literal[
    "web_search_call.action.sources",
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
    "reasoning.encrypted_content",
]
