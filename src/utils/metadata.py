"""Shared utilities for parsing metadata from knowledge search responses."""

import ast
import json
import logging
import re
from typing import Any

import pydantic

from models.responses import ReferencedDocument

logger = logging.getLogger(__name__)


# Case-insensitive pattern to find "Metadata:" labels
METADATA_LABEL_PATTERN = re.compile(r"^\s*metadata:\s*", re.MULTILINE | re.IGNORECASE)


def _extract_balanced_braces(text: str, start_pos: int) -> str:
    """Extract a balanced brace substring starting from start_pos.

    Args:
        text: The text to search
        start_pos: Position where the opening brace should be

    Returns:
        The balanced brace substring including the braces

    Raises:
        ValueError: If no balanced braces are found
    """
    if start_pos >= len(text) or text[start_pos] != "{":
        raise ValueError("No opening brace found at start position")

    brace_count = 0
    pos = start_pos

    while pos < len(text):
        char = text[pos]
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start_pos : pos + 1]
        pos += 1

    raise ValueError("Unmatched opening brace - no closing brace found")


def parse_knowledge_search_metadata(
    text: str, *, strict: bool = True
) -> dict[str, dict[str, Any]]:
    """Parse metadata from knowledge search text content.

    Args:
        text: Text content that may contain metadata patterns
        strict: If True (default), raise ValueError on first parsing error.
               If False, skip invalid blocks and continue parsing.

    Returns:
        Dictionary of document_id -> metadata mappings

    Raises:
        ValueError: If metadata parsing fails due to invalid Python-literal or JSON-like syntax
                   (only in strict mode)
    """
    metadata_map: dict[str, dict[str, Any]] = {}

    # Find all "Metadata:" labels (case-insensitive)
    for match in METADATA_LABEL_PATTERN.finditer(text):
        try:
            # Find the position right after the "Metadata:" label
            label_end = match.end()

            # Skip any whitespace after the label
            pos = label_end
            while pos < len(text) and text[pos].isspace():
                pos += 1

            # Look for opening brace
            if pos >= len(text) or text[pos] != "{":
                continue  # No brace found, skip this match

            # Extract balanced brace content
            brace_content = _extract_balanced_braces(text, pos)

            # Parse the extracted content
            meta = ast.literal_eval(brace_content)

            # Verify the result is a dict before accessing keys
            if isinstance(meta, dict) and "document_id" in meta:
                metadata_map[meta["document_id"]] = meta

        except (SyntaxError, ValueError) as e:
            if strict:
                raise ValueError(
                    f"Failed to parse metadata at position {match.start()}: {e}"
                ) from e
            # non-strict mode: skip bad blocks, keep the rest
            continue

    return metadata_map


def process_knowledge_search_content(tool_response: Any) -> dict[str, dict[str, Any]]:
    """Process knowledge search tool response content for metadata.

    Args:
        tool_response: Tool response object containing content to parse

    Returns:
        Dictionary mapping document_id to metadata dict
    """
    metadata_map: dict[str, dict[str, Any]] = {}

    # Guard against missing tool_response or content
    if not tool_response:
        return metadata_map

    content = getattr(tool_response, "content", None)
    if not content:
        return metadata_map

    # Handle string content by attempting JSON parsing
    if isinstance(content, str):
        try:
            content = json.loads(content, strict=False)
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, try parsing as metadata text
            try:
                parsed_metadata = parse_knowledge_search_metadata(content, strict=False)
                metadata_map.update(parsed_metadata)
            except ValueError as e:
                logger.exception(
                    "Error processing string content as metadata; position=%s",
                    getattr(e, "position", "unknown"),
                )
            return metadata_map

    # Ensure content is iterable (but not a string)
    if isinstance(content, str):
        return metadata_map
    try:
        iter(content)
    except TypeError:
        return metadata_map

    for text_content_item in content:
        # Skip items that lack a non-empty "text" attribute
        text = getattr(text_content_item, "text", None)
        if not text:
            continue

        try:
            parsed_metadata = parse_knowledge_search_metadata(text, strict=False)
            metadata_map.update(parsed_metadata)
        except ValueError as e:
            logger.exception(
                "Error processing metadata from text; position=%s",
                getattr(e, "position", "unknown"),
            )

    return metadata_map


def extract_referenced_documents_from_steps(
    steps: list[Any],
) -> list[ReferencedDocument]:
    """Extract referenced documents from tool execution steps.

    Args:
        steps: List of response steps from the agent

    Returns:
        List of referenced documents with doc_url and doc_title, sorted deterministically
    """
    metadata_map: dict[str, dict[str, Any]] = {}

    for step in steps:
        if getattr(step, "step_type", "") != "tool_execution" or not hasattr(
            step, "tool_responses"
        ):
            continue

        for tool_response in getattr(step, "tool_responses", []) or []:
            if getattr(
                tool_response, "tool_name", ""
            ) != "knowledge_search" or not getattr(tool_response, "content", []):
                continue

            response_metadata = process_knowledge_search_content(tool_response)
            metadata_map.update(response_metadata)

    # Extract referenced documents from metadata with error handling
    referenced_documents = []
    for v in metadata_map.values():
        if "docs_url" in v and "title" in v:
            try:
                doc = ReferencedDocument(doc_url=v["docs_url"], doc_title=v["title"])
                referenced_documents.append(doc)
            except (pydantic.ValidationError, ValueError) as e:
                logger.warning(
                    "Skipping invalid referenced document with docs_url='%s', title='%s': %s",
                    v.get("docs_url", "<missing>"),
                    v.get("title", "<missing>"),
                    str(e),
                )
                continue

    return sorted(referenced_documents, key=lambda d: (d.doc_title, str(d.doc_url)))
