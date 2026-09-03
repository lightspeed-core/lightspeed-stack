"""Unit tests for functions defined in metrics/utils.py"""

import pytest
from pytest_mock import MockerFixture

from metrics.utils import setup_model_metrics
from tests.unit.conftest import make_openai_model, make_openai_models_list_response


@pytest.mark.asyncio
async def test_setup_model_metrics(mocker: MockerFixture) -> None:
    """Test the setup_model_metrics function."""
    # Mock the OGXAsLibraryClient
    mock_client = mocker.patch(
        "client.ogx.AsyncOgxClientHolder.get_client"
    ).return_value
    # Make sure the client is an AsyncMock for async methods
    mock_client = mocker.AsyncMock()
    mocker.patch("client.ogx.AsyncOgxClientHolder.get_client", return_value=mock_client)
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "default_provider",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default_model",
    )

    mock_metric = mocker.patch("metrics.provider_model_configuration")
    model_default = make_openai_model(
        model_id="default_model", provider_id="default_provider", model_type="llm"
    )
    model_0 = make_openai_model(
        model_id="test_model-0", provider_id="test_provider-0", model_type="llm"
    )
    model_1 = make_openai_model(
        model_id="test_model-1", provider_id="test_provider-1", model_type="llm"
    )
    not_llm_model = make_openai_model(
        model_id="not-llm-model", provider_id="not-llm-provider", model_type="not-llm"
    )

    mock_client.openai.list.return_value = make_openai_models_list_response(
        model_0,
        model_default,
        not_llm_model,
        model_1,
    )

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
