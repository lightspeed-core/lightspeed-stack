"""Unit tests for model availability verification at startup."""

import httpx
import pytest
from llama_stack_client import APIConnectionError, APIStatusError
from pytest_mock import MockerFixture

from utils.model_availability import verify_models_available


@pytest.mark.asyncio
async def test_happy_path_models_found(mocker: MockerFixture) -> None:
    """Models are returned on the first attempt."""
    mock_client = mocker.AsyncMock()
    mock_model = mocker.Mock()
    mock_model.id = "meta-llama/Llama-3.1-8B"
    mock_client.models.list.return_value = [mock_model]

    await verify_models_available(mock_client, max_retries=3, base_delay=1)

    mock_client.models.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_then_success_empty_list(mocker: MockerFixture) -> None:
    """Empty list on first two attempts, models appear on the third."""
    mock_sleep = mocker.patch("utils.model_availability.asyncio.sleep")

    mock_model = mocker.Mock()
    mock_model.id = "model-1"
    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = [[], [], [mock_model]]

    await verify_models_available(mock_client, max_retries=5, base_delay=2)

    assert mock_client.models.list.await_count == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_all_retries_exhausted_empty_list(mocker: MockerFixture) -> None:
    """RuntimeError raised when all retries return empty lists."""
    mocker.patch("utils.model_availability.asyncio.sleep")

    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = []

    with pytest.raises(RuntimeError, match="No models registered"):
        await verify_models_available(mock_client, max_retries=3, base_delay=1)

    assert mock_client.models.list.await_count == 3


@pytest.mark.asyncio
async def test_api_connection_error_then_recovery(mocker: MockerFixture) -> None:
    """APIConnectionError on first attempt, success on the second."""
    mocker.patch("utils.model_availability.asyncio.sleep")

    mock_model = mocker.Mock()
    mock_model.id = "model-a"
    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = [
        APIConnectionError(request=mocker.Mock()),
        [mock_model],
    ]

    await verify_models_available(mock_client, max_retries=3, base_delay=2)

    assert mock_client.models.list.await_count == 2


@pytest.mark.asyncio
async def test_api_connection_error_exhaustion(mocker: MockerFixture) -> None:
    """APIConnectionError raised when all retries fail with connection errors."""
    mocker.patch("utils.model_availability.asyncio.sleep")

    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = APIConnectionError(request=mocker.Mock())

    with pytest.raises(APIConnectionError):
        await verify_models_available(mock_client, max_retries=3, base_delay=1)

    assert mock_client.models.list.await_count == 3


@pytest.mark.asyncio
async def test_exponential_backoff_timing(mocker: MockerFixture) -> None:
    """Verify sleep delays follow the exponential backoff formula."""
    mock_sleep = mocker.patch("utils.model_availability.asyncio.sleep")

    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = []

    with pytest.raises(RuntimeError):
        await verify_models_available(mock_client, max_retries=5, base_delay=2)

    # Attempts 0-3 sleep; attempt 4 raises without sleeping
    expected_delays = [2, 4, 8, 16]
    actual_delays = [call.args[0] for call in mock_sleep.await_args_list]
    assert actual_delays == expected_delays


@pytest.mark.asyncio
async def test_exponential_backoff_on_connection_error(
    mocker: MockerFixture,
) -> None:
    """Backoff timing also applies to APIConnectionError retries."""
    mock_sleep = mocker.patch("utils.model_availability.asyncio.sleep")

    mock_model = mocker.Mock()
    mock_model.id = "model-x"
    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = [
        APIConnectionError(request=mocker.Mock()),
        APIConnectionError(request=mocker.Mock()),
        [mock_model],
    ]

    await verify_models_available(mock_client, max_retries=5, base_delay=2)

    expected_delays = [2, 4]
    actual_delays = [call.args[0] for call in mock_sleep.await_args_list]
    assert actual_delays == expected_delays


def _make_api_status_error() -> APIStatusError:
    """Create an APIStatusError with a mocked httpx response."""
    mock_request = httpx.Request("GET", "http://localhost/models")
    mock_response = httpx.Response(
        status_code=503, text="Service Unavailable", request=mock_request
    )
    return APIStatusError("Internal Server Error", response=mock_response, body=None)


@pytest.mark.asyncio
async def test_api_status_error_then_recovery(mocker: MockerFixture) -> None:
    """APIStatusError on first attempt, success on the second."""
    mocker.patch("utils.model_availability.asyncio.sleep")

    mock_model = mocker.Mock()
    mock_model.id = "model-a"
    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = [
        _make_api_status_error(),
        [mock_model],
    ]

    await verify_models_available(mock_client, max_retries=3, base_delay=2)

    assert mock_client.models.list.await_count == 2


@pytest.mark.asyncio
async def test_api_status_error_exhaustion(mocker: MockerFixture) -> None:
    """APIStatusError raised when all retries fail with status errors."""
    mocker.patch("utils.model_availability.asyncio.sleep")

    mock_client = mocker.AsyncMock()
    mock_client.models.list.side_effect = _make_api_status_error()

    with pytest.raises(APIStatusError):
        await verify_models_available(mock_client, max_retries=3, base_delay=1)

    assert mock_client.models.list.await_count == 3
