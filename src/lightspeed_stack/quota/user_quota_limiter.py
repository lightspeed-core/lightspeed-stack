"""Simple user quota limiter where each user has a fixed quota."""

from log import get_logger
from models.config import QuotaHandlersConfiguration
from quota.revokable_quota_limiter import RevokableQuotaLimiter

logger = get_logger(__name__)


class UserQuotaLimiter(RevokableQuotaLimiter):
    """Simple user quota limiter where each user has a fixed quota."""

    def __init__(
        self,
        configuration: QuotaHandlersConfiguration,
        initial_quota: int = 0,
        increase_by: int = 0,
    ) -> None:
        """
        Create a user-specific quota limiter and initialize its persistent storage.

        Parameters:
        ----------
            configuration (QuotaHandlersConfiguration): Configuration for quota
            handlers and storage.
            initial_quota (int): Starting quota value assigned to each user.
            increase_by (int): Amount to increase a user's quota when replenished.

        Notes:
        -----
            Establishes the database connection and initializes required tables
            as part of construction.
        """
        subject = "u"  # user
        super().__init__(configuration, initial_quota, increase_by, subject)

        # initialize connection to DB
        # and initialize tables too
        self.connect()

    def __str__(self) -> str:
        """
        Provide a textual representation of the limiter instance.

        Returns:
            A string containing the class name and the values of
            `initial_quota` and `increase_by` specified in the service
            configuration.
        """
        name = type(self).__name__
        return f"{name}: initial quota: {self.initial_quota} increase by: {self.increase_by}"
