"""Unit tests for runners."""

from unittest.mock import patch

from models.config import DataCollectorConfiguration
from runners.data_collector import start_data_collector


def test_start_data_collector() -> None:
    """Test the function to start data collector service."""
    configuration = DataCollectorConfiguration(
        enabled=True,
        ingress_server_url="http://localhost:8080",
        ingress_server_auth_token="xyzzy",
        collection_interval=60,
    )

    # don't start real data collector service
    with patch("services.data_collector.DataCollectorService.run") as mocked_run:
        start_data_collector(configuration)
        mocked_run.assert_called_once()


def test_start_data_collector_disabled() -> None:
    """Test the function to start data collector service."""
    configuration = DataCollectorConfiguration(
        enabled=False,
        ingress_server_url="http://localhost:8080",
        ingress_server_auth_token="xyzzy",
        collection_interval=60,
    )

    # don't start real data collector service
    with patch("services.data_collector.DataCollectorService.run") as mocked_run:
        start_data_collector(configuration)
        mocked_run.assert_not_called()
