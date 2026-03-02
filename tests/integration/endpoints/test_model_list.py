"""Integration tests for the /models endpoint (using Responses API)."""

from typing import Any, Generator

import pytest
from fastapi import Request
from fastapi.exceptions import HTTPException
from pytest_mock import AsyncMockType, MockerFixture
from llama_stack_client import APIConnectionError

from models.requests import ModelFilter
from app.endpoints.models import models_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
        mocker (MockerFixture): pytest-mock fixture used to create and patch mocks.

    Returns:
        mock_client: The mocked Llama Stack client instance configured as described above.
    """
    # Patch in app.endpoints.models where it's actually used by models_endpoint_handler_base
    mock_holder_class = mocker.patch("app.endpoints.models.AsyncLlamaStackClientHolder")

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
        mocker (MockerFixture): pytest-mock fixture used to create and patch mocks.

    Returns:
        mock_client: The mocked Llama Stack client instance configured as described above.
    """
    # Patch in app.endpoints.models where it's actually used by models_endpoint_handler_base
    mock_holder_class = mocker.patch("app.endpoints.models.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()

    mock_client.models.list.side_effect = APIConnectionError(request=mocker.Mock())

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.mark.asyncio
async def test_models_list(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that models endpoint returns successful response.

    This integration test verifies:
    - Model list handler

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    response = await models_endpoint_handler(
        request=test_request,
        auth=test_auth,
        model_type=ModelFilter(model_type=None),
    )

    # Verify response structure
    assert response is not None
    assert len(response.models) == 2
    assert response.models[0]["identifier"] == "test-provider/test-model-1"
    assert response.models[0]["api_model_type"] == "llm"
    assert response.models[1]["identifier"] == "test-provider/test-model-2"
    assert response.models[1]["api_model_type"] == "embedding"


@pytest.mark.asyncio
async def test_models_list_filter_model_type_llm(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that models endpoint returns successful response.

    This integration test verifies:
    - Model list handler

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    response = await models_endpoint_handler(
        request=test_request, auth=test_auth, model_type=ModelFilter(model_type="llm")
    )

    # Verify response structure
    assert response is not None
    assert len(response.models) == 1
    assert response.models[0]["identifier"] == "test-provider/test-model-1"
    assert response.models[0]["api_model_type"] == "llm"


@pytest.mark.asyncio
async def test_models_list_filter_model_type_embedding(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that models endpoint returns successful response.

    This integration test verifies:
    - Model list handler

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    response = await models_endpoint_handler(
        request=test_request,
        auth=test_auth,
        model_type=ModelFilter(model_type="embedding"),
    )

    # Verify response structure
    assert response is not None
    assert len(response.models) == 1
    assert response.models[0]["identifier"] == "test-provider/test-model-2"
    assert response.models[0]["api_model_type"] == "embedding"


@pytest.mark.asyncio
async def test_models_list_filter_model_type_unknown(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that models endpoint returns successful response.

    This integration test verifies:
    - Model list handler

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    _ = test_config
    _ = mock_llama_stack_client

    response = await models_endpoint_handler(
        request=test_request,
        auth=test_auth,
        model_type=ModelFilter(model_type="foobar"),
    )

    # Verify response structure
    assert response is not None
    assert len(response.models) == 0


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
    assert exc_info.value.detail["response"] == "Unable to connect to Llama Stack"
    assert "cause" in exc_info.value.detail
