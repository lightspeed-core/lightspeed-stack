"""Data collector runner."""

import logging

from models.config import UserDataCollection
from services.data_collector import DataCollectorService

logger: logging.Logger = logging.getLogger(__name__)


def start_data_collector(configuration: UserDataCollection) -> None:
    """Start the data collector service as a standalone process."""
    logger.info("Starting data collector runner")

    if not configuration.export_enabled:
        logger.info("Data collection is disabled")
        return

    try:
        service = DataCollectorService(
            feedback_dir=configuration.feedback_storage,
            transcripts_dir=configuration.transcripts_storage,
            collection_interval=configuration.export_collection_interval,
            cleanup_after_send=configuration.cleanup_after_send,
            ingress_server_url=configuration.ingress_server_url,
            ingress_server_auth_token=configuration.ingress_server_auth_token,
            ingress_content_service_name=configuration.ingress_content_service_name,
            connection_timeout=configuration.export_connection_timeout,
        )
        service.run()
    except Exception as e:
        logger.error(
            "Data collector service encountered an exception: %s", e, exc_info=True
        )
        raise
