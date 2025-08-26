"""Unit tests for the authorization resolvers."""

from authorization.resolvers import JwtRolesResolver, GenericAccessResolver
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action


class TestJwtRolesResolver:
    """Test cases for JwtRolesResolver."""

    async def test_resolve_roles_redhat_employee(self):
        """Test role extraction for RedHat employee JWT."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            )
        ]
        jwt_resolver = JwtRolesResolver(role_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:employee@redhat.com",
            "realm_access": {
                "roles": [
                    "uma_authorization",
                    "redhat:employees",
                    "default-roles-redhat",
                ]
            },
        }

        # Mock auth tuple with JWT claims as third element
        auth = ("user", "token", str(jwt_claims).replace("'", '"'))
        roles = await jwt_resolver.resolve_roles(auth)
        assert "employee" in roles

    async def test_resolve_roles_no_match(self):
        """Test role extraction when no rules match."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            )
        ]
        jwt_resolver = JwtRolesResolver(role_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:user@example.com",
            "realm_access": {"roles": ["uma_authorization", "default-roles-example"]},
        }

        # Mock auth tuple with JWT claims as third element
        auth = ("user", "token", str(jwt_claims).replace("'", '"'))
        roles = await jwt_resolver.resolve_roles(auth)
        assert len(roles) == 0


class TestGenericAccessResolver:
    """Test cases for GenericAccessResolver."""

    async def test_check_access_with_valid_role(self):
        """Test access check with valid role."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        # Test access granted
        has_access = resolver.check_access(Action.QUERY, {"employee"})
        assert has_access is True

        # Test access denied
        has_access = resolver.check_access(Action.FEEDBACK, frozenset(["employee"]))
        assert has_access is False

    async def test_check_access_with_invalid_role(self):
        """Test access check with invalid role."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        has_access = resolver.check_access(Action.QUERY, {"visitor"})
        assert has_access is False

    async def test_check_access_with_no_roles(self):
        """Test access check with no roles."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        has_access = resolver.check_access(Action.QUERY, set())
        assert has_access is False
