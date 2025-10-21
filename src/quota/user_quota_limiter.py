"""Simple user quota limiter where each user have fixed quota."""

from models.config import QuotaHandlersConfiguration
from log import get_logger
from quota.revokable_quota_limiter import RevokableQuotaLimiter

logger = get_logger(__name__)


class UserQuotaLimiter(RevokableQuotaLimiter):
    """Simple user quota limiter where each user have fixed quota."""

    def __init__(
        self,
        configuration: QuotaHandlersConfiguration,
        initial_quota: int = 0,
        increase_by: int = 0,
    ) -> None:
        """Initialize quota limiter storage."""
        subject = "u"  # user
        super().__init__(configuration, initial_quota, increase_by, subject)

        # initialize connection to DB
        # and initialize tables too
        self.connect()

    def __str__(self) -> str:
        """Return textual representation of limiter instance."""
        name = type(self).__name__
        return f"{name}: initial quota: {self.initial_quota} increase by: {self.increase_by}"
