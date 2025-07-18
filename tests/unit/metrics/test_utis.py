"""Unit tests for functions defined in metrics/utils.py"""

from metrics.utils import setup_model_metrics


def test_setup_model_metrics(mocker):
    """Test the setup_model_metrics function."""

    # Mock the LlamaStackAsLibraryClient
    mock_client = mocker.patch("client.LlamaStackClientHolder.get_client").return_value

    mock_metric = mocker.patch("metrics.provider_model_configuration")
    fake_model = mocker.Mock(
        provider_id="test_provider",
        identifier="test_model",
        model_type="llm",
    )
    mock_client.models.list.return_value = [fake_model]

    setup_model_metrics()

    # Assert that the metric was set correctly
    mock_metric.labels("test_provider", "test_model").set.assert_called_once_with(1)
