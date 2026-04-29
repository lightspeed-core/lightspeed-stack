"""Recording helpers for Prometheus metrics.

This module keeps metric definitions in ``metrics.__init__`` while providing a
small facade for application code. New metrics should add a recording helper
here so callers do not need to know Prometheus object details.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import metrics
from log import get_logger

logger = get_logger(__name__)


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


def record_auth_attempt(auth_module: str, result: str, reason: str) -> None:
    """Record one authentication attempt.

    Args:
        auth_module: Configured authentication module name.
        result: Bounded result label, such as ``success`` or ``failure``.
        reason: Bounded reason label for the result.
    """
    try:
        metrics.auth_attempts_total.labels(auth_module, result, reason).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authentication metric", exc_info=True)


def record_auth_duration(auth_module: str, result: str, duration: float) -> None:
    """Record authentication duration.

    Args:
        auth_module: Configured authentication module name.
        result: Bounded result label, such as ``success`` or ``failure``.
        duration: Authentication duration in seconds.
    """
    try:
        metrics.auth_duration_seconds.labels(auth_module, result).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authentication duration metric", exc_info=True)


def record_authorization_check(action: str, result: str) -> None:
    """Record one authorization check.

    Args:
        action: Protected action name.
        result: Bounded result label, such as ``success`` or ``denied``.
    """
    try:
        metrics.authorization_checks_total.labels(action, result).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authorization metric", exc_info=True)


def record_authorization_duration(action: str, result: str, duration: float) -> None:
    """Record authorization check duration.

    Args:
        action: Protected action name.
        result: Bounded result label, such as ``success`` or ``denied``.
        duration: Authorization check duration in seconds.
    """
    try:
        metrics.authorization_duration_seconds.labels(action, result).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authorization duration metric", exc_info=True)


def record_quota_check(
    endpoint_path: str, quota_subject: str, result: str, duration: float
) -> None:
    """Record a quota availability check.

    Args:
        endpoint_path: API endpoint path for metric labeling.
        quota_subject: Bounded quota subject source, not the subject identifier.
        result: Bounded result label, such as ``success``, ``skipped``, or ``failure``.
        duration: Quota check duration in seconds.
    """
    try:
        metrics.quota_checks_total.labels(endpoint_path, quota_subject, result).inc()
        metrics.quota_check_duration_seconds.labels(
            endpoint_path, quota_subject, result
        ).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update quota check metrics", exc_info=True)


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
