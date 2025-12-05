"""Common types for the project."""

from typing import Any, Optional
import json
from llama_stack_client.lib.agents.tool_parser import ToolParser
from llama_stack_client.lib.agents.types import (
    CompletionMessage as AgentCompletionMessage,
    ToolCall as AgentToolCall,
)
from llama_stack_client.types.shared.interleaved_content_item import (
    TextContentItem,
    ImageContentItem,
)
from llama_stack_client.types.alpha.tool_execution_step import ToolExecutionStep
from pydantic import BaseModel
from pydantic import Field
from constants import DEFAULT_RAG_TOOL


def content_to_str(content: Any) -> str:
    """Convert content (str, TextContentItem, ImageContentItem, or list) to string.

    Args:
        content: Content to convert to string.

    Returns:
        str: String representation of the content.
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
            output_message (AgentCompletionMessage | None): Completion
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
    content: Any = Field(..., description="Content/result returned from the tool")
    type: str = Field("tool_result", description="Type indicator for tool result")
    round: int = Field(..., description="Round number or step of tool execution")


class RAGChunk(BaseModel):
    """Model representing a RAG chunk used in the response."""

    content: str = Field(description="The content of the chunk")
    source: str | None = Field(None, description="Source document or URL")
    score: float | None = Field(None, description="Relevance score")


class TurnSummary(BaseModel):
    """Summary of a turn in llama stack."""

    llm_response: str
    tool_calls: list[ToolCallSummary]
    tool_results: list[ToolResultSummary]
    rag_chunks: list[RAGChunk]

    def append_tool_calls_from_llama(self, tec: ToolExecutionStep) -> None:
        """Append the tool calls from a llama tool execution step."""
        calls_by_id = {tc.call_id: tc for tc in tec.tool_calls}
        responses_by_id = {tc.call_id: tc for tc in tec.tool_responses}
        for call_id, tc in calls_by_id.items():
            resp = responses_by_id.get(call_id)
            response_content = content_to_str(resp.content) if resp else None

            self.tool_calls.append(
                ToolCallSummary(
                    id=call_id,
                    name=tc.tool_name,
                    args=(
                        tc.arguments
                        if isinstance(tc.arguments, dict)
                        else {"args": str(tc.arguments)}
                    ),
                    type="tool_call",
                )
            )
            self.tool_results.append(
                ToolResultSummary(
                    id=call_id,
                    status="success" if resp else "failure",
                    content=response_content,
                    type="tool_result",
                    round=1,  # clarify meaning of this attribute
                )
            )
            # Extract RAG chunks from knowledge_search tool responses
            if tc.tool_name == DEFAULT_RAG_TOOL and resp and response_content:
                self._extract_rag_chunks_from_response(response_content)

    def _extract_rag_chunks_from_response(self, response_content: str) -> None:
        """Extract RAG chunks from tool response content."""
        try:
            # Parse the response to get chunks
            # Try JSON first
            try:
                data = json.loads(response_content)
                if isinstance(data, dict) and "chunks" in data:
                    for chunk in data["chunks"]:
                        self.rag_chunks.append(
                            RAGChunk(
                                content=chunk.get("content", ""),
                                source=chunk.get("source"),
                                score=chunk.get("score"),
                            )
                        )
                elif isinstance(data, list):
                    # Handle list of chunks
                    for chunk in data:
                        if isinstance(chunk, dict):
                            self.rag_chunks.append(
                                RAGChunk(
                                    content=chunk.get("content", str(chunk)),
                                    source=chunk.get("source"),
                                    score=chunk.get("score"),
                                )
                            )
            except json.JSONDecodeError:
                # If not JSON, treat the entire response as a single chunk
                if response_content.strip():
                    self.rag_chunks.append(
                        RAGChunk(
                            content=response_content,
                            source=DEFAULT_RAG_TOOL,
                            score=None,
                        )
                    )
        except (KeyError, AttributeError, TypeError, ValueError):
            # Treat response as single chunk on data access/structure errors
            if response_content.strip():
                self.rag_chunks.append(
                    RAGChunk(
                        content=response_content, source=DEFAULT_RAG_TOOL, score=None
                    )
                )
