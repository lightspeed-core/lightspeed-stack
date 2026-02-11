"""Utility functions for endpoint handlers."""

from typing import Any, Optional

from fastapi import HTTPException
from pydantic import AnyUrl, ValidationError
from sqlalchemy.exc import SQLAlchemyError

import constants
from app.database import get_session
from configuration import AppConfig, LogicError
from log import get_logger
from models.database.conversations import UserConversation
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
)
from utils.types import ReferencedDocument, TurnSummary

logger = get_logger(__name__)


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation from the local database by its ID.

    Args:
        conversation_id (str): The unique identifier of the conversation to delete.

    Returns:
        bool: True if the conversation was deleted, False if it was not found.
    """
    with get_session() as session:
        db_conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )
        if db_conversation:
            session.delete(db_conversation)
            session.commit()
            logger.info("Deleted conversation %s from local database", conversation_id)
            return True
        logger.info(
            "Conversation %s not found in local database, it may have already been deleted",
            conversation_id,
        )
        return False


def retrieve_conversation(conversation_id: str) -> Optional[UserConversation]:
    """Retrieve a conversation from the database by its ID.

    Args:
        conversation_id (str): The unique identifier of the conversation to retrieve.

    Returns:
        Optional[UserConversation]: The conversation object if found, otherwise None.
    """
    with get_session() as session:
        return session.query(UserConversation).filter_by(id=conversation_id).first()


def validate_conversation_ownership(
    user_id: str, conversation_id: str, others_allowed: bool = False
) -> Optional[UserConversation]:
    """Validate that the conversation belongs to the user.

    Validates that the conversation with the given ID belongs to the user with the given ID.
    If `others_allowed` is True, it allows conversations that do not belong to the user,
    which is useful for admin access.
    """
    with get_session() as session:
        conversation_query = session.query(UserConversation)

        filtered_conversation_query = (
            conversation_query.filter_by(id=conversation_id)
            if others_allowed
            else conversation_query.filter_by(id=conversation_id, user_id=user_id)
        )

        conversation: Optional[UserConversation] = filtered_conversation_query.first()

        return conversation


def can_access_conversation(
    conversation_id: str, user_id: str, others_allowed: bool
) -> bool:
    """Check only whether a user is allowed to access a conversation.

    Args:
        conversation_id (str): The ID of the conversation to check.
        user_id (str): The ID of the user requesting access.
        others_allowed (bool): Whether the user can access conversations owned by others.

    Returns:
        bool: True if the user is allowed to access the conversation, False otherwise.
    """
    if others_allowed:
        return True

    with get_session() as session:
        owner_user_id = (
            session.query(UserConversation.user_id)
            .filter(UserConversation.id == conversation_id)
            .scalar()
        )
        # If conversation does not exist, permissions check returns True
        if owner_user_id is None:
            return True

        # If conversation exists, user_id must match
        return owner_user_id == user_id


def validate_and_retrieve_conversation(
    normalized_conv_id: str,
    user_id: str,
    others_allowed: bool,
) -> UserConversation:
    """
    Validate access and retrieve a conversation from the database.

    This function performs access validation, retrieves the conversation,
    and handles all error cases (forbidden access, not found, database errors).

    Args:
        normalized_conv_id: The normalized conversation ID to retrieve.
        user_id: The ID of the user requesting access.
        others_allowed: Whether the user can access conversations owned by others.

    Returns:
        UserConversation: The conversation object if found and accessible.

    Raises:
        HTTPException:
            - 403 Forbidden: If user doesn't have access to the conversation.
            - 404 Not Found: If conversation doesn't exist in database.
            - 500 Internal Server Error: If database error occurs.
    """
    if not can_access_conversation(
        normalized_conv_id,
        user_id,
        others_allowed=others_allowed,
    ):
        logger.warning(
            "User %s attempted to read conversation %s they don't have access to",
            user_id,
            normalized_conv_id,
        )
        response = ForbiddenResponse.conversation(
            action="read",
            resource_id=normalized_conv_id,
            user_id=user_id,
        )
        raise HTTPException(**response.model_dump())

    # If reached this, user is authorized to retrieve this conversation
    try:
        user_conversation = retrieve_conversation(normalized_conv_id)
        if user_conversation is None:
            logger.error(
                "Conversation %s not found in database.",
                normalized_conv_id,
            )
            response = NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            )
            raise HTTPException(**response.model_dump())

    except SQLAlchemyError as e:
        logger.error(
            "Database error occurred while retrieving conversation %s: %s",
            normalized_conv_id,
            str(e),
        )
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

    return user_conversation


def check_configuration_loaded(config: AppConfig) -> None:
    """
    Raise an error if the configuration is not loaded.

    Args:
        config (AppConfig): The application configuration.

    Raises:
        HTTPException: If configuration is missing.
    """
    try:
        _ = config.configuration
    except LogicError as e:
        response = InternalServerErrorResponse.configuration_not_loaded()
        raise HTTPException(**response.model_dump()) from e


def _process_http_source(
    src: str, doc_urls: set[str]
) -> Optional[tuple[Optional[AnyUrl], str]]:
    """
    Process HTTP source and return (doc_url, doc_title) tuple.

    Parameters:
        src (str): The source URL string to process.
        doc_urls (set[str]): Set of already-seen source strings; the function
                             will add `src` to this set when it is new.

    Returns:
        Optional[tuple[Optional[AnyUrl], str]]: A tuple (validated_url, doc_title)
               when `src` was not previously seen:
            - `validated_url`: an `AnyUrl` instance if `src` is a valid URL, or
              `None` if validation failed.
            - `doc_title`: the last path segment of the URL or `src` if no path
               segment is present.
        Returns `None` if `src` was already present in `doc_urls`.
    """
    if src not in doc_urls:
        doc_urls.add(src)
        try:
            validated_url = AnyUrl(src)
        except ValidationError:
            logger.warning("Invalid URL in chunk source: %s", src)
            validated_url = None

        doc_title = src.rsplit("/", 1)[-1] or src
        return (validated_url, doc_title)
    return None


def _process_document_id(
    src: str,
    doc_ids: set[str],
    doc_urls: set[str],
    metas_by_id: dict[str, dict[str, Any]],
    metadata_map: Optional[dict[str, Any]],
) -> Optional[tuple[Optional[AnyUrl], str]]:
    """
    Process document ID and return (doc_url, doc_title) tuple.

    Parameters:
        src (str): Document identifier to process.
        doc_ids (set[str]): Set of already-seen document IDs; the function adds `src` to this set.
        doc_urls (set[str]): Set of already-seen document URLs; the function
                             adds discovered URLs to this set to avoid duplicates.
        metas_by_id (dict[str, dict[str, Any]]): Mapping of document IDs to
                                                 metadata dicts that may
                                                 contain `docs_url` and
                                                 `title`.
        metadata_map (Optional[dict[str, Any]]): If provided (truthy), indicates
                                              metadata is available and enables
                                              metadata lookup; when falsy,
                                              metadata lookup is skipped.

    Returns:
        Optional[tuple[Optional[AnyUrl], str]]: `(validated_url, doc_title)` where
        `validated_url` is a validated `AnyUrl` or `None` and `doc_title` is
        the chosen title string; returns `None` if the `src` or its URL was
        already processed.
    """
    if src in doc_ids:
        return None
    doc_ids.add(src)

    meta = metas_by_id.get(src, {}) if metadata_map else {}
    doc_url = meta.get("docs_url")
    title = meta.get("title")
    # Type check to ensure we have the right types
    if not isinstance(doc_url, (str, type(None))):
        doc_url = None
    if not isinstance(title, (str, type(None))):
        title = None

    if doc_url:
        if doc_url in doc_urls:
            return None
        doc_urls.add(doc_url)

    try:
        validated_doc_url = None
        if doc_url and doc_url.startswith("http"):
            validated_doc_url = AnyUrl(doc_url)
    except ValidationError:
        logger.warning("Invalid URL in metadata: %s", doc_url)
        validated_doc_url = None

    doc_title = title or (doc_url.rsplit("/", 1)[-1] if doc_url else src)
    return (validated_doc_url, doc_title)


def _add_additional_metadata_docs(
    doc_urls: set[str],
    metas_by_id: dict[str, dict[str, Any]],
) -> list[tuple[Optional[AnyUrl], str]]:
    """Add additional referenced documents from metadata_map."""
    additional_entries: list[tuple[Optional[AnyUrl], str]] = []
    for meta in metas_by_id.values():
        doc_url = meta.get("docs_url")
        title = meta.get("title")  # Note: must be "title", not "Title"
        # Type check to ensure we have the right types
        if not isinstance(doc_url, (str, type(None))):
            doc_url = None
        if not isinstance(title, (str, type(None))):
            title = None
        if doc_url and doc_url not in doc_urls and title is not None:
            doc_urls.add(doc_url)
            try:
                validated_url = None
                if doc_url.startswith("http"):
                    validated_url = AnyUrl(doc_url)
            except ValidationError:
                logger.warning("Invalid URL in metadata_map: %s", doc_url)
                validated_url = None

            additional_entries.append((validated_url, title))
    return additional_entries


def _process_rag_chunks_for_documents(
    rag_chunks: list,
    metadata_map: Optional[dict[str, Any]] = None,
) -> list[tuple[Optional[AnyUrl], str]]:
    """
    Process RAG chunks and return a list of (doc_url, doc_title) tuples.

    This is the core logic shared between both return formats.

    Parameters:
        rag_chunks (list): Iterable of RAG chunk objects; each chunk must
        provide a `source` attribute (e.g., an HTTP URL or a document ID).
        metadata_map (Optional[dict[str, Any]]): Optional mapping of document IDs
        to metadata dictionaries used to resolve titles and document URLs.

    Returns:
        list[tuple[Optional[AnyUrl], str]]: Ordered list of tuples where the first
        element is a validated URL object or `None` (if no URL is available)
        and the second element is the document title.
    """
    doc_urls: set[str] = set()
    doc_ids: set[str] = set()

    # Process metadata_map if provided
    metas_by_id: dict[str, dict[str, Any]] = {}
    if metadata_map:
        metas_by_id = {k: v for k, v in metadata_map.items() if isinstance(v, dict)}

    document_entries: list[tuple[Optional[AnyUrl], str]] = []

    for chunk in rag_chunks:
        src = chunk.source
        if not src or src == constants.DEFAULT_RAG_TOOL:
            continue

        if src.startswith("http"):
            entry = _process_http_source(src, doc_urls)
            if entry:
                document_entries.append(entry)
        else:
            entry = _process_document_id(
                src, doc_ids, doc_urls, metas_by_id, metadata_map
            )
            if entry:
                document_entries.append(entry)

    # Add any additional referenced documents from metadata_map not already present
    if metadata_map:
        additional_entries = _add_additional_metadata_docs(doc_urls, metas_by_id)
        document_entries.extend(additional_entries)

    return document_entries


def create_referenced_documents(
    rag_chunks: list,
    metadata_map: Optional[dict[str, Any]] = None,
    return_dict_format: bool = False,
) -> list[ReferencedDocument] | list[dict[str, Optional[str]]]:
    """
    Create referenced documents from RAG chunks with optional metadata enrichment.

    This unified function processes RAG chunks and creates referenced documents with
    optional metadata enrichment, deduplication, and proper URL handling. It can return
    either ReferencedDocument objects (for query endpoint) or dictionaries (for streaming).

    Parameters:
        rag_chunks: List of RAG chunks with source information
        metadata_map: Optional mapping containing metadata about referenced documents
        return_dict_format: If True, returns list of dicts; if False, returns list of
            ReferencedDocument objects

    Returns:
        List of ReferencedDocument objects or dictionaries with doc_url and doc_title
    """
    document_entries = _process_rag_chunks_for_documents(rag_chunks, metadata_map)

    if return_dict_format:
        return [
            {
                "doc_url": str(doc_url) if doc_url else None,
                "doc_title": doc_title,
            }
            for doc_url, doc_title in document_entries
        ]
    return [
        ReferencedDocument(doc_url=doc_url, doc_title=doc_title)
        for doc_url, doc_title in document_entries
    ]


# Backward compatibility functions
def create_referenced_documents_with_metadata(
    summary: TurnSummary, metadata_map: dict[str, Any]
) -> list[ReferencedDocument]:
    """
    Create referenced documents from RAG chunks with metadata enrichment for streaming.

    This function now returns ReferencedDocument objects for consistency with the query endpoint.

    Parameters:
        summary (TurnSummary): Summary object containing `rag_chunks` to be processed.
        metadata_map (dict[str, Any]): Metadata keyed by document id used to
                                       derive or enrich document `doc_url` and `doc_title`.

    Returns:
        list[ReferencedDocument]: ReferencedDocument objects with `doc_url` and
        `doc_title` populated; `doc_url` may be `None` if no valid URL could be
        determined.
    """
    document_entries = _process_rag_chunks_for_documents(
        summary.rag_chunks, metadata_map
    )
    return [
        ReferencedDocument(doc_url=doc_url, doc_title=doc_title)
        for doc_url, doc_title in document_entries
    ]


def create_referenced_documents_from_chunks(
    rag_chunks: list,
) -> list[ReferencedDocument]:
    """
    Create referenced documents from RAG chunks for query endpoint.

    This is a backward compatibility wrapper around the unified
    create_referenced_documents function.

    Parameters:
        rag_chunks (list): List of RAG chunk entries containing source and metadata information.

    Returns:
        list[ReferencedDocument]: ReferencedDocument instances created from the
        chunks; each contains `doc_url` (validated URL or `None`) and
        `doc_title`.
    """
    document_entries = _process_rag_chunks_for_documents(rag_chunks)
    return [
        ReferencedDocument(doc_url=doc_url, doc_title=doc_title)
        for doc_url, doc_title in document_entries
    ]
