"""Utility functions for formatting and parsing MCP tool descriptions."""

from typing import Any
from log import get_logger

logger = get_logger(__name__)


def format_tool_response(tool_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Format a tool dictionary to include only required fields.

    If the input description contains structured metadata (e.g.,
    lines starting with `TOOL_NAME=` or `DISPLAY_NAME=`), the
    description will be replaced with a cleaned, human-readable
    version extracted by `extract_clean_description`.

    Parameters:
        tool_dict: Raw tool dictionary from Llama Stack

    Returns:
        dict[str, Any]: Formatted tool dictionary containing the following keys:
            - identifier: tool identifier string (defaults to "").
            - description: cleaned or original description string.
            - parameters: list of parameter definitions (defaults to empty list).
            - provider_id: provider identifier string (defaults to "").
            - toolgroup_id: tool group identifier string (defaults to "").
            - server_source: server source string (defaults to "").
            - type: tool type string (defaults to "").
    """
    # Clean up description if it contains structured metadata
    description = tool_dict.get("description", "")
    if description and ("TOOL_NAME=" in description or "DISPLAY_NAME=" in description):
        # Extract clean description from structured metadata
        clean_description = extract_clean_description(description)
        description = clean_description

    # Extract only the required fields
    formatted_tool = {
        "identifier": tool_dict.get("identifier", ""),
        "description": description,
        "parameters": tool_dict.get("parameters", []),
        "provider_id": tool_dict.get("provider_id", ""),
        "toolgroup_id": tool_dict.get("toolgroup_id", ""),
        "server_source": tool_dict.get("server_source", ""),
        "type": tool_dict.get("type", ""),
    }

    return formatted_tool


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
        description: Raw description with structured metadata

    Returns:
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


def format_tools_list(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Format a list of tools with structured description parsing.

    Parameters:
        tools: (list[dict[str, Any]]): List of raw tool dictionaries

    Returns:
        list[dict[str, Any]]: Formatted tool dictionaries with normalized
                              fields and cleaned descriptions.
    """
    return [format_tool_response(tool) for tool in tools]
