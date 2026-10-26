import sqlite3
from collections.abc import AsyncIterator, Mapping
from typing import Optional

import psycopg2
from ag_ui.core import (
    BaseEvent,
    RunAgentInput,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from fastapi import HTTPException
from ogx_client import ApiException, AsyncOgxClient
from pydantic_ai import RunUsage
from pydantic_ai.messages import NativeToolReturnPart
from pydantic_ai.output import OutputDataT
from pydantic_ai.tools import AgentDepsT
from pydantic_ai.ui import UIEventStream
from pydantic_ai.ui.ag_ui import AGUIAdapter, AGUIEventStream

from configuration import configuration
from log import get_logger
from models.api.requests.agui import AGUIForwardedProps
from models.api.responses.error.internal import InternalServerErrorResponse
from models.api.responses.error.not_found import NotFoundResponse
from models.api.responses.error.service_unavailable import ServiceUnavailableResponse
from models.common.responses.responses_api_params import ResponsesApiParams
from models.database.conversations import UserConversation
from utils.mcp.mcp_headers import McpHeaders
from utils.prompts import get_system_prompt
from utils.query import (
    extract_provider_and_model_from_model_id,
    normalize_vertex_ai_model_id,
)
from utils.quota_utils import consume_tokens
from utils.responses import (
    apply_reasoning_for_resolved_tools,
    build_provider_data_headers,
    check_model_configured,
    prepare_tools,
    select_model_for_responses,
)
from utils.token_counter import TokenCounter

logger = get_logger(__name__)


# Tweak to work with OGX will be removed when the Pydantic AI migration is done
async def prepare_responses_params(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    client: AsyncOgxClient,
    agui_forwarded_props: AGUIForwardedProps,
    user_conversation: Optional[UserConversation],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    stream: bool = False,
    store: bool = True,
    request_headers: Optional[Mapping[str, str]] = None,
) -> ResponsesApiParams:
    """Prepare API request parameters for Responses API.

    Args:
        client: The AsyncOgxClient instance (must be initialized by caller)
        query_request: The query request containing the user's question
        user_conversation: The user conversation if conversation_id was provided, None otherwise
        token: The authentication token for authorization
        mcp_headers: Optional MCP headers for multi-component processing
        stream: Whether to stream the response
        store: Whether to store the response
        request_headers: Incoming HTTP request headers for allowlist propagation
        inline_rag_context: Optional RAG context to inject into the query before
            sending to the LLM. Passed separately to keep QueryRequest a pure public
            API model.

    Returns:
        ResponsesApiParams containing all prepared parameters for the API request

    """
    request_model = (
        f"{agui_forwarded_props.provider}/{agui_forwarded_props.model}"
        if agui_forwarded_props.model and agui_forwarded_props.provider
        else None
    )
    model = await select_model_for_responses(request_model, client, user_conversation)

    if not await check_model_configured(client, model):
        _, model_id = extract_provider_and_model_from_model_id(model)
        error_response = NotFoundResponse(resource="model", resource_id=model_id)
        raise HTTPException(**error_response.model_dump())

    # Use system prompt from request or default one
    system_prompt = get_system_prompt(agui_forwarded_props.system_prompt)
    logger.debug("Using system prompt: %s", system_prompt)

    # Prepare tools for responses API
    tools = await prepare_tools(
        agui_forwarded_props.vector_store_ids,
        agui_forwarded_props.no_tools,
        token,
        mcp_headers,
        request_headers,
    )

    # TODO: ResponseApiParams should not impose conversation to be set it's optional at OGX side
    # No conversation_id provided - create a new conversation first
    try:
        conversation = await client.conversations.create(metadata={})
    except ApiException as e:
        if not e.status:
            error_response = ServiceUnavailableResponse(
                backend_name="OGX",
            )
            raise HTTPException(**error_response.model_dump()) from e
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e

    ogx_conv_id = conversation.id
    logger.info(
        "Created new conversation with ID: %s",
        ogx_conv_id,
    )

    # Build X-OGX-Provider-Data header from MCP tool headers
    extra_headers = build_provider_data_headers(tools)

    # Normalize Vertex AI model IDs to work around OGX 0.6.x bug
    normalized_model = normalize_vertex_ai_model_id(model)

    # Known LLS bug: https://redhat.atlassian.net/browse/LCORE-1583
    reasoning = apply_reasoning_for_resolved_tools(
        None, tools, normalized_model, configuration.skills
    )

    # User input is not provided here
    return ResponsesApiParams(
        input="",
        model=normalized_model,
        instructions=system_prompt,
        tools=tools,
        conversation=ogx_conv_id,
        stream=stream,
        store=store,
        extra_headers=extra_headers,
        max_infer_iters=configuration.inference.max_infer_iters,
        max_tool_calls=configuration.inference.max_tool_calls,
        reasoning=reasoning,
    )


def consume_token_usage(usage: RunUsage, user_id: str, model_id: str):
    token_counter = TokenCounter.from_run_usage(usage)
    provider, model = extract_provider_and_model_from_model_id(model_id)

    try:
        logger.info("Consuming tokens")
        consume_tokens(
            quota_limiters=configuration.quota_limiters,
            token_usage_history=configuration.token_usage_history,
            user_id=user_id,
            input_tokens=token_counter.input_tokens,
            output_tokens=token_counter.output_tokens,
            model_id=model,
            provider_id=provider,
        )
    except (psycopg2.Error, sqlite3.Error, ValueError) as e:
        logger.exception("Error consuming tokens: %s", e)
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e


class LightspeedAGUIEventStream(AGUIEventStream[AgentDepsT, OutputDataT]):
    """AG-UI event stream with lightspeed-specific overrides."""

    _text_was_emitted: bool = False

    # The logic here is to catch the violation message. But, we also have to fix the problem that
    # during wrap_run the AGUI does not provide ctx.prompt and the most current user prompt is in
    # the ctx.messages
    async def handle_text_start(self, part, follows_text=False):
        """Track whether any text was emitted during the stream."""
        self._text_was_emitted = True
        async for e in super().handle_text_start(part, follows_text):
            yield e

    async def handle_run_result(self, event):
        if (
            not self._text_was_emitted
            and isinstance(event.result.output, str)
            and event.result.output
        ):
            msg_id = self.new_message_id()
            yield TextMessageStartEvent(message_id=msg_id)
            yield TextMessageContentEvent(message_id=msg_id, delta=event.result.output)
            yield TextMessageEndEvent(message_id=msg_id)

    # This is make the a2ui tool call work. The native tool call in OGX will wrap the whole content inside
    # "output" field, so we need to distruct it. After we migrate to Pydantic AI, we can remove this.
    async def handle_builtin_tool_return(
        self, part: NativeToolReturnPart
    ) -> AsyncIterator[BaseEvent]:
        """Unwrap server-side MCP tool results.

        OGX handles MCP calls server-side and returns them as McpCall items.
        pydantic-ai's _map_mcp_call wraps the result in {"output": ..., "error": ...}.
        This override extracts the raw output so AG-UI clients receive the same
        format as client-side MCPToolset calls.
        """
        if isinstance(part.content, dict) and "output" in part.content:
            part.content = part.content["output"]
        async for event in super().handle_builtin_tool_return(part):
            yield event


class LightspeedAGUIAdapter(AGUIAdapter[AgentDepsT, OutputDataT]):
    def build_event_stream(
        self,
    ) -> UIEventStream[RunAgentInput, BaseEvent, AgentDepsT, OutputDataT]:
        return LightspeedAGUIEventStream(
            self.run_input, accept=self.accept, ag_ui_version=self.ag_ui_version
        )
