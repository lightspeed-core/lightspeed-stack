"""Integration tests for the /models endpoint (using Responses API)."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request
from fastapi.exceptions import HTTPException
from llama_stack_client import APIConnectionError
from pytest_mock import AsyncMockType, MockerFixture

from lightspeed_stack.app.endpoints.models import models_endpoint_handler
from lightspeed_stack.authentication.interface import AuthTuple
from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.models.api.requests import ModelFilter


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
    ----------
        mocker (MockerFixture): pytest-mock fixture used to create and patch mocks.

    Returns:
    -------
        mock_client: The mocked Llama Stack client instance configured as described above.
    """
    # Patch in app.endpoints.models where it's actually used by models_endpoint_handler_base
    mock_holder_class = mocker.patch("lightspeed_stack.app.endpoints.models.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()

    # Mock models list (required for model selection)
    mock_model1 = mocker.MagicMock()
    mock_model1.id = "test-provider/test-model-1"
    mock_model1.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "llm",
    }
    mock_model2 = mocker.MagicMock()
    mock_model2.id = "test-provider/test-model-2"
    mock_model2.custom_metadata = {
        "provider_id": "test-provider",
        "model_type": "embedding",
    }
    mock_client.models.list.return_value = [mock_model1, mock_model2]

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.fixture(name="mock_llama_stack_client_failing")
def mock_llama_stack_client_failing_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
    ----------
        mocker (MockerFixture): pytest-mock fixture used to create and patch mocks.

    Returns:
    -------
        mock_client: The mocked Llama Stack client instance configured as described above.
    """
    # Patch in app.endpoints.models where it's actually used by models_endpoint_handler_base
    mock_holder_class = mocker.patch("lightspeed_stack.app.endpoints.models.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()

    mock_client.models.list.side_effect = APIConnectionError(request=mocker.Mock())

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


MODEL_FILTER_TEST_CASES = [
    pytest.param(
        {
            "filter_type": None,
            "expected_count": 2,
            "expected_models": [
                {"identifier": "test-provider/test-model-1", "api_model_type": "llm"},
                {
                    "identifier": "test-provider/test-model-2",
                    "api_model_type": "embedding",
                },
            ],
        },
        id="no_filter_returns_all_models",
    ),
    pytest.param(
        {
            "filter_type": "llm",
            "expected_count": 1,
            "expected_models": [
                {"identifier": "test-provider/test-model-1", "api_model_type": "llm"},
            ],
        },
        id="filter_llm_returns_llm_model",
    ),
    pytest.param(
        {
            "filter_type": "foobar",
            "expected_count": 0,
            "expected_models": [],
        },
        id="filter_unknown_type_returns_empty",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", MODEL_FILTER_TEST_CASES)
async def test_models_list_with_filter(
    test_case: dict,
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Tests for models endpoint filtering.

    Tests different model_type filter scenarios:
    - No filter (returns all models)
    - Filter by llm type
    - Filter by unknown type (returns empty)

    Parameters:
    ----------
        test_case: Dictionary containing test parameters (filter_type,
            expected_count, expected_models)
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    filter_type = test_case["filter_type"]
    expected_count = test_case["expected_count"]
    expected_models = test_case["expected_models"]

    response = await models_endpoint_handler(
        request=test_request,
        auth=test_auth,
        model_type=ModelFilter(model_type=filter_type),
    )

    # Verify response structure
    assert response is not None
    assert len(response.models) == expected_count

    # Verify each expected model
    for i, expected_model in enumerate(expected_models):
        assert response.models[i]["identifier"] == expected_model["identifier"]
        assert response.models[i]["api_model_type"] == expected_model["api_model_type"]


@pytest.mark.asyncio
async def test_models_list_on_api_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client_failing: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that models endpoint raises HTTPException on API connection error.

    This integration test verifies:
    - Model list handler
    - Error handling when Llama Stack is unreachable

    Parameters:
    ----------
        test_config: Test configuration
        mock_llama_stack_client_failing: Mocked Llama Stack client that raises APIConnectionError
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client_failing

    # we should catch HTTPException, not APIConnectionError!
    with pytest.raises(HTTPException) as exc_info:
        await models_endpoint_handler(
            request=test_request,
            auth=test_auth,
            model_type=ModelFilter(model_type=None),
        )

    assert exc_info.value.status_code == 503
    assert isinstance(exc_info.value.detail, dict)
    expected = "Unable to connect to Llama Stack"
    assert exc_info.value.detail["response"] == expected  # type: ignore[reportArgumentType]
    assert "cause" in exc_info.value.detail
