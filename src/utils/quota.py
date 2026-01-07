"""Quota handling helper functions."""

from typing import Optional

import psycopg2
from fastapi import HTTPException

from log import get_logger
from models.responses import InternalServerErrorResponse, QuotaExceededResponse
from quota.quota_exceed_error import QuotaExceedError
from quota.quota_limiter import QuotaLimiter
from quota.token_usage_history import TokenUsageHistory

logger = get_logger(__name__)


# pylint: disable=R0913,R0917
def consume_tokens(
    quota_limiters: list[QuotaLimiter],
    token_usage_history: Optional[TokenUsageHistory],
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    model_id: str,
    provider_id: str,
) -> None:
    """Consume tokens from cluster and/or user quotas.

    Parameters:
        quota_limiters: List of quota limiter instances to consume tokens from.
        token_usage_history: Optional instance of TokenUsageHistory class that records used tokens
        user_id: Identifier of the user consuming tokens.
        input_tokens: Number of input tokens to consume.
        output_tokens: Number of output tokens to consume.
        model_id: Model identification
        provider_id: Provider identification

    Returns:
        None
    """
    # record token usage history
    if token_usage_history is not None:
        token_usage_history.consume_tokens(
            user_id=user_id,
            provider=provider_id,
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    # consume tokens all configured quota limiters
    for quota_limiter in quota_limiters:
        quota_limiter.consume_tokens(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            subject_id=user_id,
        )


def check_tokens_available(quota_limiters: list[QuotaLimiter], user_id: str) -> None:
    """Check if tokens are available for user.

    Parameters:
        quota_limiters: List of quota limiter instances to check.
        user_id: Identifier of the user to check quota for.

    Returns:
        None

    Raises:
        HTTPException: With status 500 if database communication fails,
            or status 429 if quota is exceeded.
    """
    try:
        # check available tokens using all configured quota limiters
        for quota_limiter in quota_limiters:
            quota_limiter.ensure_available_quota(subject_id=user_id)
    except psycopg2.Error as pg_error:
        message = "Error communicating with quota database backend"
        logger.error(message)
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from pg_error
    except QuotaExceedError as e:
        logger.error("The quota has been exceeded")
        response = QuotaExceededResponse.from_exception(e)
        raise HTTPException(**response.model_dump()) from e


def get_available_quotas(
    quota_limiters: list[QuotaLimiter],
    user_id: str,
) -> dict[str, int]:
    """Get quota available from all quota limiters.

    Args:
        quota_limiters: List of quota limiter instances to query.
        user_id: Identifier of the user to get quotas for.

    Returns:
        Dictionary mapping quota limiter class names to available token counts.
    """
    available_quotas: dict[str, int] = {}

    # retrieve available tokens using all configured quota limiters
    for quota_limiter in quota_limiters:
        name = quota_limiter.__class__.__name__
        available_quota = quota_limiter.available_quota(user_id)
        available_quotas[name] = available_quota
    return available_quotas
