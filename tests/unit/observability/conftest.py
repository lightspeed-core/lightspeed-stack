"""Shared pytest fixtures for obesrvability unit tests."""

from typing import Any

import pytest
from pytest_mock import MockerFixture


@pytest.fixture(name="mock_background_tasks")
def mock_background_tasks_fixture(mocker: MockerFixture) -> Any:
    """Create a mock BackgroundTasks object.

    Returns:
        A Mock object representing FastAPI BackgroundTasks.
    """
    return mocker.Mock()
