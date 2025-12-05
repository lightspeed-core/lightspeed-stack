"""Unit tests for the authorization middleware."""

from typing import Any, cast

import pytest
from fastapi import HTTPException, status
from pytest_mock import MockerFixture, MockType
from starlette.requests import Request

import constants
from authentication.interface import AuthTuple
from authorization.middleware import (
    _perform_authorization_check,
    authorize,
    get_authorization_resolvers,
)
from authorization.resolvers import (
    AccessResolver,
    GenericAccessResolver,
    JwtRolesResolver,
    NoopAccessResolver,
    NoopRolesResolver,
)
from models.config import AccessRule, Action, JsonPathOperator, JwtRoleRule


@pytest.fixture(name="dummy_auth_tuple")
def fixture_dummy_auth_tuple() -> AuthTuple:
    """Standard auth tuple for testing."""
    return ("user_id", "username", False, "mock_token")


class TestGetAuthorizationResolvers:
    """Test cases for the get_authorization_resolvers function."""

    @pytest.fixture
    def mock_configuration(self, mocker: MockerFixture) -> MockType:
        """Mock configuration object."""
        config = mocker.MagicMock()
        config.authorization_configuration.access_rules = []
        config.authentication_configuration.jwk_configuration.jwt_configuration.role_rules = (
            []
        )
        return config

    @pytest.fixture
    def sample_access_rule(self) -> AccessRule:
        """Sample access rule for testing."""
        return AccessRule(role="test", actions=[Action.QUERY])

    @pytest.fixture
    def sample_role_rule(self) -> JwtRoleRule:
        """Sample role rule for testing."""
        return JwtRoleRule(
            jsonpath="$.test",
            operator=JsonPathOperator.EQUALS,
            value="test",
            roles=["test"],
        )

    @pytest.mark.parametrize(
        "auth_module,expected_types",
        [
            (constants.AUTH_MOD_NOOP, (NoopRolesResolver, NoopAccessResolver)),
            (constants.AUTH_MOD_K8S, (NoopRolesResolver, NoopAccessResolver)),
            (
                constants.AUTH_MOD_NOOP_WITH_TOKEN,
                (NoopRolesResolver, NoopAccessResolver),
            ),
        ],
    )
    def test_noop_auth_modules(
        self,
        mocker: MockerFixture,
        mock_configuration: MockType,
        auth_module: str,
        expected_types: tuple[AccessResolver, AccessResolver],
    ) -> None:
        """Test resolver selection for noop-style authentication modules."""
        mock_configuration.authentication_configuration.module = auth_module
        mocker.patch("authorization.middleware.configuration", mock_configuration)

        roles_resolver, access_resolver = get_authorization_resolvers()

        assert isinstance(roles_resolver, expected_types[0])  # type: ignore
        assert isinstance(access_resolver, expected_types[1])  # type: ignore

    @pytest.mark.parametrize(
        "empty_rules", ["role_rules", "access_rules", "both_rules"]
    )
    def test_jwk_token_with_empty_rules(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        mocker: MockerFixture,
        mock_configuration: MockType,
        sample_access_rule: AccessRule,
        sample_role_rule: JwtRoleRule,
        empty_rules: str,
    ) -> None:
        """Test JWK token auth falls back to noop when rules are missing."""
        get_authorization_resolvers.cache_clear()

        mock_configuration.authentication_configuration.module = (
            constants.AUTH_MOD_JWK_TOKEN
        )

        # Create a real rule for the non-empty case
        if empty_rules == "role_rules":
            mock_configuration.authorization_configuration.access_rules = [
                sample_access_rule
            ]
        elif empty_rules == "access_rules":
            jwt_config = (
                mock_configuration.authentication_configuration.jwk_configuration.jwt_configuration
            )
            jwt_config.role_rules = [sample_role_rule]
        elif empty_rules == "both_rules":
            # For "both_rules", both lists remain empty (default in fixture)
            pass

        mocker.patch("authorization.middleware.configuration", mock_configuration)

        roles_resolver, access_resolver = get_authorization_resolvers()
        assert isinstance(roles_resolver, NoopRolesResolver)
        assert isinstance(access_resolver, NoopAccessResolver)

    def test_jwk_token_with_rules(
        self,
        mocker: MockerFixture,
        mock_configuration: MockType,
        sample_access_rule: AccessRule,
        sample_role_rule: JwtRoleRule,
    ) -> None:
        """Test JWK token auth with configured rules returns proper resolvers."""
        get_authorization_resolvers.cache_clear()

        mock_configuration.authentication_configuration.module = (
            constants.AUTH_MOD_JWK_TOKEN
        )
        mock_configuration.authorization_configuration.access_rules = [
            sample_access_rule
        ]
        jwt_config = (
            mock_configuration.authentication_configuration.jwk_configuration.jwt_configuration
        )
        jwt_config.role_rules = [sample_role_rule]
        mocker.patch("authorization.middleware.configuration", mock_configuration)

        roles_resolver, access_resolver = get_authorization_resolvers()
        assert isinstance(roles_resolver, JwtRolesResolver)
        assert isinstance(access_resolver, GenericAccessResolver)

    def test_unknown_auth_module(
        self, mocker: MockerFixture, mock_configuration: MockType
    ) -> None:
        """Test unknown authentication module raises HTTPException."""
        # Clear the cache to avoid cached results
        get_authorization_resolvers.cache_clear()

        mock_configuration.authentication_configuration.module = "unknown"
        mocker.patch("authorization.middleware.configuration", mock_configuration)

        with pytest.raises(HTTPException) as exc_info:
            get_authorization_resolvers()

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestPerformAuthorizationCheck:
    """Test cases for _perform_authorization_check function."""

    @pytest.fixture
    def mock_resolvers(self, mocker: MockerFixture) -> tuple[MockType, MockType]:
        """Mock role and access resolvers."""
        role_resolver = mocker.AsyncMock()
        access_resolver = mocker.MagicMock()
        role_resolver.resolve_roles.return_value = {"employee"}
        access_resolver.check_access.return_value = True
        access_resolver.get_actions.return_value = {Action.QUERY}
        return role_resolver, access_resolver

    async def test_missing_auth_kwarg(self) -> None:
        """Test KeyError when auth dependency is missing."""
        with pytest.raises(HTTPException) as exc_info:
            await _perform_authorization_check(Action.QUERY, (), {})

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    async def test_access_denied(
        self,
        mocker: MockerFixture,
        dummy_auth_tuple: AuthTuple,
        mock_resolvers: tuple[MockType, MockType],
    ) -> None:
        """Test HTTPException when access is denied."""
        role_resolver, access_resolver = mock_resolvers
        access_resolver.check_access.return_value = False  # Override to deny access

        mocker.patch(
            "authorization.middleware.get_authorization_resolvers",
            return_value=(role_resolver, access_resolver),
        )

        with pytest.raises(HTTPException) as exc_info:
            await _perform_authorization_check(
                Action.ADMIN, (), {"auth": dummy_auth_tuple}
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.status_code == 403
        detail = cast(dict[str, str], exc_info.value.detail)
        assert detail["response"] == (
            "User does not have permission to access this endpoint"
        )
        assert "not authorized to access this endpoint" in detail["cause"]

    @pytest.mark.parametrize("request_location", ["kwargs", "args", "none"])
    async def test_request_state_handling(
        self,
        mocker: MockerFixture,
        dummy_auth_tuple: AuthTuple,
        mock_resolvers: tuple[MockType, MockType],
        request_location: str,
    ) -> None:
        """Test that authorized_actions are set on request state when present."""
        mocker.patch(
            "authorization.middleware.get_authorization_resolvers",
            return_value=mock_resolvers,
        )

        mock_request = mocker.MagicMock(spec=Request)
        mock_request.state = mocker.MagicMock()

        kwargs = {"auth": dummy_auth_tuple}
        args = []

        if request_location == "kwargs":
            kwargs["request"] = mock_request
        elif request_location == "args":
            args = [
                mock_request,
            ]

        await _perform_authorization_check(Action.QUERY, args, kwargs)  # type: ignore

        if request_location != "none":
            assert mock_request.state.authorized_actions == {Action.QUERY}

    async def test_everyone_role_added(
        self,
        mocker: MockerFixture,
        dummy_auth_tuple: AuthTuple,
        mock_resolvers: tuple[MockType, MockType],
    ) -> None:
        """Test that everyone (*) role is always added to user roles."""
        role_resolver, access_resolver = mock_resolvers
        mocker.patch(
            "authorization.middleware.get_authorization_resolvers",
            return_value=(role_resolver, access_resolver),
        )

        await _perform_authorization_check(Action.QUERY, (), {"auth": dummy_auth_tuple})

        # Verify check_access was called with both user roles and everyone role
        access_resolver.check_access.assert_called_once_with(
            Action.QUERY, {"employee", "*"}
        )


class TestAuthorizeDecorator:
    """Test cases for authorize decorator."""

    async def test_decorator_success(
        self, mocker: MockerFixture, dummy_auth_tuple: AuthTuple
    ) -> None:
        """Test successful authorization through decorator."""

        @authorize(Action.QUERY)
        async def mock_endpoint(**_: Any) -> str:
            return "success"

        mocker.patch(
            "authorization.middleware._perform_authorization_check", return_value=None
        )

        result = await mock_endpoint(auth=dummy_auth_tuple)
        assert result == "success"

    async def test_decorator_failure(
        self, mocker: MockerFixture, dummy_auth_tuple: AuthTuple
    ) -> None:
        """Test authorization failure through decorator."""

        @authorize(Action.ADMIN)
        async def mock_endpoint(**_: Any) -> str:
            return "success"

        mocker.patch(
            "authorization.middleware._perform_authorization_check",
            side_effect=HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await mock_endpoint(auth=dummy_auth_tuple)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
