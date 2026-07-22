"""Utility functions for formatting and parsing MCP tool descriptions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from log import get_logger
from models.common.tools import (
    CatalogTool,
    CatalogToolParameter,
    ListedMcpTool,
    ToolDef,
)

logger = get_logger(__name__)


def input_schema_to_parameters(
    schema: Optional[dict[str, Any]],
) -> list[CatalogToolParameter]:
    """Convert a JSON Schema object to the flat parameter list used by ``/tools``.

    Parameters:
        schema: JSON Schema dict with ``properties`` and ``required`` keys.

    Returns:
        Flat parameter models for the tools endpoint response.
    """
    if not schema or "properties" not in schema:
        return []

    required_params = set(schema.get("required", []))
    return [
        CatalogToolParameter(
            name=name,
            description=prop.get("description", ""),
            parameter_type=prop.get("type", "string"),
            required=name in required_params,
            default=prop.get("default"),
        )
        for name, prop in schema["properties"].items()
    ]


def extract_clean_description(description: str) -> str:
    """
    Extract a clean description from structured metadata format.

    Parses a raw description that may contain structured metadata
    (e.g., lines or sections starting with TOOL_NAME=,
    DISPLAY_NAME=, USECASE=, INSTRUCTIONS=, INPUT_DESCRIPTION=,
    OUTPUT_DESCRIPTION=, EXAMPLES=, PREREQUISITES=,
    AGENT_DECISION_CRITERIA=) and returns a cleaned, user-facing
    description.  The function prefers the first paragraph that
    does not start with a known metadata prefix and is longer than
    20 characters. If no such paragraph exists, it returns the
    value of a `USECASE=` line if present. If neither is found, it
    returns the first 200 characters of the input, appending "..."
    when truncation occurs.

    Parameters:
    ----------
        description: Raw description with structured metadata

    Returns:
    -------
        Clean description without metadata
    """
    min_description_length = 20
    fallback_truncation_length = 200

    try:
        # Look for the main description after all the metadata
        description_parts = description.split("\n\n")
        for part in description_parts:
            if not any(
                part.strip().startswith(prefix)
                for prefix in [
                    "TOOL_NAME=",
                    "DISPLAY_NAME=",
                    "USECASE=",
                    "INSTRUCTIONS=",
                    "INPUT_DESCRIPTION=",
                    "OUTPUT_DESCRIPTION=",
                    "EXAMPLES=",
                    "PREREQUISITES=",
                    "AGENT_DECISION_CRITERIA=",
                ]
            ):
                if (
                    part.strip() and len(part.strip()) > min_description_length
                ):  # Reasonable description length
                    return part.strip()

        # If no clean description found, try to extract from USECASE
        lines = description.split("\n")
        for line in lines:
            if line.startswith("USECASE="):
                return line.replace("USECASE=", "").strip()

        # Fallback to first 200 characters
        return (
            description[:fallback_truncation_length] + "..."
            if len(description) > fallback_truncation_length
            else description
        )

    except (ValueError, AttributeError) as e:
        logger.warning("Failed to extract clean description: %s", e)
        return (
            description[:fallback_truncation_length] + "..."
            if len(description) > fallback_truncation_length
            else description
        )


def build_catalog_tool(
    tool: ListedMcpTool | ToolDef,
    *,
    provider_id: str,
    toolgroup_id: str,
    server_source: str,
) -> CatalogTool:
    """Build a ``/tools`` catalog entry from discovered tool metadata.

    Parameters:
        tool: MCP or Llama Stack tool definition with name, description, and schema.
        provider_id: Provider ID serving the tool.
        toolgroup_id: Tool group identifier.
        server_source: Human-readable source label for the tool.

    Returns:
        Typed catalog tool entry.
    """
    cleaned_description = tool.description or ""
    if cleaned_description and (
        "TOOL_NAME=" in cleaned_description or "DISPLAY_NAME=" in cleaned_description
    ):
        cleaned_description = extract_clean_description(cleaned_description)

    return CatalogTool(
        identifier=tool.name,
        description=cleaned_description,
        parameters=input_schema_to_parameters(tool.input_schema),
        provider_id=provider_id,
        toolgroup_id=toolgroup_id,
        server_source=server_source,
    )


def translate_vector_store_ids_to_user_facing(
    tools: list[dict[str, Any]],
    rag_id_mapping: Mapping[str, str],
) -> list[dict[str, Any]]:
    """
    Rewrite file_search tool dicts so vector_store_ids use user-facing RAG IDs.

    Parameters:
    ----------
        tools: Serialized tool dicts.
        rag_id_mapping: Llama Stack vector_db_id -> user-facing RAG id.

    Returns:
    -------
        list[dict[str, Any]]: New list of tool dicts; file_search entries get
            updated vector_store_ids.
    """
    if not rag_id_mapping:
        return list(tools)
    out: list[dict[str, Any]] = []
    for tool in tools:
        if tool["type"] == "file_search":
            mapped = [rag_id_mapping.get(vid, vid) for vid in tool["vector_store_ids"]]
            out.append({**tool, "vector_store_ids": mapped})
        else:
            out.append(tool)
    return out
