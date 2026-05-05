"""Splunk telemetry helpers for the Responses API endpoint.

Extracted from responses.py to reduce module size while keeping telemetry
functions co-located with the endpoint they serve.
"""

from datetime import UTC, datetime
from typing import Optional

from fastapi import BackgroundTasks

from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.responses_context import ResponsesContext
from models.common.turn_summary import TurnSummary
from observability import ResponsesEventData, build_responses_event
from observability.splunk import dispatch_splunk_event
from utils.suid import normalize_conversation_id

logger = get_logger(__name__)


def queue_responses_splunk_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    background_tasks: Optional[BackgroundTasks],
    input_text: str,
    response_text: str,
    conversation_id: str,
    model: str,
    rh_identity_context: tuple[str, str],
    inference_time: float,
    sourcetype: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    fire_and_forget: bool = False,
    user_agent: Optional[str] = None,
) -> None:
    """Build and queue a Splunk telemetry event for the responses endpoint.

    No-op when background_tasks is None and fire_and_forget is False
    (Splunk telemetry disabled).

    Args:
        background_tasks: FastAPI background task manager, or None if disabled.
        input_text: User input text.
        response_text: Response text from LLM or shield.
        conversation_id: Conversation identifier.
        model: Model name used for inference.
        rh_identity_context: Tuple of (org_id, system_id) from RH identity.
        inference_time: Request processing duration in seconds.
        sourcetype: Splunk sourcetype for the event.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens produced.
        fire_and_forget: When True, dispatch via asyncio.create_task() instead
            of background_tasks.  Use for error paths where an HTTPException
            follows, since FastAPI discards BackgroundTasks on non-2xx responses.
        user_agent: Sanitized User-Agent string from the request header, or None.
    """
    if not fire_and_forget and background_tasks is None:
        return
    event_data = ResponsesEventData(
        input_text=input_text,
        response_text=response_text,
        conversation_id=conversation_id,
        model=model,
        org_id=rh_identity_context[0],
        system_id=rh_identity_context[1],
        inference_time=inference_time,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        user_agent=user_agent,
    )
    event = build_responses_event(event_data)
    dispatch_splunk_event(
        event,
        sourcetype,
        background_tasks=background_tasks,
        fire_and_forget=fire_and_forget,
    )


def queue_responses_error_event(
    error: Exception,
    api_params: ResponsesApiParams,
    context: ResponsesContext,
) -> None:
    """Queue fire-and-forget Splunk telemetry for a Responses API error.

    Args:
        error: The backend exception being converted into an HTTP error.
        api_params: Responses API parameters for the failed request.
        context: Request-scoped Responses API context.
    """
    queue_responses_splunk_event(
        background_tasks=context.background_tasks,
        input_text=context.input_text,
        response_text=type(error).__name__,
        conversation_id=normalize_conversation_id(api_params.conversation),
        model=api_params.model,
        rh_identity_context=context.rh_identity_context,
        inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
        sourcetype="responses_error",
        fire_and_forget=True,
        user_agent=context.user_agent,
    )


def queue_blocked_response_event(
    api_params: ResponsesApiParams,
    context: ResponsesContext,
    response_text: str,
) -> None:
    """Queue Splunk telemetry for a shield-blocked Responses API request.

    Args:
        api_params: Responses API parameters for the blocked request.
        context: Request-scoped Responses API context.
        response_text: Refusal text sent to the client.
    """
    queue_responses_splunk_event(
        background_tasks=context.background_tasks,
        input_text=context.input_text,
        response_text=response_text,
        conversation_id=normalize_conversation_id(api_params.conversation),
        model=api_params.model,
        rh_identity_context=context.rh_identity_context,
        inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
        sourcetype="responses_shield_blocked",
        user_agent=context.user_agent,
    )


def queue_completed_response_event(
    api_params: ResponsesApiParams,
    context: ResponsesContext,
    turn_summary: TurnSummary,
    completed_at: datetime,
    response_text: str,
) -> None:
    """Queue Splunk telemetry for a completed Responses API request.

    Args:
        api_params: Responses API parameters for the completed request.
        context: Request-scoped Responses API context.
        turn_summary: Summary containing token usage for telemetry.
        completed_at: Time when response handling completed.
        response_text: Final text sent to the client.
    """
    if context.moderation_result.decision != "passed":
        return
    queue_responses_splunk_event(
        background_tasks=context.background_tasks,
        input_text=context.input_text,
        response_text=response_text,
        conversation_id=normalize_conversation_id(api_params.conversation),
        model=api_params.model,
        rh_identity_context=context.rh_identity_context,
        inference_time=(completed_at - context.started_at).total_seconds(),
        sourcetype="responses_completed",
        input_tokens=turn_summary.token_usage.input_tokens,
        output_tokens=turn_summary.token_usage.output_tokens,
        user_agent=context.user_agent,
    )
