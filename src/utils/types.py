"""Common types for the project."""

import ast
import json
import logging
import re
from typing import Any, Optional

from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.lib.agents.tool_parser import ToolParser
from llama_stack_client.types.shared.completion_message import CompletionMessage
from llama_stack_client.types.shared.tool_call import ToolCall
from llama_stack_client.types.tool_execution_step import ToolExecutionStep
from pydantic import BaseModel

from constants import DEFAULT_RAG_TOOL
from models.responses import RAGChunk

logger = logging.getLogger(__name__)

# Pattern to match individual RAG result blocks: " Result N\nContent: ..."
# Captures result number and everything until the next result or end marker
RAG_RESULT_PATTERN = re.compile(
    r"\s*Result\s+(\d+)\s*\nContent:\s*(.*?)(?=\s*Result\s+\d+\s*\n|END of knowledge_search)",
    re.DOTALL,
)

# Pattern to extract metadata dict from a result block
RAG_METADATA_PATTERN = re.compile(r"Metadata:\s*(\{[^}]+\})", re.DOTALL)


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

    def get_tool_calls(self, output_message: CompletionMessage) -> list[ToolCall]:
        """
        Return the `tool_calls` list from a CompletionMessage, or an empty list if none are present.

        Parameters:
            output_message (CompletionMessage | None): Completion
            message potentially containing `tool_calls`.

        Returns:
            list[ToolCall]: The list of tool call entries
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
            response_content = (
                interleaved_content_as_str(resp.content) if resp else None
            )

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
        """Extract RAG chunks from tool response content.

        Parses RAG tool responses in multiple formats:
        1. JSON format with "chunks" array or list of chunk objects
        2. Formatted text with "Result N" blocks containing Content and Metadata

        For formatted text responses, extracts:
        - Content text for each result
        - Metadata including docs_url, title, chunk_id, document_id
        """
        if not response_content or not response_content.strip():
            return

        # Try JSON format first
        if self._try_parse_json_chunks(response_content):
            return

        # Try formatted text with "Result N" blocks
        if self._try_parse_formatted_chunks(response_content):
            return

        # Fallback: treat entire response as single chunk
        # This may indicate the RAG response format has changed
        logger.warning(
            "Unable to parse individual RAG chunks from response. "
            "Falling back to single-chunk extraction. "
            "This may indicate a change in the RAG tool response format. "
            "Response preview: %.200s...",
            response_content[:200] if len(response_content) > 200 else response_content,
        )
        self.rag_chunks.append(
            RAGChunk(
                content=response_content,
                source=DEFAULT_RAG_TOOL,
                score=None,
            )
        )

    def _try_parse_json_chunks(self, response_content: str) -> bool:
        """Try to parse response as JSON chunks.

        Returns True if successfully parsed, False otherwise.
        """
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
                return True
            if isinstance(data, list):
                for chunk in data:
                    if isinstance(chunk, dict):
                        self.rag_chunks.append(
                            RAGChunk(
                                content=chunk.get("content", str(chunk)),
                                source=chunk.get("source"),
                                score=chunk.get("score"),
                            )
                        )
                return bool(data)
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError, ValueError):
            pass
        return False

    def _try_parse_formatted_chunks(self, response_content: str) -> bool:
        """Try to parse formatted text response with 'Result N' blocks.

        Parses responses in format:
            knowledge_search tool found N chunks:
            BEGIN of knowledge_search tool results.
             Result 1
            Content: <text>
            Metadata: {'chunk_id': '...', 'docs_url': '...', 'title': '...', ...}
             Result 2
            ...
            END of knowledge_search tool results.

        Returns True if at least one chunk was parsed, False otherwise.
        """
        # Check if this looks like a formatted RAG response
        if "Result" not in response_content or "Content:" not in response_content:
            return False

        matches = RAG_RESULT_PATTERN.findall(response_content)
        if not matches:
            return False

        for _result_num, content_block in matches:
            chunk = self._parse_single_chunk(content_block)
            if chunk:
                self.rag_chunks.append(chunk)

        return bool(self.rag_chunks)

    def _parse_single_chunk(self, content_block: str) -> RAGChunk | None:
        """Parse a single chunk from a content block.

        Args:
            content_block: Text containing content and optionally metadata

        Returns:
            RAGChunk if successfully parsed, None otherwise
        """
        # Extract metadata if present
        metadata: dict[str, Any] = {}
        metadata_match = RAG_METADATA_PATTERN.search(content_block)
        if metadata_match:
            try:
                metadata = ast.literal_eval(metadata_match.group(1))
            except (ValueError, SyntaxError) as e:
                logger.debug("Failed to parse chunk metadata: %s", e)

        # Extract content (everything before "Metadata:" if present)
        if metadata_match:
            content = content_block[: metadata_match.start()].strip()
        else:
            content = content_block.strip()

        if not content:
            return None

        return RAGChunk(
            content=content,
            source=metadata.get("docs_url") or metadata.get("source"),
            score=metadata.get("score"),
        )
