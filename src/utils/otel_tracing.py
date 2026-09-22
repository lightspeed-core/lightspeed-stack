"""OpenTelemetry tracing utilities for Lightspeed Core Stack.

This module provides helper functions and constants for instrumenting
the application with OpenTelemetry spans, attributes, and events.
"""

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Optional

from opentelemetry import trace

from constants import OTEL_ANONYMIZATION_SECRET_ENV_VAR
from log import get_logger
from models.common.moderation import ShieldModerationResult
from models.common.turn_summary import TurnSummary

logger = get_logger(__name__)


class SpanAttributes(StrEnum):
    """OpenTelemetry span attribute keys for LCS instrumentation."""

    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"
    SESSION_ID = "session.id"
    USER_ID = "user.id"  # anonymized (identity field)
    SAFETY_IDENTIFIER = "request.safety_identifier"  # caller-supplied identifier
    INPUT = "request.input"  # raw content (anonymization handled downstream)
    OUTPUT = "response.output"  # raw content (anonymization handled downstream)
    RESPONSE_ERROR = "response.error"
    RESPONSE_CAUSE = "response.cause"
    REQUEST_ATTACHMENTS_COUNT = "request.attachments.count"
    LLM_MODEL_ID = "llm.model.id"
    LLM_PROVIDER_ID = "llm.provider.id"
    LLM_USAGE_INPUT_TOKENS = "llm.usage.input_tokens"
    LLM_USAGE_OUTPUT_TOKENS = "llm.usage.output_tokens"
    INFERENCE_TIME = "inference_time"
    COMPACTED = "compacted"
    QUOTA_CHECK_PASSED = "quota.check.passed"
    SHIELD_RESULT = "shield.result"
    SHIELD_REASON = "shield.reason"
    RAG_INPUT = "rag.input"
    RAG_SOURCES_COUNT = "rag.sources.count"
    RAG_SOURCES = "rag.sources"
    RAG_CHUNKS = "rag_chunks"
    TOOL_CALLS_COUNT = "tool.calls.count"
    TOOL_CALLS_NAMES = "tool.calls.names"
    TOOL_CALLS = "tool_calls"
    TOOL_RESULTS = "tool_results"
    SKILL_ACTIVATIONS = "skill.activations"
    RLS_TEMPLATE_OK = "rls.template.ok"
    TOPIC_SUMMARY_SUCCESS = "topic.summary.success"
    A2A_RPC_METHOD = "a2a.rpc.method"
    A2A_REQUEST_ID = "a2a.request.id"
    FEEDBACK_OPERATION = "feedback.operation"
    FEEDBACK_CONVERSATION = "feedback.conversation"
    FEEDBACK_RATING = "feedback.rating"
    FEEDBACK_COMMENT = (
        "feedback.comment"  # raw content (anonymization handled downstream)
    )
    FEEDBACK_CATEGORIES = "feedback.categories"
    FEEDBACK_STATUS_CODE = "feedback.status.code"
    FEEDBACK_STORAGE_OUTCOME = "feedback.storage.outcome"
    INTERRUPT_REQUEST_ID = "interrupt.request_id"
    STREAM_CONVERSATION_ID = "stream.conversation.id"
    INTERRUPT_RESULT = "interrupt.result"
    MCP_SERVER_NAME = "mcp.server.name"
    MCP_SERVER_PROVIDER_ID = "mcp.server.provider_id"
    MCP_SERVERS_COUNT = "mcp.servers.count"
    MCP_OPERATION = "mcp.operation"
    MCP_SERVER_DELETED = "mcp.server.deleted"


class SpanEvents(StrEnum):
    """OpenTelemetry span event names for LCS instrumentation."""

    RLS_TEMPLATE_RENDERED = "rls.template.rendered"
    VALIDATION_COMPLETED = "validation.completed"
    SHIELD_REJECTED = "shield.rejected"
    PII_DETECTED = "pii.detected"
    LLM_INFERENCE_STARTED = "llm.inference.started"
    LLM_INFERENCE_COMPLETED = "llm.inference.completed"
    RAG_RETRIEVAL_COMPLETED = "rag.retrieval.completed"
    TOOL_EXECUTION_COMPLETED = "tool.execution.completed"
    SKILL_ACTIVATED = "skill.activated"
    LLM_RESPONSE_COMPLETED = "llm.response.completed"
    TURN_PERSISTED = "turn.persisted"
    TOPIC_SUMMARY_TASK_STARTED = "topic.summary.task.started"
    TOPIC_SUMMARY_TASK_FINISHED = "topic.summary.task.finished"
    A2A_DISPATCH_START = "a2a.dispatch.start"
    A2A_DISPATCH_END = "a2a.dispatch.end"
    FEEDBACK_SUBMITTED = "feedback.submitted"


def anonymize_value(value: str, max_length: int = 50) -> str:
    """Anonymize a string value using HMAC-SHA-256 for secure correlation.

    Uses HMAC-SHA-256 with a secret key to prevent rainbow table attacks.
    The secret MUST be configured via the OTEL_ANONYMIZATION_SECRET environment
    variable. This function will raise an error if the secret is not set and
    OTEL SDK is enabled.

    Parameters:
        value: The string value to anonymize.
        max_length: Maximum length threshold for classification (default: 50).

    Returns:
        Anonymized string containing only HMAC digest and length metadata.
        Format: [hash:<16-hex-digits>:short|long:len=<length>]
        The digest is the first 16 hex chars (64 bits) of HMAC-SHA-256.
        If OTEL SDK is disabled, returns a placeholder.

    Raises:
        ValueError: If OTEL_ANONYMIZATION_SECRET environment variable is not set
            and OTEL SDK is enabled.
    """
    # Get HMAC secret from environment - fail clearly if not configured
    secret = os.environ.get(OTEL_ANONYMIZATION_SECRET_ENV_VAR)
    if not secret:
        # If OTEL SDK is disabled, anonymization is not needed - return placeholder
        if os.environ.get("OTEL_SDK_DISABLED", "").lower() in ("true", "1"):
            return f"[otel-disabled:len={len(value)}]"

        raise ValueError(
            f"OTEL anonymization secret not configured. "
            f"Set the {OTEL_ANONYMIZATION_SECRET_ENV_VAR} environment variable "
            f"to a secure random value before enabling OpenTelemetry tracing."
        )
    # Compute HMAC-SHA-256 and take first 16 hex chars (64 bits)
    mac = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
    digest = mac.hexdigest()[:16]  # 16 hex chars = 64 bits
    length_indicator = "long" if len(value) > max_length else "short"
    return f"[hash:{digest}:{length_indicator}:len={len(value)}]"


def set_span_attributes(
    span: trace.Span, attributes: Mapping[SpanAttributes, Any]
) -> None:
    """Set multiple attributes on a span.

    Parameters:
        span: The OpenTelemetry span to set attributes on.
        attributes: Mapping of ``SpanAttributes`` keys to values.
    """
    for key, value in attributes.items():
        span.set_attribute(key, value)


def shield_span_attributes(
    moderation_result: ShieldModerationResult,
) -> dict[SpanAttributes, Any]:
    """Build shield decision/reason attributes from an existing moderation result.

    Parameters:
        moderation_result: Shield moderation outcome for the turn.

    Returns:
        Span attribute mapping with decision and, when blocked, reason.
    """
    attributes: dict[SpanAttributes, Any] = {
        SpanAttributes.SHIELD_RESULT: moderation_result.decision,
    }
    if moderation_result.decision == "blocked":
        attributes[SpanAttributes.SHIELD_REASON] = moderation_result.message
    return attributes


def turn_summary_attributes(
    turn_summary: TurnSummary,
    model_id: str,
    provider_id: str,
    inference_time: float,
    compacted: bool = False,
) -> dict[SpanAttributes, Any]:
    """Build span attributes from an existing turn summary.

    Serializes rag_chunks, tool_calls, and tool_results (including ``round``)
    as JSON so nested structures fit OTEL primitive attribute types.

    Parameters:
        turn_summary: Completed turn summary already populated by the request path.
        model_id: Bare model id (provider prefix stripped).
        provider_id: Provider id.
        inference_time: Request processing duration in seconds.
        compacted: Whether the turn used compacted conversation context.

    Returns:
        Span attribute mapping ready for ``set_span_attributes``.
    """
    return {
        SpanAttributes.RAG_CHUNKS: json.dumps(
            [chunk.model_dump(mode="json") for chunk in turn_summary.rag_chunks]
        ),
        SpanAttributes.TOOL_CALLS: json.dumps(
            [call.model_dump(mode="json") for call in turn_summary.tool_calls]
        ),
        SpanAttributes.TOOL_RESULTS: json.dumps(
            [result.model_dump(mode="json") for result in turn_summary.tool_results]
        ),
        SpanAttributes.COMPACTED: compacted,
        SpanAttributes.LLM_USAGE_INPUT_TOKENS: turn_summary.token_usage.input_tokens,
        SpanAttributes.LLM_USAGE_OUTPUT_TOKENS: turn_summary.token_usage.output_tokens,
        SpanAttributes.OUTPUT: turn_summary.llm_response,
        SpanAttributes.LLM_MODEL_ID: model_id,
        SpanAttributes.LLM_PROVIDER_ID: provider_id,
        SpanAttributes.INFERENCE_TIME: inference_time,
    }


def add_span_event(
    span: trace.Span, event_name: str, attributes: Optional[dict[str, Any]] = None
) -> None:
    """Add an event to a span with optional attributes.

    Parameters:
        span: The OpenTelemetry span to add the event to.
        event_name: Name of the event.
        attributes: Optional dictionary of event attributes.
    """
    if attributes is None:
        attributes = {}
    span.add_event(event_name, attributes=attributes)


def record_exception(
    span: trace.Span,
    exception: Exception,
    attributes: Optional[Mapping[SpanAttributes, Any]] = None,
) -> None:
    """Record an exception on a span.

    Parameters:
        span: The OpenTelemetry span to record the exception on.
        exception: The exception to record.
        attributes: Optional additional attributes for the exception event.
    """
    span_attributes = (
        {str(key): value for key, value in attributes.items()} if attributes else None
    )
    span.record_exception(exception, attributes=span_attributes)
