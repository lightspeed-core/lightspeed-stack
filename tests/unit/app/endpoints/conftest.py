"""Shared pytest fixtures for endpoint unit tests."""

from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture


@pytest.fixture(name="mock_request_factory")
def mock_request_factory_fixture(mocker: MockerFixture) -> Callable[..., Any]:
    """Create a mock FastAPI Request with optional RH Identity.

    Returns:
        Callable that accepts an optional rh_identity argument and returns a Mock request.
    """

    def _create(rh_identity: Any = None) -> Any:
        mock_request = mocker.Mock()
        mock_request.headers = {"User-Agent": "CLA/0.4.2"}

        if rh_identity is not None:
            mock_request.state = mocker.Mock()
            mock_request.state.rh_identity_data = rh_identity
        else:
            # Use spec=[] to create a Mock with no attributes, simulating absent rh_identity_data
            mock_request.state = mocker.Mock(spec=[])

        return mock_request

    return _create


@pytest.fixture(name="mock_background_tasks")
def mock_background_tasks_fixture(mocker: MockerFixture) -> Any:
    """Create a mock BackgroundTasks object.

    Returns:
        A Mock object representing FastAPI BackgroundTasks.
    """
    return mocker.Mock()
