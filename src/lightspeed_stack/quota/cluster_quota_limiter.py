"""Simple cluster quota limiter where quota is fixed for the whole cluster."""

from log import get_logger
from models.config import QuotaHandlersConfiguration
from quota.revokable_quota_limiter import RevokableQuotaLimiter

logger = get_logger(__name__)


class ClusterQuotaLimiter(RevokableQuotaLimiter):
    """Simple cluster quota limiter where quota is fixed for the whole cluster."""

    def __init__(
        self,
        configuration: QuotaHandlersConfiguration,
        initial_quota: int = 0,
        increase_by: int = 0,
    ) -> None:
        """
        Create a quota limiter and initialize its persistent storage.

        Parameters:
        ----------
            configuration (QuotaHandlersConfiguration): Handlers and settings used by the limiter.
            initial_quota (int): Starting quota value for the entire cluster.
            increase_by (int): Amount by which the quota is increased when applicable.

        Notes:
        -----
            Establishes the database connection and ensures required tables exist.
        """
        subject = "c"  # cluster
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
