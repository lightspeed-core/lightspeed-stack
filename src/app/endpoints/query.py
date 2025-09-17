"""Handler for REST API call to provide answer to query using Agent API."""

import json
import logging
from typing import Annotated, cast

from llama_stack_client import APIConnectionError
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types import UserMessage  # type: ignore
from llama_stack_client.types.agents.turn import Turn
from llama_stack_client.types.agents.turn_create_params import (
    ToolgroupAgentToolGroupWithArgs,
    Toolgroup,
)

from fastapi import APIRouter, Request, Depends

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from client import AsyncLlamaStackClientHolder
from configuration import configuration
import metrics
from metrics.utils import update_llm_token_count_from_turn
from authorization.middleware import authorize
from models.config import Action
from models.requests import QueryRequest
from models.responses import QueryResponse
from utils.endpoints import (
    get_agent,
    get_system_prompt,
)
from utils.mcp_headers import mcp_headers_dependency, handle_mcp_headers_with_toolgroups
from utils.types import TurnSummary
from utils.query import (
    query_response,
    evaluate_model_hints,
    select_model_and_provider_id,
    is_input_shield,
    is_output_shield,
    validate_attachments_metadata,
    validate_query_request,
    handle_api_connection_error,
    process_transcript_and_persist_conversation,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])
auth_dependency = get_auth_dependency()


@router.post("/query", responses=query_response)
@authorize(Action.QUERY)
async def query_endpoint_handler(
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """
    Handle request to the /query endpoint using Agent API.

    Processes a POST request to the /query endpoint, forwarding the
    user's query to a selected Llama Stack LLM or agent using Agent API
    and returning the generated response.

    Validates configuration and authentication, selects the appropriate model
    and provider, retrieves the LLM response, updates metrics, and optionally
    stores a transcript of the interaction. Handles connection errors to the
    Llama Stack service by returning an HTTP 500 error.

    Returns:
        QueryResponse: Contains the conversation ID and the LLM-generated response.
    """
    # Validate request and get user info
    user_id, user_conversation, token = validate_query_request(
        request, query_request, auth
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
        summary, conversation_id = await retrieve_response(
            client,
            llama_stack_model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
            provider_id=provider_id,
        )
        # Update metrics for the LLM call
        metrics.llm_calls_total.labels(provider_id, model_id).inc()

        process_transcript_and_persist_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            model_id=model_id,
            provider_id=provider_id,
            query_request=query_request,
            summary=summary,
        )

        return QueryResponse(
            conversation_id=conversation_id,
            response=summary.llm_response,
        )

    # connection to Llama Stack server
    except APIConnectionError as e:
        handle_api_connection_error(e)


async def retrieve_response(  # pylint: disable=too-many-locals,too-many-branches,too-many-arguments
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
    *,
    provider_id: str = "",
) -> tuple[TurnSummary, str]:
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
        tuple[TurnSummary, str]: A tuple containing a summary of the LLM or agent's response content
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

    # Update token count metrics for the LLM call
    model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
    update_llm_token_count_from_turn(response, model_label, provider_id, system_prompt)

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
    return summary, conversation_id


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
