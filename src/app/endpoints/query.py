"""Handler for REST API call to provide answer to query."""

from contextlib import suppress
from datetime import datetime, UTC
import json
import logging
import os
from pathlib import Path
from typing import Any

from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client import APIConnectionError
from llama_stack_client import LlamaStackClient  # type: ignore
from llama_stack_client.types import UserMessage, Shield  # type: ignore
from llama_stack_client.types.agents.turn_create_params import (
    ToolgroupAgentToolGroupWithArgs,
    Toolgroup,
)
from llama_stack_client.types.model_list_response import ModelListResponse

from fastapi import APIRouter, HTTPException, status, Depends

from client import LlamaStackClientHolder
from configuration import configuration
import metrics
from models.responses import QueryResponse, UnauthorizedResponse, ForbiddenResponse
from models.requests import QueryRequest, Attachment
import constants
from auth import get_auth_dependency
from utils.common import retrieve_user_id
from utils.endpoints import check_configuration_loaded, get_system_prompt
from utils.mcp_headers import mcp_headers_dependency, handle_mcp_headers_with_toolgroups
from utils.suid import get_suid
from utils.types import GraniteToolParser

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])
auth_dependency = get_auth_dependency()

query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "response": "LLM ansert",
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
    503: {
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


def get_agent(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: LlamaStackClient,
    model_id: str,
    system_prompt: str,
    available_input_shields: list[str],
    available_output_shields: list[str],
    conversation_id: str | None,
    no_tools: bool = False,
) -> tuple[Agent, str, str]:
    """Get existing agent or create a new one with session persistence."""
    existing_agent_id = None
    if conversation_id:
        with suppress(ValueError):
            existing_agent_id = client.agents.retrieve(
                agent_id=conversation_id
            ).agent_id

    logger.debug("Creating new agent")
    # TODO(lucasagomes): move to ReActAgent
    agent = Agent(
        client,
        model=model_id,
        instructions=system_prompt,
        input_shields=available_input_shields if available_input_shields else [],
        output_shields=available_output_shields if available_output_shields else [],
        tool_parser=None if no_tools else GraniteToolParser.get_parser(model_id),
        enable_session_persistence=True,
    )
    if existing_agent_id and conversation_id:
        orphan_agent_id = agent.agent_id
        agent.agent_id = conversation_id
        client.agents.delete(agent_id=orphan_agent_id)
        sessions_response = client.agents.session.list(agent_id=conversation_id)
        logger.info("session response: %s", sessions_response)
        session_id = str(sessions_response.data[0]["session_id"])
    else:
        conversation_id = agent.agent_id
        session_id = agent.create_session(get_suid())

    return agent, conversation_id, session_id


@router.post("/query", responses=query_response)
def query_endpoint_handler(
    query_request: QueryRequest,
    auth: Any = Depends(auth_dependency),
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """Handle request to the /query endpoint."""
    check_configuration_loaded(configuration)

    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)

    _user_id, _user_name, token = auth

    try:
        # try to get Llama Stack client
        client = LlamaStackClientHolder().get_client()
        model_id, provider_id = select_model_and_provider_id(
            client.models.list(), query_request
        )
        response, conversation_id = retrieve_response(
            client,
            model_id,
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
                user_id=retrieve_user_id(auth),
                conversation_id=conversation_id,
                query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                query=query_request.query,
                query_request=query_request,
                response=response,
                rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

        return QueryResponse(conversation_id=conversation_id, response=response)

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
    models: ModelListResponse, query_request: QueryRequest
) -> tuple[str, str | None]:
    """Select the model ID and provider ID based on the request or available models."""
    # If model_id and provider_id are provided in the request, use them
    model_id = query_request.model
    provider_id = query_request.provider

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
            return model_id, provider_id
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

    return llama_stack_model_id, provider_id


def _is_inout_shield(shield: Shield) -> bool:
    return shield.identifier.startswith("inout_")


def is_output_shield(shield: Shield) -> bool:
    """Determine if the shield is for monitoring output."""
    return _is_inout_shield(shield) or shield.identifier.startswith("output_")


def is_input_shield(shield: Shield) -> bool:
    """Determine if the shield is for monitoring input."""
    return _is_inout_shield(shield) or not is_output_shield(shield)


def retrieve_response(  # pylint: disable=too-many-locals
    client: LlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str]:
    """Retrieve response from LLMs and agents."""
    available_input_shields = [
        shield.identifier for shield in filter(is_input_shield, client.shields.list())
    ]
    available_output_shields = [
        shield.identifier for shield in filter(is_output_shield, client.shields.list())
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

    agent, conversation_id, session_id = get_agent(
        client,
        model_id,
        system_prompt,
        available_input_shields,
        available_output_shields,
        query_request.conversation_id,
        query_request.no_tools or False,
    )

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

        vector_db_ids = [vector_db.identifier for vector_db in client.vector_dbs.list()]
        toolgroups = (get_rag_toolgroups(vector_db_ids) or []) + [
            mcp_server.name for mcp_server in configuration.mcp_servers
        ]
        # Convert empty list to None for consistency with existing behavior
        if not toolgroups:
            toolgroups = None

    response = agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=False,
        toolgroups=toolgroups,
    )

    # Check for validation errors in the response
    steps = getattr(response, "steps", [])
    for step in steps:
        if step.step_type == "shield_call" and step.violation:
            # Metric for LLM validation errors
            metrics.llm_calls_validation_errors_total.inc()
            break

    return str(response.output_message.content), conversation_id  # type: ignore[union-attr]


def validate_attachments_metadata(attachments: list[Attachment]) -> None:
    """Validate the attachments metadata provided in the request.

    Raises HTTPException if any attachment has an improper type or content type.
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
    """Construct path to transcripts."""
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
    query_is_valid: bool,
    query: str,
    query_request: QueryRequest,
    response: str,
    rag_chunks: list[str],
    truncated: bool,
    attachments: list[Attachment],
) -> None:
    """Store transcript in the local filesystem.

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
            "provider": query_request.provider,
            "model": query_request.model,
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
    """Return a list of RAG Tool groups if the given vector DB list is not empty."""
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
