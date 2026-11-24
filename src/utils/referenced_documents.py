"""Utilities for referenced document lists."""

from typing import Optional

from models.common.turn_summary import ReferencedDocument


def deduplicate_referenced_documents(
    docs: list[ReferencedDocument],
) -> list[ReferencedDocument]:
    """Remove duplicate referenced documents based on URL and title."""
    seen: set[tuple[Optional[str], Optional[str]]] = set()
    out: list[ReferencedDocument] = []
    for doc in docs:
        key = (str(doc.doc_url) if doc.doc_url else None, doc.doc_title)
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out
