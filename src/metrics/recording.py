"""Recording helpers for Prometheus metrics.

This module keeps metric definitions in ``metrics.__init__`` while providing a
small facade for application code. New metrics should add a recording helper
here so callers do not need to know Prometheus object details.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

import metrics
from log import get_logger
from models.config import Action

logger = get_logger(__name__)

AUTHORIZATION_ACTION_UNKNOWN: Final[str] = "unknown"
AUTHORIZATION_RESULT_SUCCESS: Final[str] = "success"
AUTHORIZATION_RESULT_DENIED: Final[str] = "denied"
AUTHORIZATION_RESULT_ERROR: Final[str] = "error"

ALLOWED_AUTHORIZATION_ACTIONS: Final[frozenset[str]] = frozenset(
    action.value for action in Action
)
ALLOWED_AUTHORIZATION_RESULTS: Final[frozenset[str]] = frozenset(
    {
        AUTHORIZATION_RESULT_SUCCESS,
        AUTHORIZATION_RESULT_DENIED,
        AUTHORIZATION_RESULT_ERROR,
    }
)


def normalize_authorization_action(action: str) -> str:
    """Normalize authorization action labels to the bounded Action enum values.

    Args:
        action: Raw authorization action label.

    Returns:
        The action when it is a known protected action, otherwise ``unknown``.
    """
    if action in ALLOWED_AUTHORIZATION_ACTIONS:
        return action
    return AUTHORIZATION_ACTION_UNKNOWN


def normalize_authorization_result(result: str) -> str:
    """Normalize authorization result labels to the bounded result set.

    Args:
        result: Raw authorization result label.

    Returns:
        The result when it is allowed, otherwise ``error``.
    """
    if result in ALLOWED_AUTHORIZATION_RESULTS:
        return result
    return AUTHORIZATION_RESULT_ERROR


@contextmanager
def measure_response_duration(path: str) -> Iterator[None]:
    """Measure REST API response duration for a route path.

    Args:
        path: Normalized route path used as the metric label.
    """
    try:
        cm = metrics.response_duration_seconds.labels(path).time()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to start response duration metric", exc_info=True)
        yield
        return
    with cm:
        yield


def record_rest_api_call(path: str, status_code: int) -> None:
    """Record one REST API request.

    Args:
        path: Normalized route path used as the metric label.
        status_code: HTTP response status code returned by the endpoint.
    """
    try:
        metrics.rest_api_calls_total.labels(path, status_code).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update REST API call metric", exc_info=True)


def record_llm_call(provider: str, model: str, endpoint_path: str) -> None:
    """Record one LLM call for a provider and model.

    Args:
        provider: LLM provider identifier.
        model: LLM model identifier without the provider prefix.
        endpoint_path: The API endpoint path for metric labeling.
    """
    try:
        metrics.llm_calls_total.labels(provider, model, endpoint_path).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update LLM call metric", exc_info=True)


def record_llm_failure(provider: str, model: str, endpoint_path: str) -> None:
    """Record one failed LLM call for a provider and model.

    Args:
        provider: LLM provider identifier.
        model: LLM model identifier without the provider prefix.
        endpoint_path: The API endpoint path for metric labeling.
    """
    try:
        metrics.llm_calls_failures_total.labels(provider, model, endpoint_path).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update LLM failure metric", exc_info=True)


def record_llm_validation_error(endpoint_path: str = "") -> None:
    """Record one LLM validation error, such as a shield violation.

    Args:
        endpoint_path: The API endpoint path for metric labeling.
    """
    try:
        metrics.llm_calls_validation_errors_total.labels(endpoint_path).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update LLM validation error metric", exc_info=True)


def record_llm_token_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    endpoint_path: str,
) -> None:
    """Record LLM token usage for a provider and model.

    Args:
        provider: LLM provider identifier.
        model: LLM model identifier without the provider prefix.
        input_tokens: Number of tokens sent to the LLM.
        output_tokens: Number of tokens received from the LLM.
        endpoint_path: The API endpoint path for metric labeling.
    """
    try:
        metrics.llm_token_sent_total.labels(provider, model, endpoint_path).inc(
            input_tokens
        )
        metrics.llm_token_received_total.labels(provider, model, endpoint_path).inc(
            output_tokens
        )
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update token metrics", exc_info=True)


def record_llm_inference_duration(
    provider: str, model: str, endpoint_path: str, result: str, duration: float
) -> None:
    """Record the latency of a direct LLM inference backend call.

    Args:
        provider: LLM provider identifier.
        model: LLM model identifier without the provider prefix.
        endpoint_path: API endpoint path for metric labeling.
        result: Bounded result label, such as ``success`` or ``failure``.
        duration: Inference call duration in seconds.
    """
    try:
        metrics.llm_inference_duration_seconds.labels(
            provider, model, endpoint_path, result
        ).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update LLM inference duration metric", exc_info=True)


def record_authorization_check(action: str, result: str) -> None:
    """Record one authorization check.

    Args:
        action: Protected action name. Unknown values are recorded as ``unknown``.
        result: Bounded result label. Unknown values are recorded as ``error``.
    """
    normalized_action = normalize_authorization_action(action)
    normalized_result = normalize_authorization_result(result)

    try:
        metrics.authorization_checks_total.labels(
            normalized_action, normalized_result
        ).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authorization metric", exc_info=True)


def record_authorization_duration(action: str, result: str, duration: float) -> None:
    """Record authorization check duration.

    Args:
        action: Protected action name. Unknown values are recorded as ``unknown``.
        result: Bounded result label. Unknown values are recorded as ``error``.
        duration: Authorization check duration in seconds.
    """
    normalized_action = normalize_authorization_action(action)
    normalized_result = normalize_authorization_result(result)

    try:
        metrics.authorization_duration_seconds.labels(
            normalized_action, normalized_result
        ).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authorization duration metric", exc_info=True)
