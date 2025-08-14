"""Shared utilities for parsing metadata from knowledge search responses."""

import ast
import re
from typing import Any


METADATA_PATTERN = re.compile(r"^\s*Metadata:\s*(\{.*?\})\s*$", re.MULTILINE)


def parse_knowledge_search_metadata(text: str) -> dict[str, Any]:
    """Parse metadata from knowledge search text content.

    Args:
        text: Text content that may contain metadata patterns

    Returns:
        Dictionary of document_id -> metadata mappings

    Raises:
        ValueError: If metadata parsing fails due to invalid JSON or syntax
    """
    metadata_map: dict[str, Any] = {}

    for match in METADATA_PATTERN.findall(text):
        try:
            meta = ast.literal_eval(match)
            # Verify the result is a dict before accessing keys
            if isinstance(meta, dict) and "document_id" in meta:
                metadata_map[meta["document_id"]] = meta
        except (SyntaxError, ValueError) as e:
            raise ValueError(f"Failed to parse metadata '{match}': {e}") from e

    return metadata_map
