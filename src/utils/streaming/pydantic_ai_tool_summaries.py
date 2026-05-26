"""Tool call/result summary builders for pydantic-ai streaming dispatch."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any, Optional, cast

from openai.types.responses.response_file_search_tool_call import (
    Result as OpenAIFileSearchResult,
)
from pydantic import AnyUrl
from pydantic_ai import ModelResponse, ModelResponsePart
from pydantic_ai.messages import (
    ModelMessage,
    NativeToolCallPart,
    NativeToolReturnPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.native_tools import FileSearchTool, MCPServerTool, WebSearchTool

from constants import DEFAULT_RAG_TOOL
from models.common.turn_summary import (
    MCPListToolsSummary,
    RAGChunk,
    ReferencedDocument,
    ToolCallSummary,
    ToolInfoSummary,
    ToolResultSummary,
)

_MCP_PREFIX = f"{MCPServerTool.kind}:"
_FILE_SEARCH_URL_KEYS = ("doc_url", "docs_url", "url", "link")


def function_tool_call_summary(part: ToolCallPart) -> ToolCallSummary:
    """Builds a tool-call summary for a client function tool call.

    Args:
        part: Function tool call part emitted by the agent.

    Returns:
        Tool call summary in LCS turn-summary format.
    """
    return ToolCallSummary(
        id=part.tool_call_id,
        name=part.tool_name,
        args=part.args_as_dict(),
        type="function_call",
    )


def tool_call_summary(
    part: NativeToolCallPart,
) -> Optional[ToolCallSummary]:
    """Builds a tool-call summary for a native pydantic-ai tool call.

    Args:
        part: Native tool call part emitted by the model.

    Returns:
        Tool call summary when the native call is supported, otherwise None.
    """
    call_id = part.tool_call_id
    args = part.args_as_dict()
    if part.tool_name == WebSearchTool.kind:
        return ToolCallSummary(
            id=call_id,
            name=part.tool_name,
            args=args,
            type="web_search_call",
        )
    if part.tool_name == FileSearchTool.kind:
        return ToolCallSummary(
            id=call_id,
            name=DEFAULT_RAG_TOOL,
            args=args,
            type="file_search_call",
        )

    label = part.tool_name.removeprefix(_MCP_PREFIX)
    action = args.get("action")
    # MCP list tools
    if action == "list_tools":
        return ToolCallSummary(
            id=call_id,
            name="mcp_list_tools",
            args={"server_label": label},
            type="mcp_list_tools",
        )

    # MCP call
    summary_args = dict(args["tool_args"])
    return ToolCallSummary(
        id=call_id,
        name=args["tool_name"],
        args=summary_args,
        type="mcp_call",
    )


def function_tool_result_summary(
    part: ToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Builds a tool-result summary for a client function tool return.

    Args:
        part: Function tool return part emitted by the agent.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    return ToolResultSummary(
        id=part.tool_call_id,
        status="success",
        content=part.model_response_str(),
        type="function_call_output",
        round=tool_round,
    )


def tool_result_summary(
    part: NativeToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Builds a tool-result summary for a native Open Responses tool return.

    Args:
        part: Native tool return part emitted by the model.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    content = cast(dict[str, Any], part.content)
    call_id = part.tool_call_id
    type = part.tool_name

    if type in (WebSearchTool.kind, FileSearchTool.kind):
        status = str(content.pop("status"))
        return ToolResultSummary(
            id=call_id,
            status=status,
            content=json.dumps(content) if content else "",
            type=type + "_call",
            round=tool_round,
        )

    label = part.tool_name.removeprefix(_MCP_PREFIX)
    # MCP list tools
    if "tools" in content or "error" in content:
        if content.get("error") is not None:
            return ToolResultSummary(
                id=call_id,
                status="failure",
                content="",
                type="mcp_list_tools",
                round=tool_round,
            )

        list_summary = MCPListToolsSummary(
            server_label=label,
            tools=[ToolInfoSummary.model_validate(tool) for tool in content["tools"]],
        )
        return ToolResultSummary(
            id=call_id,
            status="success",
            content=json.dumps(list_summary.model_dump()),
            type="mcp_list_tools",
            round=tool_round,
        )

    # MCP call
    if (error := content.get("error")) is not None:
        return ToolResultSummary(
            id=call_id,
            status="failure",
            content=str(error),
            type="mcp_call",
            round=tool_round,
        )

    output = content.get("output", "")
    return ToolResultSummary(
        id=call_id,
        status="success",
        content=str(output),
        type="mcp_call",
        round=tool_round,
    )


def parse_tool_referenced_documents_from_agent_messages(
    messages: Sequence[ModelMessage],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> list[ReferencedDocument]:
    """Parses referenced documents from native file-search returns in messages.

    Args:
        messages: Agent messages produced during the run.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Deduplicated referenced documents extracted from file-search results.
    """
    documents: list[ReferencedDocument] = []
    seen_docs: set[tuple[str, str]] = set()

    vs_ids = vector_store_ids or []
    id_mapping = rag_id_mapping or {}

    for result in openai_file_search_results_iterator(messages):
        doc = _referenced_document_from_file_search_result(result, vs_ids, id_mapping)
        if doc is None:
            continue

        dedup_key = (
            str(doc.doc_url) if doc.doc_url else "",
            doc.doc_title or "",
        )
        if dedup_key in seen_docs:
            continue

        seen_docs.add(dedup_key)
        documents.append(doc)

    return documents


def parse_tool_rag_chunks_from_agent_messages(
    messages: Sequence[ModelMessage],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> list[RAGChunk]:
    """Extracts RAG chunks from native file-search returns in messages.

    Args:
        messages: Agent messages produced during the run.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        RAG chunks extracted from file-search result rows.
    """
    vs_ids = vector_store_ids or []
    id_mapping = rag_id_mapping or {}
    rag_chunks: list[RAGChunk] = []
    for result in openai_file_search_results_iterator(messages):
        if not result.text:
            continue
        rag_chunks.append(
            RAGChunk(
                content=result.text,
                source=_resolve_source_for_result(result, vs_ids, id_mapping),
                score=result.score,
                attributes=result.attributes or None,
            )
        )
    return rag_chunks


def _referenced_document_from_file_search_result(
    result: OpenAIFileSearchResult,
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> Optional[ReferencedDocument]:
    """Builds one referenced document from a single file-search result row.

    Args:
        result: OpenAI file-search result row.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Referenced document when metadata is present, otherwise None.
    """
    attributes = result.attributes or {}

    doc_url = _file_search_attribute_url(attributes)
    doc_title = _file_search_attribute_str(attributes, "title")
    if not (doc_title or doc_url):
        return None

    doc_id = _file_search_attribute_str(
        attributes, "document_id"
    ) or _file_search_attribute_str(attributes, "doc_id")
    return ReferencedDocument(
        doc_url=AnyUrl(doc_url) if doc_url else None,
        doc_title=doc_title,
        source=_resolve_source_for_result(result, vector_store_ids, rag_id_mapping),
        document_id=doc_id,
    )


def _file_search_attribute_url(
    attributes: dict[str, str | float | bool],
) -> Optional[str]:
    """Extracts the first available document URL from file-search attributes.

    Args:
        attributes: File-search result metadata attributes.

    Returns:
        First matching URL value as a string, or None.
    """
    return next(
        (str(value) for key in _FILE_SEARCH_URL_KEYS if (value := attributes.get(key))),
        None,
    )


def _file_search_attribute_str(
    attributes: dict[str, str | float | bool],
    key: str,
) -> Optional[str]:
    """Reads a non-empty string metadata field from file-search attributes.

    Args:
        attributes: File-search result metadata attributes.
        key: Metadata key to read.

    Returns:
        Non-empty string value for the key, or None.
    """
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None


def openai_file_search_results_iterator(
    messages: Sequence[ModelMessage],
) -> Iterator[OpenAIFileSearchResult]:
    """Yields OpenAI file-search result rows from agent response messages.

    Args:
        messages: Agent messages to scan for native file-search returns.

    Yields:
        Validated OpenAI file-search result rows.
    """
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not is_file_search_part(part):
                continue
            part = cast(NativeToolReturnPart, part)
            content = cast(dict[str, Any], part.content)
            for result in content.get("results", []):
                yield OpenAIFileSearchResult.model_validate(result)


def is_file_search_part(part: ModelResponsePart) -> bool:
    """Returns whether a part is a native file-search tool return.

    Args:
        part: Model response part to inspect.

    Returns:
        True when the part is a native file-search return part.
    """
    return (
        isinstance(part, NativeToolReturnPart) and part.tool_name == FileSearchTool.kind
    )


def _resolve_source_for_result(
    result: OpenAIFileSearchResult,
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> Optional[str]:
    """Resolves a human-friendly source name for a file-search result.

    Args:
        result: OpenAI file-search result row.
        vector_store_ids: Vector store IDs used in the request.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Resolved source label for the result, or None.
    """
    if not vector_store_ids:
        return None

    # Single vector store → direct mapping
    if len(vector_store_ids) == 1:
        store_id = vector_store_ids[0]
        return rag_id_mapping.get(store_id, store_id)

    # Multi-store → try result metadata first, then fallback to first store
    attributes = result.attributes or {}

    source = attributes.get("source")
    if isinstance(source, str) and source:
        return source

    vector_store_id = attributes.get("vector_store_id")
    if isinstance(vector_store_id, str) and vector_store_id:
        return rag_id_mapping.get(vector_store_id, vector_store_id)

    # fallback: first store (keeps behavior deterministic)
    fallback_store_id = vector_store_ids[0]
    return rag_id_mapping.get(fallback_store_id, fallback_store_id)
