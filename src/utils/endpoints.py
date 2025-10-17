"""Utility functions for endpoint handlers."""

from contextlib import suppress
from typing import Any
from fastapi import HTTPException, status
from llama_stack_client._client import AsyncLlamaStackClient
from llama_stack_client.lib.agents.agent import AsyncAgent
from pydantic import AnyUrl, ValidationError

import constants
from models.cache_entry import CacheEntry
from models.requests import QueryRequest
from models.responses import ReferencedDocument
from models.database.conversations import UserConversation
from models.config import Action
from app.database import get_session
from configuration import AppConfig
from utils.suid import get_suid
from utils.types import TurnSummary
from utils.types import GraniteToolParser


from log import get_logger

logger = get_logger(__name__)


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation according to its ID."""
    with get_session() as session:
        db_conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )
        if db_conversation:
            session.delete(db_conversation)
            session.commit()
            logger.info("Deleted conversation %s from local database", conversation_id)
        else:
            logger.info(
                "Conversation %s not found in local database, it may have already been deleted",
                conversation_id,
            )


def retrieve_conversation(conversation_id: str) -> UserConversation | None:
    """Retrieve a conversation from the database by its ID.

    Args:
        conversation_id (str): The unique identifier of the conversation to retrieve.

    Returns:
        UserConversation | None: The conversation object if found, otherwise None.
    """
    with get_session() as session:
        return session.query(UserConversation).filter_by(id=conversation_id).first()


def validate_conversation_ownership(
    user_id: str, conversation_id: str, others_allowed: bool = False
) -> UserConversation | None:
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

        conversation: UserConversation | None = filtered_conversation_query.first()

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


def check_configuration_loaded(config: AppConfig) -> None:
    """
    Ensure the application configuration object is present.

    Raises:
        HTTPException: HTTP 500 Internal Server Error with detail `{"response":
        "Configuration is not loaded"}` when `config` is None.
    """
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"response": "Configuration is not loaded"},
        )


def get_system_prompt(query_request: QueryRequest, config: AppConfig) -> str:
    """
    Resolve which system prompt to use for a query.

    Precedence:
    1. If the request includes `system_prompt`, that value is returned (highest
       precedence).
    2. Else if the application configuration provides a customization
       `system_prompt`, that value is returned.
    3. Otherwise the module default `constants.DEFAULT_SYSTEM_PROMPT` is
       returned (lowest precedence).

    If configuration disables per-request system prompts
    (config.customization.disable_query_system_prompt) and the incoming
    `query_request` contains a `system_prompt`, an HTTP 422 Unprocessable
    Entity is raised instructing the client to remove the field.

    Parameters:
        query_request (QueryRequest): The incoming query payload; may contain a
        per-request `system_prompt`.
        config (AppConfig): Application configuration which may include
        customization flags and a default `system_prompt`.

    Returns:
        str: The resolved system prompt to apply to the request.
    """
    system_prompt_disabled = (
        config.customization is not None
        and config.customization.disable_query_system_prompt
    )
    if system_prompt_disabled and query_request.system_prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "response": (
                    "This instance does not support customizing the system prompt in the "
                    "query request (disable_query_system_prompt is set). Please remove the "
                    "system_prompt field from your request."
                )
            },
        )

    if query_request.system_prompt:
        # Query taking precedence over configuration is the only behavior that
        # makes sense here - if the configuration wants precedence, it can
        # disable query system prompt altogether with disable_system_prompt.
        return query_request.system_prompt

    # profile takes precedence for setting prompt
    if (
        config.customization is not None
        and config.customization.custom_profile is not None
    ):
        prompt = config.customization.custom_profile.get_prompts().get("default")
        if prompt:
            return prompt

    if (
        config.customization is not None
        and config.customization.system_prompt is not None
    ):
        return config.customization.system_prompt

    # default system prompt has the lowest precedence
    return constants.DEFAULT_SYSTEM_PROMPT


def get_topic_summary_system_prompt(config: AppConfig) -> str:
    """Get the topic summary system prompt."""
    # profile takes precedence for setting prompt
    if (
        config.customization is not None
        and config.customization.custom_profile is not None
    ):
        prompt = config.customization.custom_profile.get_prompts().get("topic_summary")
        if prompt:
            return prompt

    return constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


def validate_model_provider_override(
    query_request: QueryRequest, authorized_actions: set[Action] | frozenset[Action]
) -> None:
    """Validate whether model/provider overrides are allowed by RBAC.

    Raises HTTP 403 if the request includes model or provider and the caller
    lacks Action.MODEL_OVERRIDE permission.
    """
    if (query_request.model is not None or query_request.provider is not None) and (
        Action.MODEL_OVERRIDE not in authorized_actions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "response": (
                    "This instance does not permit overriding model/provider in the query request "
                    "(missing permission: MODEL_OVERRIDE). Please remove the model and provider "
                    "fields from your request."
                )
            },
        )


# # pylint: disable=R0913,R0917
def store_conversation_into_cache(
    config: AppConfig,
    user_id: str,
    conversation_id: str,
    cache_entry: CacheEntry,
    _skip_userid_check: bool,
    topic_summary: str | None,
) -> None:
    """Store one part of conversation into conversation history cache."""
    if config.conversation_cache_configuration.type is not None:
        cache = config.conversation_cache
        if cache is None:
            logger.warning("Conversation cache configured but not initialized")
            return
        cache.insert_or_append(
            user_id, conversation_id, cache_entry, _skip_userid_check
        )
        if topic_summary and len(topic_summary) > 0:
            cache.set_topic_summary(
                user_id, conversation_id, topic_summary, _skip_userid_check
            )


# # pylint: disable=R0913,R0917
async def get_agent(
    client: AsyncLlamaStackClient,
    model_id: str,
    system_prompt: str,
    available_input_shields: list[str],
    available_output_shields: list[str],
    conversation_id: str | None,
    no_tools: bool = False,
) -> tuple[AsyncAgent, str, str]:
    """
    Create or reuse an AsyncAgent with session persistence.

    Return the agent, conversation and session IDs.

    If a conversation_id is provided, the function attempts to retrieve the
    existing agent and, on success, rebinds a newly created agent instance to
    that conversation (deleting the temporary/orphan agent) and returns the
    first existing session_id for the conversation. If no conversation_id is
    provided or the existing agent cannot be retrieved, a new agent and session
    are created.

    Parameters:
        model_id (str): Identifier of the model to instantiate the agent with.
        system_prompt (str): Instructions/system prompt to initialize the agent with.

        available_input_shields (list[str]): Input shields to apply to the
        agent; empty list used if None/empty.

        available_output_shields (list[str]): Output shields to apply to the
        agent; empty list used if None/empty.

        conversation_id (str | None): If provided, attempt to reuse the agent
        for this conversation; otherwise a new conversation_id is created.

        no_tools (bool): When True, disables tool parsing for the agent (uses no tool parser).

    Returns:
        tuple[AsyncAgent, str, str]: A tuple of (agent, conversation_id, session_id).

    Raises:
        HTTPException: Raises HTTP 404 Not Found if an attempt to reuse a
        conversation succeeds in retrieving the agent but no sessions are found
        for that conversation.

    Side effects:
        - May delete an orphan agent when rebinding a newly created agent to an
          existing conversation_id.
        - Initializes the agent and may create a new session.
    """
    existing_agent_id = None
    if conversation_id:
        with suppress(ValueError):
            agent_response = await client.agents.retrieve(agent_id=conversation_id)
            existing_agent_id = agent_response.agent_id

    logger.debug("Creating new agent")
    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        input_shields=available_input_shields if available_input_shields else [],
        output_shields=available_output_shields if available_output_shields else [],
        tool_parser=None if no_tools else GraniteToolParser.get_parser(model_id),
        enable_session_persistence=True,
    )
    await agent.initialize()

    if existing_agent_id and conversation_id:
        logger.debug("Existing conversation ID: %s", conversation_id)
        logger.debug("Existing agent ID: %s", existing_agent_id)
        orphan_agent_id = agent.agent_id
        agent._agent_id = conversation_id  # type: ignore[assignment]  # pylint: disable=protected-access
        await client.agents.delete(agent_id=orphan_agent_id)
        sessions_response = await client.agents.session.list(agent_id=conversation_id)
        logger.info("session response: %s", sessions_response)
        try:
            session_id = str(sessions_response.data[0]["session_id"])
        except IndexError as e:
            logger.error("No sessions found for conversation %s", conversation_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "response": "Conversation not found",
                    "cause": f"Conversation {conversation_id} could not be retrieved.",
                },
            ) from e
    else:
        conversation_id = agent.agent_id
        logger.debug("New conversation ID: %s", conversation_id)
        session_id = await agent.create_session(get_suid())
        logger.debug("New session ID: %s", session_id)

    return agent, conversation_id, session_id


async def get_temp_agent(
    client: AsyncLlamaStackClient,
    model_id: str,
    system_prompt: str,
) -> tuple[AsyncAgent, str, str]:
    """Create a temporary agent with new agent_id and session_id.

    This function creates a new agent without persistence, shields, or tools.
    Useful for temporary operations or one-off queries, such as validating a
    question or generating a summary.
    Args:
        client: The AsyncLlamaStackClient to use for the request.
        model_id: The ID of the model to use.
        system_prompt: The system prompt/instructions for the agent.
    Returns:
        tuple[AsyncAgent, str]: A tuple containing the agent and session_id.
    """
    logger.debug("Creating temporary agent")
    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        enable_session_persistence=False,  # Temporary agent doesn't need persistence
    )
    await agent.initialize()

    # Generate new IDs for the temporary agent
    conversation_id = agent.agent_id
    session_id = await agent.create_session(get_suid())

    return agent, session_id, conversation_id


def create_rag_chunks_dict(summary: TurnSummary) -> list[dict[str, Any]]:
    """
    Create dictionary representation of RAG chunks for streaming response.

    Args:
        summary: TurnSummary containing RAG chunks

    Returns:
        List of dictionaries with content, source, and score
    """
    return [
        {"content": chunk.content, "source": chunk.source, "score": chunk.score}
        for chunk in summary.rag_chunks
    ]


def _process_http_source(
    src: str, doc_urls: set[str]
) -> tuple[AnyUrl | None, str] | None:
    """Process HTTP source and return (doc_url, doc_title) tuple."""
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
    metadata_map: dict[str, Any] | None,
) -> tuple[AnyUrl | None, str] | None:
    """Process document ID and return (doc_url, doc_title) tuple."""
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
) -> list[tuple[AnyUrl | None, str]]:
    """Add additional referenced documents from metadata_map."""
    additional_entries: list[tuple[AnyUrl | None, str]] = []
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
    metadata_map: dict[str, Any] | None = None,
) -> list[tuple[AnyUrl | None, str]]:
    """
    Process RAG chunks and return a list of (doc_url, doc_title) tuples.

    This is the core logic shared between both return formats.
    """
    doc_urls: set[str] = set()
    doc_ids: set[str] = set()

    # Process metadata_map if provided
    metas_by_id: dict[str, dict[str, Any]] = {}
    if metadata_map:
        metas_by_id = {k: v for k, v in metadata_map.items() if isinstance(v, dict)}

    document_entries: list[tuple[AnyUrl | None, str]] = []

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
    metadata_map: dict[str, Any] | None = None,
    return_dict_format: bool = False,
) -> list[ReferencedDocument] | list[dict[str, str | None]]:
    """
    Create referenced documents from RAG chunks with optional metadata enrichment.

    This unified function processes RAG chunks and creates referenced documents with
    optional metadata enrichment, deduplication, and proper URL handling. It can return
    either ReferencedDocument objects (for query endpoint) or dictionaries (for streaming).

    Args:
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
    """
    document_entries = _process_rag_chunks_for_documents(rag_chunks)
    return [
        ReferencedDocument(doc_url=doc_url, doc_title=doc_title)
        for doc_url, doc_title in document_entries
    ]
