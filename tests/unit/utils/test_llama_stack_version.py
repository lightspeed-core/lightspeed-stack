"""Unit tests for utility function to check Llama Stack version."""

from typing import Any

import pytest
from llama_stack_client import APIConnectionError
from llama_stack_client.types import VersionInfo
from pytest_mock import MockerFixture
from pytest_subtests import SubTests
from semver import Version

from lightspeed_stack.constants import (
    MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
    MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
)
from lightspeed_stack.utils.llama_stack_version import (
    InvalidLlamaStackVersionException,
    check_llama_stack_version,
)


@pytest.mark.asyncio
async def test_check_llama_stack_version_minimal_supported_version(
    mocker: MockerFixture,
) -> None:
    """Test the check_llama_stack_version function."""
    # mock the Llama Stack client
    mock_client = mocker.AsyncMock()
    mock_client.inspect.version.return_value = VersionInfo(
        version=MINIMAL_SUPPORTED_LLAMA_STACK_VERSION
    )

    # test if the version is checked
    await check_llama_stack_version(mock_client)


@pytest.mark.asyncio
async def test_check_llama_stack_version_maximal_supported_version(
    mocker: MockerFixture,
) -> None:
    """Test the check_llama_stack_version function."""
    # mock the Llama Stack client
    mock_client = mocker.AsyncMock()
    mock_client.inspect.version.return_value = VersionInfo(
        version=MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION
    )

    # test if the version is checked
    await check_llama_stack_version(mock_client)


@pytest.mark.asyncio
async def test_check_llama_stack_version_too_small_version(
    mocker: MockerFixture,
) -> None:
    """Test the check_llama_stack_version function."""
    # mock the Llama Stack client
    mock_client = mocker.AsyncMock()

    # that is surely out of range
    mock_client.inspect.version.return_value = VersionInfo(version="0.0.0")

    expected_exception_msg = (
        f"Llama Stack version >= {MINIMAL_SUPPORTED_LLAMA_STACK_VERSION} "
        + "is required, but 0.0.0 is used"
    )
    # test if the version is checked
    with pytest.raises(InvalidLlamaStackVersionException, match=expected_exception_msg):
        await check_llama_stack_version(mock_client)


async def _check_version_must_fail(mock_client: Any, bigger_version: Version) -> None:
    """Check if the Llama Stack version is supported and must fail if not.

    Args:
        mock_client: A mock client used for testing.
        bigger_version: A version object representing a version higher than the supported version.

    Raises:
        InvalidLlamaStackVersionException: If the Llama Stack version is greater than the
        maximal supported version.
    """
    mock_client.inspect.version.return_value = VersionInfo(version=str(bigger_version))

    expected_exception_msg = (
        f"Llama Stack version <= {MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION} is required, "
        + f"but {bigger_version} is used"
    )
    # test if the version is checked
    with pytest.raises(InvalidLlamaStackVersionException, match=expected_exception_msg):
        await check_llama_stack_version(mock_client)


@pytest.mark.asyncio
async def test_check_llama_stack_version_too_big_version(
    mocker: MockerFixture, subtests: SubTests
) -> None:
    """Test the check_llama_stack_version function."""
    # mock the Llama Stack client
    mock_client = mocker.AsyncMock()

    max_version = Version.parse(MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION)

    with subtests.test(msg="Increased patch number"):
        bigger_version = max_version.bump_patch()
        await _check_version_must_fail(mock_client, bigger_version)

    with subtests.test(msg="Increased minor number"):
        bigger_version = max_version.bump_minor()
        await _check_version_must_fail(mock_client, bigger_version)

    with subtests.test(msg="Increased major number"):
        bigger_version = max_version.bump_major()
        await _check_version_must_fail(mock_client, bigger_version)

    with subtests.test(msg="Increased all numbers"):
        bigger_version = max_version.bump_major().bump_minor().bump_patch()
        await _check_version_must_fail(mock_client, bigger_version)


@pytest.mark.asyncio
async def test_check_llama_stack_version_retries_on_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test that check_llama_stack_version retries on APIConnectionError."""
    mock_client = mocker.AsyncMock()
    mock_sleep = mocker.patch(
        "lightspeed_stack.utils.llama_stack_version.asyncio.sleep"
    )

    # Fail twice with connection error, then succeed
    mock_client.inspect.version.side_effect = [
        APIConnectionError(request=mocker.MagicMock()),
        APIConnectionError(request=mocker.MagicMock()),
        VersionInfo(version=MINIMAL_SUPPORTED_LLAMA_STACK_VERSION),
    ]

    await check_llama_stack_version(mock_client, max_retries=5, retry_delay=1)

    assert mock_client.inspect.version.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_check_llama_stack_version_raises_after_max_retries(
    mocker: MockerFixture,
) -> None:
    """Test that check_llama_stack_version raises after all retries are exhausted."""
    mock_client = mocker.AsyncMock()
    mock_sleep = mocker.patch(
        "lightspeed_stack.utils.llama_stack_version.asyncio.sleep"
    )

    mock_client.inspect.version.side_effect = APIConnectionError(
        request=mocker.MagicMock()
    )

    with pytest.raises(APIConnectionError):
        await check_llama_stack_version(mock_client, max_retries=3, retry_delay=1)

    assert mock_client.inspect.version.call_count == 3
    assert mock_sleep.call_count == 2
