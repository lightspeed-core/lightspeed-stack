"""Unit tests for functions defined in metrics/utils.py"""

from metrics.utils import setup_model_metrics


async def test_setup_model_metrics(mocker):
    """Test the setup_model_metrics function."""

    # Mock the LlamaStackAsLibraryClient
    mock_client = mocker.patch("client.LlamaStackClientHolder.get_client").return_value
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "default_provider",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default_model",
    )

    mock_metric = mocker.patch("metrics.provider_model_configuration")
    # Mock a model that is the default
    model_default = mocker.Mock(
        provider_id="default_provider",
        identifier="default_model",
        model_type="llm",
    )
    # Mock a model that is not the default
    model_0 = mocker.Mock(
        provider_id="test_provider-0",
        identifier="test_model-0",
        model_type="llm",
    )
    # Mock a second model which is not default
    model_1 = mocker.Mock(
        provider_id="test_provider-1",
        identifier="test_model-1",
        model_type="llm",
    )
    # Mock a model that is not an LLM type, should be ignored
    not_llm_model = mocker.Mock(
        provider_id="not-llm-provider",
        identifier="not-llm-model",
        model_type="not-llm",
    )

    # Mock the list of models returned by the client
    mock_client.models.list.return_value = [
        model_0,
        model_default,
        not_llm_model,
        model_1,
    ]

    await setup_model_metrics()

    # Check that the provider_model_configuration metric was set correctly
    # The default model should have a value of 1, others should be 0
    assert mock_metric.labels.call_count == 3
    mock_metric.assert_has_calls(
        [
            mocker.call.labels("test_provider-0", "test_model-0"),
            mocker.call.labels().set(0),
            mocker.call.labels("default_provider", "default_model"),
            mocker.call.labels().set(1),
            mocker.call.labels("test_provider-1", "test_model-1"),
            mocker.call.labels().set(0),
        ],
        any_order=False,  # Order matters here
    )
