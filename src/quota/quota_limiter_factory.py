"""Quota limiter factory class."""

from log import get_logger
import constants
from models.config import QuotaHandlersConfiguration

from quota.user_quota_limiter import UserQuotaLimiter
from quota.cluster_quota_limiter import ClusterQuotaLimiter
from quota.quota_limiter import QuotaLimiter

logger = get_logger(__name__)


# pylint: disable=too-few-public-methods


class QuotaLimiterFactory:
    """Quota limiter factory class."""

    @staticmethod
    def quota_limiters(config: QuotaHandlersConfiguration) -> list[QuotaLimiter]:
        """Create instances of quota limiters based on loaded configuration.

        Returns:
            List of instances of 'QuotaLimiter',
        """
        limiters: list[QuotaLimiter] = []

        # storage (Postgres) configuration
        if config.sqlite is None and config.postgres is None:
            logger.warning("Storage configuration for quota limiters not specified")
            return limiters

        limiters_config = config.limiters
        if limiters_config is None:
            logger.warning("Quota limiters are not specified in configuration")
            return limiters

        # fill-in list of initialized quota limiters
        for limiter_config in config.limiters:
            limiter_type = limiter_config.type
            limiter_name = limiter_config.name
            initial_quota = limiter_config.initial_quota
            increase_by = limiter_config.quota_increase
            limiter = QuotaLimiterFactory.create_limiter(
                config, limiter_type, initial_quota, increase_by
            )
            limiters.append(limiter)
            logger.info("Set up quota limiter '%s'", limiter_name)
        return limiters

    @staticmethod
    def create_limiter(
        configuration: QuotaHandlersConfiguration,
        limiter_type: str,
        initial_quota: int,
        increase_by: int,
    ) -> QuotaLimiter:
        """Create selected quota limiter."""
        match limiter_type:
            case constants.USER_QUOTA_LIMITER:
                return UserQuotaLimiter(configuration, initial_quota, increase_by)
            case constants.CLUSTER_QUOTA_LIMITER:
                return ClusterQuotaLimiter(configuration, initial_quota, increase_by)
            case _:
                raise ValueError(f"Invalid limiter type: {limiter_type}.")
