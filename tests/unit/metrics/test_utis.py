"""Unit tests for functions defined in metrics/utils.py"""

import pytest
from ogx_client.types import ListModelsResponse
from ogx_client.types.model import Model
from pytest_mock import MockerFixture

from metrics.utils import setup_model_metrics


def _make_model(model_id: str, provider_id: str, model_type: str) -> Model:
    """Build an OGX Model for metrics tests."""
    return Model.model_construct(
        id=model_id,
        created=0,
        owned_by="test",
        object="model",
        custom_metadata={"provider_id": provider_id, "model_type": model_type},
    )


@pytest.mark.asyncio
async def test_setup_model_metrics(mocker: MockerFixture) -> None:
    """Test the setup_model_metrics function."""
    # Mock the OGXAsLibraryClient
    mock_client = mocker.patch("client.AsyncOgxClientHolder.get_client").return_value
    # Make sure the client is an AsyncMock for async methods
    mock_client = mocker.AsyncMock()
    mocker.patch("client.AsyncOgxClientHolder.get_client", return_value=mock_client)
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "default_provider",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default_model",
    )

    mock_metric = mocker.patch("metrics.provider_model_configuration")
    model_default = _make_model("default_model", "default_provider", "llm")
    model_0 = _make_model("test_model-0", "test_provider-0", "llm")
    model_1 = _make_model("test_model-1", "test_provider-1", "llm")
    not_llm_model = _make_model("not-llm-model", "not-llm-provider", "not-llm")

    # Mock the list of models returned by the client
    mock_client.models.list.return_value = ListModelsResponse.model_construct(
        data=[
            model_0,
            model_default,
            not_llm_model,
            model_1,
        ]
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
