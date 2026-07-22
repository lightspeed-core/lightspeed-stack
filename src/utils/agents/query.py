"""Non-streaming agent helpers and shared turn-summary builders for agent runs."""

from __future__ import annotations

from enum import Enum
from typing import Optional, TypeAlias, cast

from fastapi import HTTPException
from ogx_client import APIConnectionError, APIStatusError, AsyncOgxClient
from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolReturnPart
from pydantic_ai.run import AgentRunResult
from pydantic_ai.usage import RunUsage

from configuration import configuration
from log import get_logger
from metrics import recording
from models.api.responses.error import (
    AbstractErrorResponse,
    InternalServerErrorResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
)
from models.common.agents import AgentTurnAccumulator
from models.common.moderation import ShieldModerationResult
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.common.turn_summary import TurnSummary
from utils.agents.tool_processor import (
    process_function_tool_call,
    process_function_tool_result,
    process_native_tool_call,
    process_native_tool_result,
)
from utils.conversations import append_turn_items_to_conversation
from utils.pydantic_ai_helpers import build_agent
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
)
from utils.responses import extract_vector_store_ids_from_tools
from utils.token_counter import TokenCounter

logger = get_logger(__name__)

AgentInferenceError: TypeAlias = (
    AgentRunError | APIStatusError | APIConnectionError | RuntimeError
)


class AgentFinishReason(str, Enum):
    """Finish reason for a completed agent model response."""

    CONTENT_FILTER = "content_filter"
    CANCELLED = "cancelled"
    SUCCESS = "stop"
    LENGTH = "length"
    ERROR = "error"


def map_agent_inference_error(
    exc: AgentInferenceError,
    model_id: str,
) -> AbstractErrorResponse:
    """Map agent run failures from pydantic-ai or Llama Stack to an LCS error response.

    Args:
        exc: Agent, HTTP status, connection, or context-length runtime error.
        model_id: Model identifier in provider/model format.

    Returns:
        Structured error response for HTTP or SSE error events.

    Raises:
        RuntimeError: Re-raised when ``exc`` is a non-agent ``RuntimeError`` that is
            not a recognized context-length failure.
    """
    match exc:
        case AgentRunError() as agent_exc:
            return map_pydantic_agent_run_error(agent_exc, model_id)
        case APIStatusError() as status_exc:
            return handle_known_apistatus_errors(status_exc, model_id)
        case APIConnectionError() as connection_exc:
            return ServiceUnavailableResponse(
                backend_name="OGX",
                cause=str(connection_exc),
            )
        case RuntimeError() as runtime_exc if is_context_length_error(str(runtime_exc)):
            return PromptTooLongResponse(model=model_id)
        case _:
            return InternalServerErrorResponse.generic()


def map_pydantic_agent_run_error(
    exc: AgentRunError, model_id: str
) -> AbstractErrorResponse:
    """Map pydantic-ai ``AgentRunError`` subclasses to LCS error responses.

    Args:
        exc: Agent exception to map.
        model_id: Model identifier in provider/model format.

    Returns:
        Structured error response for HTTP or SSE error events.
    """
    match exc:
        case ContentFilterError() as filter_exc:
            return InternalServerErrorResponse.query_failed(str(filter_exc))
        case IncompleteToolCall():
            return PromptTooLongResponse(model=model_id)
        case UnexpectedModelBehavior():
            logger.error("Unexpected model behavior: %s", exc, exc_info=True)
            return InternalServerErrorResponse.generic()
        case UsageLimitExceeded():
            return QuotaExceededResponse.model(model_id)
        case ModelHTTPError() as http_exc if is_context_length_error(str(http_exc)):
            return PromptTooLongResponse(model=model_id)
        case ModelHTTPError(status_code=429):
            return QuotaExceededResponse.model(model_id)
        case ModelHTTPError():
            return InternalServerErrorResponse.generic()
        case ModelAPIError() as api_exc:
            return ServiceUnavailableResponse(
                backend_name="OGX",
                cause=str(api_exc),
            )
        case _:
            return InternalServerErrorResponse.query_failed(str(exc))


def get_agent_finish_reason(response: ModelResponse) -> AgentFinishReason:
    """Get the finish reason from a completed agent model response.

    Args:
        response: Last model response from the agent run.

    Returns:
        Resolved finish reason.
    """
    raw_finish_reason = (response.provider_details or {}).get("finish_reason")
    if raw_finish_reason == "cancelled":
        return AgentFinishReason.CANCELLED
    if response.finish_reason is None:
        return AgentFinishReason.ERROR
    return AgentFinishReason(response.finish_reason)


def get_finish_reason_error(
    finish_reason: AgentFinishReason,
    model_id: str,
) -> AbstractErrorResponse:
    """Map a non-success agent finish reason to an LCS error response.

    Args:
        finish_reason: Resolved finish reason from :func:`get_agent_finish_reason`.
        model_id: Model identifier in provider/model format.

    Returns:
        Structured error response for HTTP or SSE error events.
    """
    match finish_reason:
        case AgentFinishReason.LENGTH:
            return PromptTooLongResponse(model=model_id)
        case AgentFinishReason.CONTENT_FILTER:
            return InternalServerErrorResponse.query_failed(
                "The model refused to generate a response due to content policy."
            )
        case AgentFinishReason.CANCELLED:
            return InternalServerErrorResponse.query_failed(
                "The response was cancelled before completion."
            )
        case _:
            return InternalServerErrorResponse.query_failed(
                "An unexpected error occurred while processing the request."
            )


def extract_agent_token_usage(
    usage: RunUsage,
    model: str,
    endpoint_path: str,
) -> TokenCounter:
    """Build token usage for a completed agent run and record related metrics.

    Args:
        usage: Run usage reported by the agent.
        model: Model identifier in provider/model format.
        endpoint_path: Endpoint path used for metric labeling.

    Returns:
        Aggregated token usage counter for the run.
    """
    provider_id, model_id = extract_provider_and_model_from_model_id(model)
    token_counter = TokenCounter(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        llm_calls=max(usage.requests, 1),
    )
    logger.debug(
        "Extracted token usage from agent run: input=%d, output=%d, requests=%d",
        token_counter.input_tokens,
        token_counter.output_tokens,
        usage.requests,
    )
    recording.record_llm_token_usage(
        provider_id,
        model_id,
        token_counter.input_tokens,
        token_counter.output_tokens,
        endpoint_path,
    )
    recording.record_llm_call(provider_id, model_id, endpoint_path)
    return token_counter


def build_turn_summary_from_agent_run(
    run_result: AgentRunResult[str],
    *,
    model_id: str,
    endpoint_path: str,
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> TurnSummary:
    """Build a turn summary from a completed agent run.

    Args:
        run_result: Completed agent run result.
        model_id: Model identifier in provider/model format.
        endpoint_path: Endpoint path used for metric labeling.
        vector_store_ids: Vector store IDs used for source mapping.
        rag_id_mapping: Mapping from vector store IDs to user-facing source labels.

    Returns:
        Turn summary with text, tools, RAG metadata, and token usage.

    Raises:
        HTTPException: When the run failed.
    """
    finish_reason = get_agent_finish_reason(run_result.response)
    if finish_reason != AgentFinishReason.SUCCESS:
        error_response = get_finish_reason_error(finish_reason, model_id)
        raise HTTPException(**error_response.model_dump())

    state = AgentTurnAccumulator(
        vector_store_ids=vector_store_ids,
        rag_id_mapping=rag_id_mapping,
        turn_summary=TurnSummary(),
    )

    for message in run_result.new_messages():
        if isinstance(message, ModelResponse):
            if message.text:
                state.turn_summary.llm_response = message.text
            for tool_call_part in message.tool_calls:
                process_function_tool_call(state, tool_call_part)
            for call_part, return_part in message.native_tool_calls:
                process_native_tool_call(state, call_part)
                process_native_tool_result(state, return_part)
        elif isinstance(message, ModelRequest):
            for request_part in message.parts:
                if isinstance(request_part, ToolReturnPart):
                    process_function_tool_result(state, request_part)

    state.turn_summary.id = run_result.response.provider_response_id or ""
    state.turn_summary.token_usage = extract_agent_token_usage(
        run_result.usage,
        model_id,
        endpoint_path,
    )
    return state.turn_summary


async def retrieve_agent_response(
    client: AsyncOgxClient,
    responses_params: ResponsesApiParams,
    moderation_result: ShieldModerationResult,
    endpoint_path: str,
    _original_input: Optional[ResponseInput] = None,
    no_tools: bool = False,
) -> TurnSummary:
    """Retrieve a turn summary from a blocking agent run.

    Mirrors :func:`app.endpoints.query.retrieve_response` for the agent path.

    Args:
        client: Llama Stack client for conversation persistence on moderation block.
        responses_params: Prepared Responses API parameters.
        moderation_result: Shield moderation outcome for the turn.
        endpoint_path: Endpoint path used for metric labeling.
        _original_input: Original user input before the explicit-input rewrite.
        no_tools: Whether to skip tool processing.
    Returns:
        Turn summary for the completed agent run.

    Raises:
        HTTPException: On moderation is not applicable; on agent or provider failure.
    """
    if moderation_result.decision == "blocked":
        await append_turn_items_to_conversation(
            client,
            responses_params.conversation,
            responses_params.input,
            [moderation_result.refusal_response],
        )
        return TurnSummary(
            id=moderation_result.moderation_id,
            llm_response=moderation_result.message,
        )
    try:
        agent = build_agent(
            client,
            responses_params,
            configuration.skills,
            shields=configuration.shields,
            no_tools=no_tools,
        )
        logger.debug("Starting agent non-streaming response processing")
        run_result = await agent.run(cast(str, responses_params.input))
    except (AgentRunError, APIStatusError, APIConnectionError, RuntimeError) as exc:
        response = map_agent_inference_error(exc, responses_params.model)
        raise HTTPException(**response.model_dump()) from exc

    vector_store_ids = extract_vector_store_ids_from_tools(responses_params.tools)
    rag_id_mapping = configuration.rag_id_mapping
    return build_turn_summary_from_agent_run(
        run_result,
        model_id=responses_params.model,
        endpoint_path=endpoint_path,
        vector_store_ids=vector_store_ids,
        rag_id_mapping=rag_id_mapping,
    )
