"""Common types for the project."""

from typing import Any, Literal, Optional, TypeAlias

from llama_stack_api import ImageContentItem, TextContentItem
from llama_stack_api.openai_responses import (
    OpenAIResponseInputFunctionToolCallOutput as FunctionToolCallOutput,
    OpenAIResponseMCPApprovalRequest as McpApprovalRequest,
    OpenAIResponseMCPApprovalResponse as McpApprovalResponse,
    OpenAIResponseMessage as ResponseMessage,
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchToolCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionToolCall,
    OpenAIResponseOutputMessageMCPCall as McpCall,
    OpenAIResponseOutputMessageMCPListTools as McpListTools,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchToolCall,
)
from llama_stack_client.lib.agents.tool_parser import ToolParser
from llama_stack_client.lib.agents.types import (
    CompletionMessage as AgentCompletionMessage,
)
from llama_stack_client.lib.agents.types import (
    ToolCall as AgentToolCall,
)
from pydantic import AnyUrl, BaseModel, Field

from utils.token_counter import TokenCounter


def content_to_str(content: Any) -> str:
    """Convert content (str, TextContentItem, ImageContentItem, or list) to string.

    Parameters:
        content: Value to normalize into a string (may be None,
                 str, content item, list, or any other object).

    Returns:
        str: The normalized string representation of the content.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, TextContentItem):
        return content.text
    if isinstance(content, ImageContentItem):
        return "<image>"
    if isinstance(content, list):
        return " ".join(content_to_str(item) for item in content)
    return str(content)


class Singleton(type):
    """Metaclass for Singleton support."""

    _instances = {}  # type: ignore

    def __call__(cls, *args, **kwargs):  # type: ignore
        """
        Return the single cached instance of the class, creating and caching it on first call.

        Returns:
            object: The singleton instance for this class.
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


# See https://github.com/meta-llama/llama-stack-client-python/issues/206
class GraniteToolParser(ToolParser):
    """Workaround for 'tool_calls' with granite models."""

    def get_tool_calls(
        self, output_message: AgentCompletionMessage
    ) -> list[AgentToolCall]:
        """
        Return the `tool_calls` list from a CompletionMessage, or an empty list if none are present.

        Parameters:
            output_message (Optional[AgentCompletionMessage]): Completion
            message potentially containing `tool_calls`.

        Returns:
            list[AgentToolCall]: The list of tool call entries
            extracted from `output_message`, or an empty list.
        """
        if output_message and output_message.tool_calls:
            return output_message.tool_calls
        return []

    @staticmethod
    def get_parser(model_id: str) -> Optional[ToolParser]:
        """
        Return a GraniteToolParser when the model identifier denotes a Granite model.

        Returns None otherwise.

        Parameters:
            model_id (str): Model identifier string checked case-insensitively.
            If it starts with "granite", a GraniteToolParser instance is
            returned.

        Returns:
            Optional[ToolParser]: GraniteToolParser for Granite models, or None
            if `model_id` is falsy or does not start with "granite".
        """
        if model_id and model_id.lower().startswith("granite"):
            return GraniteToolParser()
        return None


class ShieldModerationResult(BaseModel):
    """Result of shield moderation check."""

    blocked: bool
    message: Optional[str] = None
    shield_model: Optional[str] = None


class ResponsesApiParams(BaseModel):
    """Parameters for a Llama Stack Responses API request."""

    input: str = Field(description="The input text with attachments appended")
    model: str = Field(description='The full model ID in format "provider/model"')
    instructions: Optional[str] = Field(
        default=None, description="The resolved system prompt"
    )
    tools: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Prepared tool groups for Responses API"
    )
    conversation: str = Field(description="The conversation ID in llama-stack format")
    stream: bool = Field(description="Whether to stream the response")
    store: bool = Field(description="Whether to store the response")
    extra_headers: Optional[dict[str, str]] = Field(
        default=None,
        description="Extra HTTP headers to send with the request (e.g. x-llamastack-provider-data)",
    )


class ToolCallSummary(BaseModel):
    """Model representing a tool call made during response generation (for tool_calls list)."""

    id: str = Field(description="ID of the tool call")
    name: str = Field(description="Name of the tool called")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the tool"
    )
    type: str = Field("tool_call", description="Type indicator for tool call")


class ToolResultSummary(BaseModel):
    """Model representing a result from a tool call (for tool_results list)."""

    id: str = Field(
        description="ID of the tool call/result, matches the corresponding tool call 'id'"
    )
    status: str = Field(
        ..., description="Status of the tool execution (e.g., 'success')"
    )
    content: str = Field(..., description="Content/result returned from the tool")
    type: str = Field("tool_result", description="Type indicator for tool result")
    round: int = Field(..., description="Round number or step of tool execution")


class RAGChunk(BaseModel):
    """Model representing a RAG chunk used in the response."""

    content: str = Field(description="The content of the chunk")
    source: Optional[str] = Field(
        default=None,
        description="Index name identifying the knowledge source from configuration",
    )
    score: Optional[float] = Field(default=None, description="Relevance score")
    attributes: Optional[dict[str, Any]] = Field(
        default=None,
        description="Document metadata from the RAG provider (e.g., url, title, author)",
    )


class ReferencedDocument(BaseModel):
    """Model representing a document referenced in generating a response.

    Attributes:
        doc_url: Url to the referenced doc.
        doc_title: Title of the referenced doc.
    """

    doc_url: Optional[AnyUrl] = Field(
        default=None, description="URL of the referenced document"
    )

    doc_title: Optional[str] = Field(
        default=None, description="Title of the referenced document"
    )

    source: Optional[str] = Field(
        default=None,
        description="Index name identifying the knowledge source from configuration",
    )


class TurnSummary(BaseModel):
    """Summary of a turn in llama stack."""

    llm_response: str = ""
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    tool_results: list[ToolResultSummary] = Field(default_factory=list)
    rag_chunks: list[RAGChunk] = Field(default_factory=list)
    referenced_documents: list[ReferencedDocument] = Field(default_factory=list)
    pre_rag_documents: list[ReferencedDocument] = Field(default_factory=list)
    token_usage: TokenCounter = Field(default_factory=TokenCounter)


class TranscriptMetadata(BaseModel):
    """Metadata for a transcript entry."""

    provider: str | None = None
    model: str
    query_provider: str | None = None
    query_model: str | None = None
    user_id: str
    conversation_id: str
    timestamp: str


class Transcript(BaseModel):
    """Model representing a transcript entry to be stored."""

    metadata: TranscriptMetadata
    redacted_query: str
    query_is_valid: bool
    llm_response: str
    rag_chunks: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)


ResponseInputItem: TypeAlias = (
    ResponseMessage
    | WebSearchToolCall
    | FileSearchToolCall
    | FunctionToolCallOutput
    | McpCall
    | McpListTools
    | McpApprovalRequest
    | FunctionToolCall
    | McpApprovalResponse
)

ResponseInput: TypeAlias = str | list[ResponseInputItem]

IncludeParameter: TypeAlias = Literal[
    "web_search_call.action.sources",
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
    "reasoning.encrypted_content",
]
