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

logger = get_logger(__name__)

QUOTA_TYPE_USER_ID: Final[str] = "user_id"
QUOTA_TYPE_ORG_ID: Final[str] = "org_id"
QUOTA_TYPE_SYSTEM_ID: Final[str] = "system_id"
QUOTA_TYPE_DISABLED: Final[str] = "disabled"
QUOTA_RESULT_SUCCESS: Final[str] = "success"
QUOTA_RESULT_FAILURE: Final[str] = "failure"
QUOTA_RESULT_SKIPPED: Final[str] = "skipped"
QUOTA_RESULT_ERROR: Final[str] = "error"

ALLOWED_QUOTA_TYPES: Final[frozenset[str]] = frozenset(
    {
        QUOTA_TYPE_USER_ID,
        QUOTA_TYPE_ORG_ID,
        QUOTA_TYPE_SYSTEM_ID,
        QUOTA_TYPE_DISABLED,
    }
)
ALLOWED_QUOTA_RESULTS: Final[frozenset[str]] = frozenset(
    {
        QUOTA_RESULT_SUCCESS,
        QUOTA_RESULT_FAILURE,
        QUOTA_RESULT_SKIPPED,
        QUOTA_RESULT_ERROR,
    }
)


def normalize_quota_type(quota_type: str) -> str:
    """Return a bounded quota type label for Prometheus cardinality safety."""
    if quota_type in ALLOWED_QUOTA_TYPES:
        return quota_type
    return QUOTA_TYPE_USER_ID


def normalize_quota_result(result: str) -> str:
    """Return a bounded quota result label for Prometheus cardinality safety."""
    if result in ALLOWED_QUOTA_RESULTS:
        return result
    return QUOTA_RESULT_ERROR


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


def record_quota_check(
    endpoint_path: str, quota_type: str, result: str, duration: float
) -> None:
    """Record a quota availability check.

    Args:
        endpoint_path: API endpoint path for metric labeling.
        quota_type: Bounded quota subject type, not the subject identifier. Out-of-set
            values are recorded as ``user_id``.
        result: Bounded result label. Out-of-set values are recorded as ``error``.
        duration: Quota check duration in seconds.
    """
    normalized_quota_type = normalize_quota_type(quota_type)
    normalized_result = normalize_quota_result(result)
    try:
        metrics.quota_checks_total.labels(
            endpoint_path, normalized_quota_type, normalized_result
        ).inc()
        metrics.quota_check_duration_seconds.labels(
            endpoint_path, normalized_quota_type, normalized_result
        ).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update quota check metrics", exc_info=True)
