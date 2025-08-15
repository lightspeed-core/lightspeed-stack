"""Shared utilities for parsing metadata from knowledge search responses."""

import ast
import re
from typing import Any


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
