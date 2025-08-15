"""Shared utilities for parsing metadata from knowledge search responses."""

import ast
import re
from typing import Any


METADATA_PATTERN = re.compile(r"^\s*Metadata:\s*(\{.*?\})\s*$", re.MULTILINE)


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

    for match in METADATA_PATTERN.findall(text):
        try:
            meta = ast.literal_eval(match)
            # Verify the result is a dict before accessing keys
            if isinstance(meta, dict) and "document_id" in meta:
                metadata_map[meta["document_id"]] = meta
        except (SyntaxError, ValueError) as e:
            if strict:
                raise ValueError(f"Failed to parse metadata '{match}': {e}") from e
            # non-strict mode: skip bad blocks, keep the rest
            continue

    return metadata_map
