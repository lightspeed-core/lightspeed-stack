"""Data collector runner."""

import logging

from models.config import DataCollectorConfiguration
from services.data_collector import DataCollectorService

logger: logging.Logger = logging.getLogger(__name__)


def start_data_collector(configuration: DataCollectorConfiguration) -> None:
    """Start the data collector service as a standalone process."""
    logger.info("Starting data collector runner")

    if not configuration.enabled:
        logger.info("Data collection is disabled")
        return

    try:
        service = DataCollectorService()
        service.run()
    except Exception as e:
        logger.error(
            "Data collector service encountered an exception: %s", e, exc_info=True
        )
        raise
