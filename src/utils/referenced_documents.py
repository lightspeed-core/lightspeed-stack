"""Utilities for referenced document lists."""

from typing import Optional

from models.common.turn_summary import ReferencedDocument


def graft_url_fragment(
    reference: Optional[str], source_path: Optional[str]
) -> Optional[str]:
    """Append the ``#fragment`` from ``source_path`` onto ``reference``.

    OKP offline document URLs are built from the portal path (``parent_id`` /
    ``document_id``), which points at the page but carries no section anchor. The
    chunk's ``source_path`` does carry the matched section's ``#heading_id``.
    Grafting that fragment onto the portal path preserves deep-linking to the
    matched section.

    This is a no-op when ``reference`` is empty, when ``source_path`` is empty or
    has no ``#`` fragment, when the fragment is empty, or when ``reference``
    already has a fragment of its own.

    Args:
        reference: The portal-relative document path to augment.
        source_path: The chunk source path that may carry a ``#fragment``.

    Returns:
        ``reference`` with the fragment appended, or the original ``reference``.

    """
    if not reference or not source_path or "#" not in source_path:
        return reference
    if "#" in str(reference):
        return reference
    fragment = source_path.split("#", 1)[1]
    if not fragment:
        return reference
    return f"{reference}#{fragment}"


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
