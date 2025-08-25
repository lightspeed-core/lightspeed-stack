"""Helper functions for mocking authorization in tests."""

from typing import Any
from unittest.mock import AsyncMock, Mock

from models.config import Action


def mock_authorization_resolvers(mocker: Any) -> None:
    """Mock authorization resolvers to allow all access.

    This function mocks the authorization middleware to bypass authorization
    checks in tests by creating mock resolvers that always grant access.

    Args:
        mocker: The pytest-mock mocker fixture
    """
    mock_resolvers = mocker.patch(
        "authorization.middleware.get_authorization_resolvers"
    )
    mock_role_resolver = AsyncMock()
    mock_access_resolver = AsyncMock()
    mock_role_resolver.resolve_roles.return_value = set()
    mock_access_resolver.check_access.return_value = True
    # get_actions should be synchronous, not async
    mock_access_resolver.get_actions = Mock(return_value=set(Action))
    mock_resolvers.return_value = (mock_role_resolver, mock_access_resolver)
