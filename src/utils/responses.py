"""Utility functions for processing Responses API output."""

from typing import Any

from pydantic import AnyUrl, ValidationError

from models.responses import ReferencedDocument


def extract_text_from_response_output_item(output_item: Any) -> str:
    """Extract assistant message text from a Responses API output item.

    This function parses output items from the OpenAI-compatible Responses API
    and extracts text content from assistant messages. It handles multiple content
    formats including string content, content arrays with text parts, and refusal
    messages.

    Args:
        output_item: A Responses API output item (typically from response.output array).
            Expected to have attributes like type, role, and content.

    Returns:
        str: The extracted text content from the assistant message. Returns an empty
            string if the output_item is not an assistant message or contains no text.

    Example:
        >>> for output_item in response.output:
        ...     text = extract_text_from_response_output_item(output_item)
        ...     if text:
        ...         print(text)
    """
    if getattr(output_item, "type", None) != "message":
        return ""
    if getattr(output_item, "role", None) != "assistant":
        return ""

    content = getattr(output_item, "content", None)
    if isinstance(content, str):
        return content

    text_fragments: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                text_fragments.append(part)
                continue
            text_value = getattr(part, "text", None)
            if text_value:
                text_fragments.append(text_value)
                continue
            refusal = getattr(part, "refusal", None)
            if refusal:
                text_fragments.append(refusal)
                continue
            if isinstance(part, dict):
                dict_text = part.get("text") or part.get("refusal")
                if dict_text:
                    text_fragments.append(str(dict_text))

    return "".join(text_fragments)


def _parse_file_search_result(
    result: Any,
) -> tuple[str | None, str | None]:
    """
    Extract filename and URL from a file search result.

    Args:
        result: A file search result (dict or object)

    Returns:
        tuple[str | None, str | None]: (doc_url, filename) tuple
    """
    # Handle both object and dict access
    if isinstance(result, dict):
        filename = result.get("filename")
        attributes = result.get("attributes", {})
    else:
        filename = getattr(result, "filename", None)
        attributes = getattr(result, "attributes", {}) or {}

    # Try to get URL from attributes - look for common URL fields
    doc_url = (
        attributes.get("link") or attributes.get("url") or attributes.get("doc_url")
    )
    # Treat empty string as None for URL to satisfy AnyUrl | None
    final_url = doc_url if doc_url else None
    return (final_url, filename)


def _parse_annotation(
    annotation: Any,
) -> tuple[str | None, str | None, str | None]:
    """
    Extract type, URL, and title from an annotation.

    Args:
        annotation: An annotation (dict or object)

    Returns:
        tuple[str | None, str | None, str | None]: (type, url, title) tuple
    """
    # Handle both object and dict access for annotations
    if isinstance(annotation, dict):
        anno_type = annotation.get("type")
        anno_url = annotation.get("url")
        anno_title = annotation.get("title") or annotation.get("filename")
    else:
        anno_type = getattr(annotation, "type", None)
        anno_url = getattr(annotation, "url", None)
        anno_title = getattr(annotation, "title", None) or getattr(
            annotation, "filename", None
        )
    return (anno_type, anno_url, anno_title)


def _add_document_if_unique(
    documents: list[ReferencedDocument],
    seen_docs: set[tuple[str | None, str | None]],
    doc_url: str | None,
    doc_title: str | None,
) -> None:
    """
    Add document to list if not already seen.

    Args:
        documents: List of documents to append to
        seen_docs: Set of seen (url, title) tuples
        doc_url: Document URL string (may be None)
        doc_title: Document title (may be None)
    """
    if (doc_url, doc_title) not in seen_docs:
        # Convert string URL to AnyUrl type; None is acceptable as-is.
        validated_url: AnyUrl | None = None
        if doc_url:
            try:
                validated_url = AnyUrl(doc_url)  # type: ignore[arg-type]
            except ValidationError:
                # Skip documents with invalid URLs
                return
        documents.append(ReferencedDocument(doc_url=validated_url, doc_title=doc_title))
        seen_docs.add((doc_url, doc_title))


def _parse_file_search_output(
    output_item: Any,
    documents: list[ReferencedDocument],
    seen_docs: set[tuple[str | None, str | None]],
) -> None:
    """
    Parse file search results from an output item.

    Args:
        output_item: Output item of type "file_search_call"
        documents: List to append found documents to
        seen_docs: Set of seen (url, title) tuples
    """
    results = getattr(output_item, "results", []) or []
    for result in results:
        doc_url, filename = _parse_file_search_result(result)
        # If we have at least a filename or url
        if filename or doc_url:
            _add_document_if_unique(documents, seen_docs, doc_url, filename)


def _parse_message_annotations(
    output_item: Any,
    documents: list[ReferencedDocument],
    seen_docs: set[tuple[str | None, str | None]],
) -> None:
    """
    Parse annotations from a message output item.

    Args:
        output_item: Output item of type "message"
        documents: List to append found documents to
        seen_docs: Set of seen (url, title) tuples
    """
    content = getattr(output_item, "content", None)
    if not isinstance(content, list):
        return

    for part in content:
        # Skip if part is a string or doesn't have annotations
        if isinstance(part, str):
            continue

        annotations = getattr(part, "annotations", []) or []
        for annotation in annotations:
            anno_type, anno_url, anno_title = _parse_annotation(annotation)

            if anno_type == "url_citation":
                # Treat empty string as None
                final_url = anno_url if anno_url else None
                _add_document_if_unique(documents, seen_docs, final_url, anno_title)
            elif anno_type == "file_citation":
                _add_document_if_unique(documents, seen_docs, None, anno_title)


def parse_referenced_documents_from_responses_api(
    response: Any,
) -> list[ReferencedDocument]:
    """
    Parse referenced documents from OpenAI Responses API response.

    This function extracts document references from two sources:
    1. file_search_call results - Documents retrieved via RAG/file search
    2. message content annotations - Citation annotations in assistant messages

    Args:
        response: The OpenAI Response API response object (OpenAIResponseObject)

    Returns:
        list[ReferencedDocument]: List of unique referenced documents with doc_url and doc_title
    """
    documents: list[ReferencedDocument] = []
    # Use a set to track unique documents by (doc_url, doc_title) tuple
    seen_docs: set[tuple[str | None, str | None]] = set()

    if not response.output:
        return documents

    for output_item in response.output:
        item_type = getattr(output_item, "type", None)

        # 1. Parse from file_search_call results
        if item_type == "file_search_call":
            _parse_file_search_output(output_item, documents, seen_docs)
        # 2. Parse from message content annotations
        elif item_type == "message":
            _parse_message_annotations(output_item, documents, seen_docs)

    return documents
