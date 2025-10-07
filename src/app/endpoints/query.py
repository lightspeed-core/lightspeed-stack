"""Handler for REST API call to provide answer to query."""

import ast
import json
import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,  # type: ignore
)
from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types import Shield, UserMessage  # type: ignore
from llama_stack_client.types.agents.turn import Turn
from llama_stack_client.types.agents.turn_create_params import (
    Toolgroup,
    ToolgroupAgentToolGroupWithArgs,
)
from llama_stack_client.types.model_list_response import ModelListResponse
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem
from llama_stack_client.types.tool_execution_step import ToolExecutionStep

import constants
import metrics
from app.database import get_session
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import Attachment, QueryRequest
from models.responses import (
    ForbiddenResponse,
    QueryResponse,
    ReferencedDocument,
    ToolCall,
    UnauthorizedResponse,
)
from utils.endpoints import (
    check_configuration_loaded,
    get_agent,
    get_topic_summary_system_prompt,
    get_temp_agent,
    get_system_prompt,
    store_conversation_into_cache,
    validate_conversation_ownership,
    validate_model_provider_override,
)
from utils.mcp_headers import handle_mcp_headers_with_toolgroups, mcp_headers_dependency
from utils.transcripts import store_transcript
from utils.types import TurnSummary
from utils.token_counter import extract_and_update_token_metrics, TokenCounter

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])

query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "response": "LLM answer",
        "referenced_documents": [
            {
                "doc_url": "https://docs.openshift.com/"
                "container-platform/4.15/operators/olm/index.html",
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
    user_id: str,
    conversation_id: str,
    model: str,
    provider_id: str,
    topic_summary: Optional[str],
) -> None:
    """Associate conversation to user in the database."""
    with get_session() as session:
        existing_conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )

        if not existing_conversation:
            conversation = UserConversation(
                id=conversation_id,
                user_id=user_id,
                last_used_model=model,
                last_used_provider=provider_id,
                topic_summary=topic_summary,
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


async def get_topic_summary(
    question: str, client: AsyncLlamaStackClient, model_id: str
) -> str:
    """Get a topic summary for a question.

    Args:
        question: The question to be validated.
        client: The AsyncLlamaStackClient to use for the request.
        model_id: The ID of the model to use.
    Returns:
        str: The topic summary for the question.
    """
    topic_summary_system_prompt = get_topic_summary_system_prompt(configuration)
    agent, session_id, _ = await get_temp_agent(
        client, model_id, topic_summary_system_prompt
    )
    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=question)],
        session_id=session_id,
        stream=False,
        toolgroups=None,
    )
    response = cast(Turn, response)
    return (
        interleaved_content_as_str(response.output_message.content)
        if (
            getattr(response, "output_message", None) is not None
            and getattr(response.output_message, "content", None) is not None
        )
        else ""
    )


@router.post("/query", responses=query_response)
@authorize(Action.QUERY)
async def query_endpoint_handler(  # pylint: disable=R0914
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
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

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

    # log Llama Stack configuration
    logger.info("Llama stack config: %s", configuration.llama_stack_configuration)

    user_id, _, _skip_userid_check, token = auth

    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    user_conversation: UserConversation | None = None
    if query_request.conversation_id:
        logger.debug(
            "Conversation ID specified in query: %s", query_request.conversation_id
        )
        user_conversation = validate_conversation_ownership(
            user_id=user_id,
            conversation_id=query_request.conversation_id,
            others_allowed=(
                Action.QUERY_OTHERS_CONVERSATIONS in request.state.authorized_actions
            ),
        )

        if user_conversation is None:
            logger.warning(
                "Conversation %s not found for user %s",
                query_request.conversation_id,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "response": "Conversation not found",
                    "cause": "The requested conversation does not exist.",
                },
            )
    else:
        logger.debug("Query does not contain conversation ID")

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
            await client.models.list(),
            *evaluate_model_hints(
                user_conversation=user_conversation, query_request=query_request
            ),
        )
        summary, conversation_id, referenced_documents, token_usage = (
            await retrieve_response(
                client,
                llama_stack_model_id,
                query_request,
                token,
                mcp_headers=mcp_headers,
                provider_id=provider_id,
            )
        )

        # Get the initial topic summary for the conversation
        topic_summary = None
        with get_session() as session:
            existing_conversation = (
                session.query(UserConversation).filter_by(id=conversation_id).first()
            )
            if not existing_conversation:
                topic_summary = await get_topic_summary(
                    query_request.query, client, model_id
                )
        # Convert RAG chunks to dictionary format once for reuse
        logger.info("Processing RAG chunks...")
        rag_chunks_dict = [chunk.model_dump() for chunk in summary.rag_chunks]

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
                summary=summary,
                rag_chunks=rag_chunks_dict,
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

        logger.info("Persisting conversation details...")
        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model_id,
            provider_id=provider_id,
            topic_summary=topic_summary,
        )

        completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        store_conversation_into_cache(
            configuration,
            user_id,
            conversation_id,
            provider_id,
            model_id,
            query_request.query,
            summary.llm_response,
            started_at,
            completed_at,
            _skip_userid_check,
            topic_summary,
        )

        # Convert tool calls to response format
        logger.info("Processing tool calls...")
        tool_calls = [
            ToolCall(
                tool_name=tc.name,
                arguments=(
                    tc.args if isinstance(tc.args, dict) else {"query": str(tc.args)}
                ),
                result=(
                    {"response": tc.response}
                    if tc.response and tc.name != constants.DEFAULT_RAG_TOOL
                    else None
                ),
            )
            for tc in summary.tool_calls
        ]

        logger.info("Using referenced documents from response...")

        logger.info("Building final response...")
        response = QueryResponse(
            conversation_id=conversation_id,
            response=summary.llm_response,
            rag_chunks=summary.rag_chunks if summary.rag_chunks else [],
            tool_calls=tool_calls if tool_calls else None,
            referenced_documents=referenced_documents,
            truncated=False,  # TODO: implement truncation detection
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            available_quotas={},  # TODO: implement quota tracking
        )
        logger.info("Query processing completed successfully!")
        return response

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
        "provider/model"), and its separated parts: the model label and the provider ID.

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
            model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
            return model_id, model_label, provider_id
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


def parse_metadata_from_text_item(
    text_item: TextContentItem,
) -> Optional[ReferencedDocument]:
    """
    Parse a single TextContentItem to extract referenced documents.

    Args:
        text_item (TextContentItem): The TextContentItem containing metadata.

    Returns:
        ReferencedDocument: A ReferencedDocument object containing 'doc_url' and 'doc_title'
        representing the referenced documents found in the metadata.
    """
    docs: list[ReferencedDocument] = []
    if not isinstance(text_item, TextContentItem):
        return docs

    metadata_blocks = re.findall(
        r"Metadata:\s*({.*?})(?:\n|$)", text_item.text, re.DOTALL
    )
    for block in metadata_blocks:
        try:
            data = ast.literal_eval(block)
            url = data.get("docs_url")
            title = data.get("title")
            if url and title:
                return ReferencedDocument(doc_url=url, doc_title=title)
            logger.debug("Invalid metadata block (missing url or title): %s", block)
        except (ValueError, SyntaxError) as e:
            logger.debug("Failed to parse metadata block: %s | Error: %s", block, e)
    return None


def parse_referenced_documents(response: Turn) -> list[ReferencedDocument]:
    """
    Parse referenced documents from Turn.

    Iterate through the steps of a response and collect all referenced
    documents from rag tool responses.

    Args:
        response(Turn): The response object from the agent turn.

    Returns:
        list[ReferencedDocument]: A list of ReferencedDocument, each with 'doc_url' and 'doc_title'
        representing all referenced documents found in the response.
    """
    docs = []
    for step in response.steps:
        if not isinstance(step, ToolExecutionStep):
            continue
        for tool_response in step.tool_responses:
            if tool_response.tool_name != constants.DEFAULT_RAG_TOOL:
                continue
            for text_item in tool_response.content:
                if not isinstance(text_item, TextContentItem):
                    continue
                doc = parse_metadata_from_text_item(text_item)
                if doc:
                    docs.append(doc)
    return docs


async def retrieve_response(  # pylint: disable=too-many-locals,too-many-branches,too-many-arguments
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
    *,
    provider_id: str = "",
) -> tuple[TurnSummary, str, list[ReferencedDocument], TokenCounter]:
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
        provider_id (str): The identifier of the LLM provider to use.
        query_request (QueryRequest): The user's query and associated metadata.
        token (str): The authentication token for authorization.
        mcp_headers (dict[str, dict[str, str]], optional): Headers for multi-component processing.

    Returns:
        tuple[TurnSummary, str, list[ReferencedDocument], TokenCounter]: A tuple containing
        a summary of the LLM or agent's response
        content, the conversation ID, the list of parsed referenced documents, and token usage information.
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
    response = cast(Turn, response)

    summary = TurnSummary(
        llm_response=(
            interleaved_content_as_str(response.output_message.content)
            if (
                getattr(response, "output_message", None) is not None
                and getattr(response.output_message, "content", None) is not None
            )
            else ""
        ),
        tool_calls=[],
    )

    referenced_documents = parse_referenced_documents(response)

    # Update token count metrics and extract token usage in one call
    model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
    token_usage = extract_and_update_token_metrics(
        response, model_label, provider_id, system_prompt
    )

    # Check for validation errors in the response
    steps = response.steps or []
    for step in steps:
        if step.step_type == "shield_call" and step.violation:
            # Metric for LLM validation errors
            metrics.llm_calls_validation_errors_total.inc()
        if step.step_type == "tool_execution":
            summary.append_tool_calls_from_llama(step)

    if not summary.llm_response:
        logger.warning(
            "Response lacks output_message.content (conversation_id=%s)",
            conversation_id,
        )
    return (summary, conversation_id, referenced_documents, token_usage)


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
