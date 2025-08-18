"""Handler for REST API call to provide answer to query."""

from datetime import datetime, UTC
import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, cast

import pydantic

from llama_stack_client import APIConnectionError
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.types import UserMessage, Shield  # type: ignore
from llama_stack_client.types.agents.turn_create_params import (
    ToolgroupAgentToolGroupWithArgs,
    Toolgroup,
)
from llama_stack_client.types.model_list_response import ModelListResponse

from fastapi import APIRouter, HTTPException, status, Depends

from auth import get_auth_dependency
from auth.interface import AuthTuple
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from app.database import get_session
import metrics
from models.database.conversations import UserConversation
from models.responses import (
    QueryResponse,
    UnauthorizedResponse,
    ForbiddenResponse,
    ReferencedDocument,
)
from models.requests import QueryRequest, Attachment
import constants
from utils.endpoints import (
    check_configuration_loaded,
    get_agent,
    get_system_prompt,
    validate_conversation_ownership,
)
from utils.mcp_headers import mcp_headers_dependency, handle_mcp_headers_with_toolgroups
from utils.suid import get_suid
from utils.metadata import parse_knowledge_search_metadata

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])
auth_dependency = get_auth_dependency()


def _process_knowledge_search_content(tool_response: Any) -> dict[str, dict[str, Any]]:
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

    # Ensure content is iterable
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
            parsed_metadata = parse_knowledge_search_metadata(text)
            metadata_map.update(parsed_metadata)
        except ValueError:
            logger.exception(
                "An exception was thrown in processing metadata from text: %s",
                text[:200] + "..." if len(text) > 200 else text,
            )

    return metadata_map


def extract_referenced_documents_from_steps(
    steps: list[Any],
) -> list[ReferencedDocument]:
    """Extract referenced documents from tool execution steps.

    Args:
        steps: List of response steps from the agent

    Returns:
        List of referenced documents with doc_url and doc_title
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

            response_metadata = _process_knowledge_search_content(tool_response)
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

    return referenced_documents


query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "response": "LLM answer",
        "referenced_documents": [
            {
                "doc_url": (
                    "https://docs.openshift.com/container-platform/"
                    "4.15/operators/olm/index.html"
                ),
                "doc_title": "Operator Lifecycle Manager (OLM)",
            }
        ],
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
    500: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
    },
}


def is_transcripts_enabled() -> bool:
    """Check if transcripts is enabled.

    Returns:
        bool: True if transcripts is enabled, False otherwise.
    """
    return configuration.user_data_collection_configuration.transcripts_enabled


def persist_user_conversation_details(
    user_id: str, conversation_id: str, model: str, provider_id: str
) -> None:
    """Associate conversation to user in the database."""
    with get_session() as session:
        existing_conversation = (
            session.query(UserConversation)
            .filter_by(id=conversation_id, user_id=user_id)
            .first()
        )

        if not existing_conversation:
            conversation = UserConversation(
                id=conversation_id,
                user_id=user_id,
                last_used_model=model,
                last_used_provider=provider_id,
                message_count=1,
            )
            session.add(conversation)
            logger.debug(
                "Associated conversation %s to user %s", conversation_id, user_id
            )
        else:
            existing_conversation.last_used_model = model
            existing_conversation.last_used_provider = provider_id
            existing_conversation.last_message_at = datetime.now(UTC)
            existing_conversation.message_count += 1

        session.commit()


def evaluate_model_hints(
    user_conversation: UserConversation | None,
    query_request: QueryRequest,
) -> tuple[str | None, str | None]:
    """Evaluate model hints from user conversation."""
    model_id: str | None = query_request.model
    provider_id: str | None = query_request.provider

    if user_conversation is not None:
        if query_request.model is not None:
            if query_request.model != user_conversation.last_used_model:
                logger.debug(
                    "Model specified in request: %s, preferring it over user conversation model %s",
                    query_request.model,
                    user_conversation.last_used_model,
                )
        else:
            logger.debug(
                "No model specified in request, using latest model from user conversation: %s",
                user_conversation.last_used_model,
            )
            model_id = user_conversation.last_used_model

        if query_request.provider is not None:
            if query_request.provider != user_conversation.last_used_provider:
                logger.debug(
                    "Provider specified in request: %s, "
                    "preferring it over user conversation provider %s",
                    query_request.provider,
                    user_conversation.last_used_provider,
                )
        else:
            logger.debug(
                "No provider specified in request, "
                "using latest provider from user conversation: %s",
                user_conversation.last_used_provider,
            )
            provider_id = user_conversation.last_used_provider

    return model_id, provider_id


@router.post("/query", responses=query_response)
async def query_endpoint_handler(
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """
    Handle request to the /query endpoint.

    Processes a POST request to the /query endpoint, forwarding the
    user's query to a selected Llama Stack LLM or agent and
    returning the generated response.

    Validates configuration and authentication, selects the appropriate model
    and provider, retrieves the LLM response, updates metrics, and optionally
    stores a transcript of the interaction. Handles connection errors to the
    Llama Stack service by returning an HTTP 500 error.

    Returns:
        QueryResponse: Contains the conversation ID and the LLM-generated response.
    """
    check_configuration_loaded(configuration)

    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)

    user_id, _, token = auth

    user_conversation: UserConversation | None = None
    if query_request.conversation_id:
        user_conversation = validate_conversation_ownership(
            user_id=user_id, conversation_id=query_request.conversation_id
        )

        if user_conversation is None:
            logger.warning(
                "User %s attempted to query conversation %s they don't own",
                user_id,
                query_request.conversation_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "response": "Access denied",
                    "cause": "You do not have permission to access this conversation",
                },
            )

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
            await client.models.list(),
            *evaluate_model_hints(
                user_conversation=user_conversation, query_request=query_request
            ),
        )
        response, conversation_id, referenced_documents = await retrieve_response(
            client,
            llama_stack_model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
        )
        # Update metrics for the LLM call
        metrics.llm_calls_total.labels(provider_id, model_id).inc()

        if not is_transcripts_enabled():
            logger.debug("Transcript collection is disabled in the configuration")
        else:
            store_transcript(
                user_id=user_id,
                conversation_id=conversation_id,
                model_id=model_id,
                provider_id=provider_id,
                query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                query=query_request.query,
                query_request=query_request,
                response=response,
                rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model_id,
            provider_id=provider_id,
        )

        return QueryResponse(
            conversation_id=conversation_id,
            response=response,
            referenced_documents=referenced_documents,
        )

    # connection to Llama Stack server
    except APIConnectionError as e:
        # Update metrics for the LLM call failure
        metrics.llm_calls_failures_total.inc()
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e


def select_model_and_provider_id(
    models: ModelListResponse, model_id: str | None, provider_id: str | None
) -> tuple[str, str, str]:
    """
    Select the model ID and provider ID based on the request or available models.

    Determine and return the appropriate model and provider IDs for
    a query request.

    If the request specifies both model and provider IDs, those are used.
    Otherwise, defaults from configuration are applied. If neither is
    available, selects the first available LLM model from the provided model
    list. Validates that the selected model exists among the available models.

    Returns:
        A tuple containing the combined model ID (in the format
        "provider/model") and the provider ID.

    Raises:
        HTTPException: If no suitable LLM model is found or the selected model is not available.
    """
    # If model_id and provider_id are provided in the request, use them

    # If model_id is not provided in the request, check the configuration
    if not model_id or not provider_id:
        logger.debug(
            "No model ID or provider ID specified in request, checking configuration"
        )
        model_id = configuration.inference.default_model  # type: ignore[reportAttributeAccessIssue]
        provider_id = (
            configuration.inference.default_provider  # type: ignore[reportAttributeAccessIssue]
        )

    # If no model is specified in the request or configuration, use the first available LLM
    if not model_id or not provider_id:
        logger.debug(
            "No model ID or provider ID specified in request or configuration, "
            "using the first available LLM"
        )
        try:
            model = next(
                m
                for m in models
                if m.model_type == "llm"  # pyright: ignore[reportAttributeAccessIssue]
            )
            model_id = model.identifier
            provider_id = model.provider_id
            logger.info("Selected model: %s", model)
            return model_id, model_id, provider_id
        except (StopIteration, AttributeError) as e:
            message = "No LLM model found in available models"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            ) from e

    llama_stack_model_id = f"{provider_id}/{model_id}"
    # Validate that the model_id and provider_id are in the available models
    logger.debug("Searching for model: %s, provider: %s", model_id, provider_id)
    if not any(
        m.identifier == llama_stack_model_id and m.provider_id == provider_id
        for m in models
    ):
        message = f"Model {model_id} from provider {provider_id} not found in available models"
        logger.error(message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                "cause": message,
            },
        )

    return llama_stack_model_id, model_id, provider_id


def _is_inout_shield(shield: Shield) -> bool:
    """
    Determine if the shield identifier indicates an input/output shield.

    Parameters:
        shield (Shield): The shield to check.

    Returns:
        bool: True if the shield identifier starts with "inout_", otherwise False.
    """
    return shield.identifier.startswith("inout_")


def is_output_shield(shield: Shield) -> bool:
    """
    Determine if the shield is for monitoring output.

    Return True if the given shield is classified as an output or
    inout shield.

    A shield is considered an output shield if its identifier
    starts with "output_" or "inout_".
    """
    return _is_inout_shield(shield) or shield.identifier.startswith("output_")


def is_input_shield(shield: Shield) -> bool:
    """
    Determine if the shield is for monitoring input.

    Return True if the shield is classified as an input or inout
    shield.

    Parameters:
        shield (Shield): The shield identifier to classify.

    Returns:
        bool: True if the shield is for input or both input/output monitoring; False otherwise.
    """
    return _is_inout_shield(shield) or not is_output_shield(shield)


async def retrieve_response(  # pylint: disable=too-many-locals,too-many-branches
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str, list[ReferencedDocument]]:
    """
    Retrieve response from LLMs and agents.

    Retrieves a response from the Llama Stack LLM or agent for a
    given query, handling shield configuration, tool usage, and
    attachment validation.

    This function configures input/output shields, system prompts,
    and toolgroups (including RAG and MCP integration) as needed
    based on the query request and system configuration. It
    validates attachments, manages conversation and session
    context, and processes MCP headers for multi-component
    processing. Shield violations in the response are detected and
    corresponding metrics are updated.

    Parameters:
        model_id (str): The identifier of the LLM model to use.
        query_request (QueryRequest): The user's query and associated metadata.
        token (str): The authentication token for authorization.
        mcp_headers (dict[str, dict[str, str]], optional): Headers for multi-component processing.

    Returns:
        tuple[str, str]: A tuple containing the LLM or agent's response content
        and the conversation ID.
    """
    available_input_shields = [
        shield.identifier
        for shield in filter(is_input_shield, await client.shields.list())
    ]
    available_output_shields = [
        shield.identifier
        for shield in filter(is_output_shield, await client.shields.list())
    ]
    if not available_input_shields and not available_output_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info(
            "Available input shields: %s, output shields: %s",
            available_input_shields,
            available_output_shields,
        )
    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    agent, conversation_id, session_id = await get_agent(
        client,
        model_id,
        system_prompt,
        available_input_shields,
        available_output_shields,
        query_request.conversation_id,
        query_request.no_tools or False,
    )

    logger.debug("Conversation ID: %s, session ID: %s", conversation_id, session_id)
    # bypass tools and MCP servers if no_tools is True
    if query_request.no_tools:
        mcp_headers = {}
        agent.extra_headers = {}
        toolgroups = None
    else:
        # preserve compatibility when mcp_headers is not provided
        if mcp_headers is None:
            mcp_headers = {}
        mcp_headers = handle_mcp_headers_with_toolgroups(mcp_headers, configuration)
        if not mcp_headers and token:
            for mcp_server in configuration.mcp_servers:
                mcp_headers[mcp_server.url] = {
                    "Authorization": f"Bearer {token}",
                }

        agent.extra_headers = {
            "X-LlamaStack-Provider-Data": json.dumps(
                {
                    "mcp_headers": mcp_headers,
                }
            ),
        }

        vector_db_ids = [
            vector_db.identifier for vector_db in await client.vector_dbs.list()
        ]
        toolgroups = (get_rag_toolgroups(vector_db_ids) or []) + [
            mcp_server.name for mcp_server in configuration.mcp_servers
        ]
        # Convert empty list to None for consistency with existing behavior
        if not toolgroups:
            toolgroups = None

    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=False,
        toolgroups=toolgroups,
    )

    # Check for validation errors and extract referenced documents
    steps = getattr(response, "steps", [])
    for step in steps:
        if getattr(step, "step_type", "") == "shield_call" and getattr(
            step, "violation", False
        ):
            # Metric for LLM validation errors
            metrics.llm_calls_validation_errors_total.inc()

    # Extract referenced documents from tool execution steps
    referenced_documents = extract_referenced_documents_from_steps(steps)

    # When stream=False, response should have output_message attribute
    response_obj = cast(Any, response)

    # Safely guard access to output_message and content
    output_message = getattr(response_obj, "output_message", None)
    if output_message and getattr(output_message, "content", None) is not None:
        content_str = str(output_message.content)
    else:
        content_str = ""

    return (
        content_str,
        conversation_id,
        referenced_documents,
    )


def validate_attachments_metadata(attachments: list[Attachment]) -> None:
    """Validate the attachments metadata provided in the request.

    Raises:
        HTTPException: If any attachment has an invalid type or content type,
        an HTTP 422 error is raised.
    """
    for attachment in attachments:
        if attachment.attachment_type not in constants.ATTACHMENT_TYPES:
            message = (
                f"Attachment with improper type {attachment.attachment_type} detected"
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )
        if attachment.content_type not in constants.ATTACHMENT_CONTENT_TYPES:
            message = f"Attachment with improper content type {attachment.content_type} detected"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )


def construct_transcripts_path(user_id: str, conversation_id: str) -> Path:
    """
    Construct path to transcripts.

    Constructs a sanitized filesystem path for storing transcripts
    based on the user ID and conversation ID.

    Parameters:
        user_id (str): The user identifier, which will be normalized and sanitized.
        conversation_id (str): The conversation identifier, which will be normalized and sanitized.

    Returns:
        Path: The constructed path for storing transcripts for the specified user and conversation.
    """
    # these two normalizations are required by Snyk as it detects
    # this Path sanitization pattern
    uid = os.path.normpath("/" + user_id).lstrip("/")
    cid = os.path.normpath("/" + conversation_id).lstrip("/")
    file_path = (
        configuration.user_data_collection_configuration.transcripts_storage or ""
    )
    return Path(file_path, uid, cid)


def store_transcript(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str | None,
    query_is_valid: bool,
    query: str,
    query_request: QueryRequest,
    response: str,
    rag_chunks: list[str],
    truncated: bool,
    attachments: list[Attachment],
) -> None:
    """
    Store transcript in the local filesystem.

    Constructs a sanitized filesystem path for storing transcripts
    based on the user ID and conversation ID.

    Returns:
        Path: The constructed path for storing transcripts for the specified user and conversation.

    Args:
        user_id: The user ID (UUID).
        conversation_id: The conversation ID (UUID).
        query_is_valid: The result of the query validation.
        query: The query (without attachments).
        query_request: The request containing a query.
        response: The response to store.
        rag_chunks: The list of `RagChunk` objects.
        truncated: The flag indicating if the history was truncated.
        attachments: The list of `Attachment` objects.
    """
    transcripts_path = construct_transcripts_path(user_id, conversation_id)
    transcripts_path.mkdir(parents=True, exist_ok=True)

    data_to_store = {
        "metadata": {
            "provider": provider_id,
            "model": model_id,
            "query_provider": query_request.provider,
            "query_model": query_request.model,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "redacted_query": query,
        "query_is_valid": query_is_valid,
        "llm_response": response,
        "rag_chunks": rag_chunks,
        "truncated": truncated,
        "attachments": [attachment.model_dump() for attachment in attachments],
    }

    # stores feedback in a file under unique uuid
    transcript_file_path = transcripts_path / f"{get_suid()}.json"
    with open(transcript_file_path, "w", encoding="utf-8") as transcript_file:
        json.dump(data_to_store, transcript_file)

    logger.info("Transcript successfully stored at: %s", transcript_file_path)


def get_rag_toolgroups(
    vector_db_ids: list[str],
) -> list[Toolgroup] | None:
    """
    Return a list of RAG Tool groups if the given vector DB list is not empty.

    Generate a list containing a RAG knowledge search toolgroup if
    vector database IDs are provided.

    Parameters:
        vector_db_ids (list[str]): List of vector database identifiers to include in the toolgroup.

    Returns:
        list[Toolgroup] | None: A list with a single RAG toolgroup if
        vector_db_ids is non-empty; otherwise, None.
    """
    return (
        [
            ToolgroupAgentToolGroupWithArgs(
                name="builtin::rag/knowledge_search",
                args={
                    "vector_db_ids": vector_db_ids,
                },
            )
        ]
        if vector_db_ids
        else None
    )
