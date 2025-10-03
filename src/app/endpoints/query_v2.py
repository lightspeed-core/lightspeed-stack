"""Handler for REST API call to provide answer to query using Response API."""

import logging
from typing import Annotated, Any, cast

from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client import APIConnectionError
from llama_stack.apis.agents.openai_responses import (
    OpenAIResponseObject,
)

from fastapi import APIRouter, HTTPException, Request, status, Depends

from app.endpoints.query import (
    evaluate_model_hints,
    is_transcripts_enabled,
    persist_user_conversation_details,
    query_response,
    select_model_and_provider_id,
    validate_attachments_metadata,
)
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
import metrics
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import QueryResponse
from utils.endpoints import (
    check_configuration_loaded,
    get_system_prompt,
    validate_model_provider_override,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.transcripts import store_transcript
from utils.types import TurnSummary, ToolCallSummary


logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query_v2"])
auth_dependency = get_auth_dependency()


@router.post("/query", responses=query_response)
@authorize(Action.QUERY)
async def query_endpoint_handler_v2(
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """
    Handle request to the /query endpoint using Response API.

    Processes a POST request to the /query endpoint, forwarding the
    user's query to a selected Llama Stack LLM using Response API
    and returning the generated response.

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

    user_id, _, _, token = auth

    user_conversation: UserConversation | None = None
    if query_request.conversation_id:
        # TODO: Implement conversation once Llama Stack supports its API
        pass

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


async def retrieve_response(  # pylint: disable=too-many-locals,too-many-branches
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
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
        query_request (QueryRequest): The user's query and associated metadata.
        token (str): The authentication token for authorization.
        mcp_headers (dict[str, dict[str, str]], optional): Headers for multi-component processing.

    Returns:
        tuple[TurnSummary, str]: A tuple containing a summary of the LLM or agent's response content
        and the conversation ID.
    """
    logger.info("Shields are not yet supported in Responses API. Disabling safety")

    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    # Prepare tools for responses API
    tools: list[dict[str, Any]] = []
    if not query_request.no_tools:
        # Get vector databases for RAG tools
        vector_db_ids = [
            vector_db.identifier for vector_db in await client.vector_dbs.list()
        ]

        # Add RAG tools if vector databases are available
        rag_tools = get_rag_tools(vector_db_ids)
        if rag_tools:
            tools.extend(rag_tools)

        # Add MCP server tools
        mcp_tools = get_mcp_tools(configuration.mcp_servers, token)
        if mcp_tools:
            tools.extend(mcp_tools)
            logger.debug(
                "Configured %d MCP tools: %s",
                len(mcp_tools),
                [tool.get("server_label", "unknown") for tool in mcp_tools],
            )

    # Create OpenAI response using responses API
    response = await client.responses.create(
        input=query_request.query,
        model=model_id,
        instructions=system_prompt,
        previous_response_id=query_request.conversation_id,
        tools=(cast(Any, tools) if tools else cast(Any, None)),
        stream=False,
        store=True,
    )
    response = cast(OpenAIResponseObject, response)

    logger.debug(
        "Received response with ID: %s, output items: %d",
        response.id,
        len(response.output),
    )
    # Return the response ID - client can use it for chaining if desired
    conversation_id = response.id

    # Process OpenAI response format
    llm_response = ""
    tool_calls: list[ToolCallSummary] = []

    for idx, output_item in enumerate(response.output):
        logger.debug(
            "Processing output item %d, type: %s", idx, type(output_item).__name__
        )

        if hasattr(output_item, "content") and output_item.content:
            # Extract text content from message output
            if isinstance(output_item.content, list):
                for content_item in output_item.content:
                    if hasattr(content_item, "text"):
                        llm_response += content_item.text
            elif hasattr(output_item.content, "text"):
                llm_response += output_item.content.text
            elif isinstance(output_item.content, str):
                llm_response += output_item.content

            if llm_response:
                logger.info(
                    "Model response content: '%s'",
                    (
                        llm_response[:200] + "..."
                        if len(llm_response) > 200
                        else llm_response
                    ),
                )

        # Process tool calls if present
        if hasattr(output_item, "tool_calls") and output_item.tool_calls:
            logger.debug(
                "Found %d tool calls in output item %d",
                len(output_item.tool_calls),
                idx,
            )
            for tool_idx, tool_call in enumerate(output_item.tool_calls):
                tool_name = (
                    tool_call.function.name
                    if hasattr(tool_call, "function")
                    else "unknown"
                )
                tool_args = (
                    tool_call.function.arguments
                    if hasattr(tool_call, "function")
                    else {}
                )

                logger.debug(
                    "Tool call %d - Name: %s, Args: %s",
                    tool_idx,
                    tool_name,
                    str(tool_args)[:100],
                )

                tool_calls.append(
                    ToolCallSummary(
                        id=(
                            tool_call.id
                            if hasattr(tool_call, "id")
                            else str(len(tool_calls))
                        ),
                        name=tool_name,
                        args=tool_args,
                        response=None,  # Tool responses would be in subsequent output items
                    )
                )

    logger.info(
        "Response processing complete - Tool calls: %d, Response length: %d chars",
        len(tool_calls),
        len(llm_response),
    )

    summary = TurnSummary(
        llm_response=llm_response,
        tool_calls=tool_calls,
    )

    # TODO(ltomasbo): update token count metrics for the LLM call
    # Update token count metrics for the LLM call
    # model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
    # update_llm_token_count_from_response(response, model_label, provider_id, system_prompt)

    if not summary.llm_response:
        logger.warning(
            "Response lacks content (conversation_id=%s)",
            conversation_id,
        )
    return summary, conversation_id


def get_rag_tools(vector_db_ids: list[str]) -> list[dict[str, Any]] | None:
    """Convert vector DB IDs to tools format for responses API."""
    if not vector_db_ids:
        return None

    return [
        {
            "type": "file_search",
            "vector_store_ids": vector_db_ids,
            "max_num_results": 10,
        }
    ]


def get_mcp_tools(mcp_servers: list, token: str | None = None) -> list[dict[str, Any]]:
    """Convert MCP servers to tools format for responses API."""
    tools = []
    for mcp_server in mcp_servers:
        tool_def = {
            "type": "mcp",
            "server_label": mcp_server.name,
            "server_url": mcp_server.url,
            "require_approval": "never",
        }

        # Add authentication if token provided (Response API format)
        if token:
            tool_def["headers"] = {"Authorization": f"Bearer {token}"}

        tools.append(tool_def)
    return tools


def process_transcript_and_persist_conversation(
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str,
    query_request: QueryRequest,
    summary: TurnSummary,
) -> None:
    """Process transcript storage and persist conversation details."""
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
