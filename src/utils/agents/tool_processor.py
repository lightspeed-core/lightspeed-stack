"""Process and record pydantic-ai tool parts during agent stream dispatch."""

from __future__ import annotations

import json
from typing import Any, Optional, cast

from openai.types.responses.response_file_search_tool_call import (
    Result as OpenAIFileSearchResult,
)
from pydantic import AnyUrl
from pydantic_ai.messages import (
    NativeToolCallPart,
    NativeToolReturnPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.native_tools import FileSearchTool, MCPServerTool, WebSearchTool

from constants import DEFAULT_RAG_TOOL
from log import get_logger
from models.common.agents import AgentTurnAccumulator
from models.common.turn_summary import (
    MCPListToolsSummary,
    RAGChunk,
    ReferencedDocument,
    ToolCallSummary,
    ToolInfoSummary,
    ToolResultSummary,
)
from utils.responses import resolve_source_for_result

logger = get_logger(__name__)

_FILE_SEARCH_URL_KEYS = ("doc_url", "docs_url", "url", "link", "reference_url")
_MCP_SERVER_TOOL_PREFIX = f"{MCPServerTool.kind}:"


def summarize_function_tool_call(part: ToolCallPart) -> ToolCallSummary:
    """Build a tool-call summary for a client function tool call.

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


def summarize_native_tool_call(
    part: NativeToolCallPart,
) -> Optional[ToolCallSummary]:
    """Build a tool-call summary for a native agent tool call.

    Args:
        part: Native tool call part emitted by the model.

    Returns:
        Tool call summary in LCS turn-summary format.
    """
    call_id = part.tool_call_id
    args = part.args_as_dict()
    match part.tool_name:
        case WebSearchTool.kind:
            return ToolCallSummary(
                id=call_id,
                name=part.tool_name,
                args=args,
                type="web_search_call",
            )
        case FileSearchTool.kind:
            return ToolCallSummary(
                id=call_id,
                name=DEFAULT_RAG_TOOL,
                args=args,
                type="file_search_call",
            )
        case tool_name if tool_name.startswith(_MCP_SERVER_TOOL_PREFIX):
            label = tool_name.removeprefix(_MCP_SERVER_TOOL_PREFIX)
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
            return ToolCallSummary(
                id=call_id,
                name=args.get("tool_name") or "",
                args=args.get("tool_args", {}),
                type="mcp_call",
            )
        case _:
            logger.warning("Unknown tool name: %s", part.tool_name)
            return None


def process_function_tool_call(
    state: AgentTurnAccumulator,
    part: ToolCallPart,
) -> Optional[ToolCallSummary]:
    """Record a client function tool call on dispatch state.

    Args:
        state: Mutable dispatch reducer state.
        part: Function tool call part from the agent.

    Returns:
        Tool call summary when recorded, otherwise None if already emitted.
    """
    if part.tool_call_id in state.emitted_tool_call_ids:
        return None
    summary = summarize_function_tool_call(part)
    state.increment_round_if_pending()
    state.emitted_tool_call_ids.add(summary.id)
    state.turn_summary.tool_calls.append(summary)
    return summary


def process_native_tool_call(
    state: AgentTurnAccumulator,
    part: NativeToolCallPart,
) -> Optional[ToolCallSummary]:
    """Record a native tool call on dispatch state.

    Args:
        state: Mutable dispatch reducer state.
        part: Native tool call part from the model.

    Returns:
        Tool call summary when recorded, otherwise None if already emitted.
    """
    if part.tool_call_id in state.emitted_tool_call_ids:
        return None
    if summary := summarize_native_tool_call(part):
        state.increment_round_if_pending()
        state.emitted_tool_call_ids.add(summary.id)
        state.turn_summary.tool_calls.append(summary)
        return summary
    return None


def process_native_tool_result(
    state: AgentTurnAccumulator,
    part: NativeToolReturnPart,
) -> Optional[ToolResultSummary]:
    """Record a native tool return on dispatch state.

    Args:
        state: Mutable dispatch reducer state.
        part: Native tool return part from the model.

    Returns:
        Tool result summary when recorded, otherwise None if already emitted.
    """
    if part.tool_call_id in state.emitted_tool_result_ids:
        return None

    match part.tool_name:
        case FileSearchTool.kind:
            tool_result, rag_chunks, referenced_documents = (
                summarize_file_search_result(
                    part,
                    state.tool_round,
                    state.seen_docs,
                    state.vector_store_ids,
                    state.rag_id_mapping,
                )
            )
            state.turn_summary.rag_chunks.extend(rag_chunks)
            state.turn_summary.referenced_documents.extend(referenced_documents)
        case WebSearchTool.kind:
            tool_result = summarize_web_search_result(part, state.tool_round)
        case tool_name if tool_name.startswith(_MCP_SERVER_TOOL_PREFIX):
            tool_result = summarize_mcp_tool_result(part, state.tool_round)
        case _:
            logger.warning("Unknown tool name: %s", part.tool_name)
            return None

    state.emitted_tool_result_ids.add(tool_result.id)
    state.turn_summary.tool_results.append(tool_result)
    state.round_increment_pending = True
    return tool_result


def process_function_tool_result(
    state: AgentTurnAccumulator,
    part: ToolReturnPart,
) -> Optional[ToolResultSummary]:
    """Record a client function tool return on dispatch state.

    Args:
        state: Mutable dispatch reducer state.
        part: Function tool return part from the agent.

    Returns:
        Tool result summary when recorded, otherwise None if already emitted.
    """
    if part.tool_call_id in state.emitted_tool_result_ids:
        return None
    tool_result = summarize_function_tool_result(part, state.tool_round)
    state.emitted_tool_result_ids.add(tool_result.id)
    state.turn_summary.tool_results.append(tool_result)
    state.round_increment_pending = True
    return tool_result


def summarize_function_tool_result(
    part: ToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Build a tool-result summary for a client function tool return.

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


def referenced_documents_from_file_search_results(
    results: list[OpenAIFileSearchResult],
    seen_docs: set[tuple[str, str]],
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> list[ReferencedDocument]:
    """Parse referenced documents from OpenAI file-search result rows.

    Args:
        results: Validated file-search result rows.
        seen_docs: Dedupe keys already emitted; updated in place.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Newly discovered referenced documents from these result rows.
    """
    documents: list[ReferencedDocument] = []
    for result in results:
        doc = build_referenced_document(result, vector_store_ids, rag_id_mapping)
        if doc is None:
            continue

        dedup_key = (str(doc.doc_url or ""), doc.doc_title or "")
        if dedup_key in seen_docs:
            continue

        seen_docs.add(dedup_key)
        documents.append(doc)

    return documents


def build_referenced_document(
    result: OpenAIFileSearchResult,
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> Optional[ReferencedDocument]:
    """Build one referenced document from a single file-search result row.

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
        source=resolve_source_for_result(attributes, vector_store_ids, rag_id_mapping),
        document_id=doc_id,
    )


def _file_search_attribute_str(
    attributes: dict[str, str | float | bool],
    key: str,
) -> Optional[str]:
    """Read a non-empty string metadata field from file-search attributes.

    Args:
        attributes: File-search result metadata attributes.
        key: Metadata key to read.

    Returns:
        Non-empty string value for the key, or None.
    """
    return str(value) if (value := attributes.get(key)) else None


def _file_search_attribute_url(
    attributes: dict[str, str | float | bool],
) -> Optional[str]:
    """Extract the first available document URL from file-search attributes.

    Args:
        attributes: File-search result metadata attributes.

    Returns:
        First matching URL value as a string, or None.
    """
    for key in _FILE_SEARCH_URL_KEYS:
        if url := _file_search_attribute_str(attributes, key):
            return url
    return None


def rag_chunks_from_file_search_results(
    results: list[OpenAIFileSearchResult],
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> list[RAGChunk]:
    """Extract RAG chunks from OpenAI file-search result rows.

    Args:
        results: Validated file-search result rows.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        RAG chunks extracted from these result rows.
    """
    return [
        RAGChunk(
            content=result.text,
            source=resolve_source_for_result(
                result.attributes or {}, vector_store_ids, rag_id_mapping
            ),
            score=result.score,
            attributes=result.attributes or None,
        )
        for result in results
        if result.text
    ]


def summarize_web_search_result(
    part: NativeToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Build a tool-result summary from a native web-search return.

    Args:
        part: Native web-search tool return part from the model stream.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    content = cast(dict[str, Any], part.content)
    status = str(content.pop("status"))
    return ToolResultSummary(
        id=part.tool_call_id,
        status=status,
        content=json.dumps(content) if content else "",
        type="web_search_call",
        round=tool_round,
    )


def summarize_mcp_list_tools_result(
    part: NativeToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Build a tool-result summary from a native MCP list-tools return.

    Args:
        part: Native MCP list-tools return part from the model stream.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    content = cast(dict[str, Any], part.content)
    call_id = part.tool_call_id
    label = part.tool_name.removeprefix(f"{MCPServerTool.kind}:")

    if error := content.get("error"):
        return ToolResultSummary(
            id=call_id,
            status="failure",
            content=str(error),
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


def summarize_mcp_call_result(
    part: NativeToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Build a tool-result summary from a native MCP tool call return.

    Args:
        part: Native MCP call return part from the model stream.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    content = cast(dict[str, Any], part.content)
    call_id = part.tool_call_id

    if error := content.get("error"):
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


def summarize_mcp_tool_result(
    part: NativeToolReturnPart,
    tool_round: int,
) -> ToolResultSummary:
    """Build a tool-result summary from a native MCP server tool return.

    Dispatches to list-tools or call processors based on return shape.

    Args:
        part: Native MCP tool return part from the model stream.
        tool_round: Tool execution round number for this result.

    Returns:
        Tool result summary in LCS turn-summary format.
    """
    content = cast(dict[str, Any], part.content)
    if "tools" in content:
        return summarize_mcp_list_tools_result(part, tool_round)
    return summarize_mcp_call_result(part, tool_round)


def summarize_file_search_result(
    part: NativeToolReturnPart,
    tool_round: int,
    seen_docs: set[tuple[str, str]],
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> tuple[ToolResultSummary, list[RAGChunk], list[ReferencedDocument]]:
    """Build tool result, RAG chunks, and referenced docs from a file-search return.

    Args:
        part: Native file-search tool return part from the model stream.
        tool_round: Tool execution round number for this result.
        seen_docs: Dedupe keys for referenced documents; updated in place.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Tool result summary, RAG chunks, and referenced documents for this return.
    """
    content = cast(dict[str, Any], part.content)
    tool_result = ToolResultSummary(
        id=part.tool_call_id,
        status=str(content.pop("status")),
        content=json.dumps(content),
        type="file_search_call",
        round=tool_round,
    )
    results = [
        OpenAIFileSearchResult.model_validate(result)
        for result in content.get("results", [])
    ]
    rag_chunks = rag_chunks_from_file_search_results(
        results,
        vector_store_ids=vector_store_ids,
        rag_id_mapping=rag_id_mapping,
    )
    referenced_documents = referenced_documents_from_file_search_results(
        results,
        seen_docs,
        vector_store_ids=vector_store_ids,
        rag_id_mapping=rag_id_mapping,
    )
    return tool_result, rag_chunks, referenced_documents
