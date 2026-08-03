"""Helper functions for mocking authorization in tests."""

from pytest_mock import MockerFixture

from lightspeed_stack.models.config import Action


def mock_authorization_resolvers(mocker: MockerFixture) -> None:
    """Mock authorization resolvers to allow all access.

    This function mocks the authorization middleware to bypass authorization
    checks in tests by creating mock resolvers that always grant access.

    Args:
        mocker: The pytest-mock mocker fixture
    """
    mock_resolvers = mocker.patch(
        "lightspeed_stack.authorization.middleware.get_authorization_resolvers"
    )
    mock_role_resolver = mocker.AsyncMock()
    mock_access_resolver = mocker.Mock()
    mock_role_resolver.resolve_roles.return_value = set()
    mock_access_resolver.check_access.return_value = True
    # get_actions should be synchronous, not async
    mock_access_resolver.get_actions = mocker.Mock(return_value=set(Action))
    mock_resolvers.return_value = (mock_role_resolver, mock_access_resolver)
