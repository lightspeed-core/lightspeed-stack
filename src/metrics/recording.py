"""Recording helpers for Prometheus metrics.

This module keeps metric definitions in ``metrics.__init__`` while providing a
small facade for application code. New metrics should add a recording helper
here so callers do not need to know Prometheus object details.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

import metrics
from constants import SUPPORTED_AUTHENTICATION_MODULES
from log import get_logger

logger = get_logger(__name__)

AUTH_RESULT_SUCCESS: Final[str] = "success"
AUTH_RESULT_FAILURE: Final[str] = "failure"
AUTH_RESULT_SKIPPED: Final[str] = "skipped"
AUTH_RESULT_UNKNOWN: Final[str] = "unknown"
AUTH_REASON_UNKNOWN: Final[str] = "unknown"

ALLOWED_AUTH_RESULTS: Final[frozenset[str]] = frozenset(
    {
        AUTH_RESULT_SUCCESS,
        AUTH_RESULT_FAILURE,
        AUTH_RESULT_SKIPPED,
    }
)
ALLOWED_AUTH_REASONS: Final[frozenset[str]] = frozenset(
    {
        "authenticated",
        "authorization_check_error",
        "empty_user_id",
        "entitlement_missing",
        "header_too_large",
        "health_probe",
        "invalid_base64",
        "invalid_claim",
        "invalid_identity",
        "invalid_jwk",
        "invalid_json",
        "invalid_key",
        "invalid_token",
        "jwk_fetch_error",
        "k8s_api_unavailable",
        "k8s_config_error",
        "malformed_token",
        "metrics",
        "missing_claim",
        "missing_header",
        "missing_token",
        "no_auth_required",
        "not_authorized",
        "token_decode_error",
        "token_expired",
        "token_review_error",
        "token_validation_error",
        "unexpected_error",
        "valid_key",
    }
)


def normalize_auth_module(auth_module: str) -> str:
    """Return a bounded authentication module label."""
    if auth_module in SUPPORTED_AUTHENTICATION_MODULES:
        return auth_module
    return AUTH_RESULT_UNKNOWN


def normalize_auth_result(result: str) -> str:
    """Return a bounded authentication result label."""
    if result in ALLOWED_AUTH_RESULTS:
        return result
    return AUTH_RESULT_FAILURE


def normalize_auth_reason(reason: str) -> str:
    """Return a bounded authentication reason label."""
    if reason in ALLOWED_AUTH_REASONS:
        return reason
    return AUTH_REASON_UNKNOWN


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


def record_auth_attempt(auth_module: str, result: str, reason: str) -> None:
    """Record one authentication attempt.

    Args:
        auth_module: Configured authentication module name. Unknown values are
            recorded as ``unknown`` to keep metric cardinality bounded.
        result: Bounded result label, such as ``success`` or ``failure``.
            Unknown values are recorded as ``failure``.
        reason: Bounded reason label for the result. Unknown values are recorded
            as ``unknown``.
    """
    try:
        metrics.auth_attempts_total.labels(
            normalize_auth_module(auth_module),
            normalize_auth_result(result),
            normalize_auth_reason(reason),
        ).inc()
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authentication metric", exc_info=True)


def record_auth_duration(auth_module: str, result: str, duration: float) -> None:
    """Record authentication duration.

    Args:
        auth_module: Configured authentication module name. Unknown values are
            recorded as ``unknown`` to keep metric cardinality bounded.
        result: Bounded result label, such as ``success`` or ``failure``.
            Unknown values are recorded as ``failure``.
        duration: Authentication duration in seconds.
    """
    try:
        metrics.auth_duration_seconds.labels(
            normalize_auth_module(auth_module),
            normalize_auth_result(result),
        ).observe(duration)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Failed to update authentication duration metric", exc_info=True)
