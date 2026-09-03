"""OpenTelemetry tracing utilities for Lightspeed Core Stack.

This module provides helper functions and constants for instrumenting
the application with OpenTelemetry spans, attributes, and events.
"""

import hashlib
import hmac
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Optional

from opentelemetry import trace

from constants import OTEL_ANONYMIZATION_SECRET_ENV_VAR
from log import get_logger

logger = get_logger(__name__)


class SpanAttributes(StrEnum):
    """OpenTelemetry span attribute keys for LCS instrumentation."""

    SESSION_ID = "session.id"
    USER_ID = "user.id"  # anonymized
    SAFETY_IDENTIFIER = "request.safety_identifier"  # caller-supplied identifier
    INPUT = "request.input"  # anonymized
    OUTPUT = "response.output"  # anonymized
    RESPONSE_ERROR = "response.error"
    RESPONSE_CAUSE = "response.cause"
    REQUEST_ATTACHMENTS_COUNT = "request.attachments.count"
    LLM_MODEL_ID = "llm.model.id"
    LLM_PROVIDER_ID = "llm.provider.id"
    LLM_USAGE_INPUT_TOKENS = "llm.usage.input_tokens"
    LLM_USAGE_OUTPUT_TOKENS = "llm.usage.output_tokens"
    QUOTA_CHECK_PASSED = "quota.check.passed"
    SHIELD_RESULT = "shield.result"
    RAG_INPUT = "rag.input"
    RAG_SOURCES_COUNT = "rag.sources.count"
    RAG_SOURCES = "rag.sources"
    TOOL_CALLS_COUNT = "tool.calls.count"
    TOOL_CALLS_NAMES = "tool.calls.names"
    SKILL_ACTIVATIONS = "skill.activations"
    RLS_TEMPLATE_OK = "rls.template.ok"
    TOPIC_SUMMARY_SUCCESS = "topic.summary.success"
    A2A_RPC_METHOD = "a2a.rpc.method"
    A2A_REQUEST_ID = "a2a.request.id"
    FEEDBACK_OPERATION = "feedback.operation"
    FEEDBACK_CONVERSATION = "feedback.conversation"
    FEEDBACK_RATING = "feedback.rating"
    FEEDBACK_COMMENT = "feedback.comment"  # anonymized
    FEEDBACK_CATEGORIES = "feedback.categories"
    FEEDBACK_STATUS_CODE = "feedback.status.code"
    FEEDBACK_STORAGE_OUTCOME = "feedback.storage.outcome"
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


def set_span_attributes(span: trace.Span, attributes: dict[str, Any]) -> None:
    """Set multiple attributes on a span.

    Parameters:
        span: The OpenTelemetry span to set attributes on.
        attributes: Dictionary of attribute key-value pairs to set.
    """
    for key, value in attributes.items():
        span.set_attribute(key, value)


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
