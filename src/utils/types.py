"""Common types for the project."""

from typing import Any, Optional
import json
from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.lib.agents.tool_parser import ToolParser
from llama_stack_client.types.shared.completion_message import CompletionMessage
from llama_stack_client.types.shared.tool_call import ToolCall
from llama_stack_client.types.tool_execution_step import ToolExecutionStep
from constants import DEFAULT_RAG_TOOL
from pydantic import BaseModel
from models.responses import RAGChunk, Field


class Singleton(type):
    """Metaclass for Singleton support."""

    _instances = {}  # type: ignore

    def __call__(cls, *args, **kwargs):  # type: ignore
        """Ensure a single instance is created."""
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


# See https://github.com/meta-llama/llama-stack-client-python/issues/206
class GraniteToolParser(ToolParser):
    """Workaround for 'tool_calls' with granite models."""

    def get_tool_calls(self, output_message: CompletionMessage) -> list[ToolCall]:
        """Use 'tool_calls' associated with the CompletionMessage, if available."""
        if output_message and output_message.tool_calls:
            return output_message.tool_calls
        return []

    @staticmethod
    def get_parser(model_id: str) -> Optional[ToolParser]:
        """Get the applicable ToolParser for the model."""
        if model_id and model_id.lower().startswith("granite"):
            return GraniteToolParser()
        return None


class ToolCallSummary(BaseModel):
    """Represents a tool call for data collection.

    Use our own tool call model to keep things consistent across llama
    upgrades or if we used something besides llama in the future.
    """

    # ID of the call itself
    id: str
    # Name of the tool used
    name: str
    # Arguments to the tool call
    args: str | dict[Any, Any]
    response: str | None




class TurnSummary(BaseModel):
    """Summary of a turn in llama stack."""

    llm_response: str
    tool_calls: list[ToolCallSummary]
    rag_chunks: list[RAGChunk] = []

    def append_tool_calls_from_llama(self, tec: ToolExecutionStep) -> None:
        """Append the tool calls from a llama tool execution step."""
        calls_by_id = {tc.call_id: tc for tc in tec.tool_calls}
        responses_by_id = {tc.call_id: tc for tc in tec.tool_responses}
        for call_id, tc in calls_by_id.items():
            resp = responses_by_id.get(call_id)
            response_content = interleaved_content_as_str(resp.content) if resp else None
            
            self.tool_calls.append(
                ToolCallSummary(
                    id=call_id,
                    name=tc.tool_name,
                    args=tc.arguments,
                    response=response_content,
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
                                score=chunk.get("score")
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
                                    score=chunk.get("score")
                                )
                            )
            except json.JSONDecodeError:
                # If not JSON, treat the entire response as a single chunk
                if response_content.strip():
                    self.rag_chunks.append(
                        RAGChunk(
                            content=response_content,
                            source=DEFAULT_RAG_TOOL,
                            score=None
                        )
                    )
        except Exception:
            # Treat response as single chunk
            if response_content.strip():
                self.rag_chunks.append(
                    RAGChunk(
                        content=response_content,
                        source=DEFAULT_RAG_TOOL,
                        score=None
                    )
                )
