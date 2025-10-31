"""Unit tests for the authorization resolvers."""

import json
import base64
import re
from contextlib import nullcontext as does_not_raise

import pytest

from authorization.resolvers import JwtRolesResolver, GenericAccessResolver
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action
import constants


def claims_to_token(claims: dict) -> str:
    """Convert JWT claims dictionary to a JSON string token."""

    string_claims = json.dumps(claims)
    b64_encoded_claims = (
        base64.urlsafe_b64encode(string_claims.encode()).decode().rstrip("=")
    )

    return f"foo_header.{b64_encoded_claims}.foo_signature"


def claims_to_auth_tuple(claims: dict) -> tuple:
    """Convert JWT claims dictionary to an auth tuple."""
    return ("user", "token", False, claims_to_token(claims))


class TestJwtRolesResolver:
    """Test cases for JwtRolesResolver."""

    @pytest.fixture
    async def employee_role_rule(self):
        """Role rule for RedHat employees."""
        return JwtRoleRule(
            jsonpath="$.realm_access.roles[*]",
            operator=JsonPathOperator.CONTAINS,
            value="redhat:employees",
            roles=["employee"],
        )

    @pytest.fixture
    async def employee_resolver(self, employee_role_rule):
        """JwtRolesResolver with a rule for RedHat employees."""
        return JwtRolesResolver([employee_role_rule])

    @pytest.fixture
    async def employee_claims(self):
        """JWT claims for a RedHat employee."""
        return {
            "foo": "bar",
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:employee@redhat.com",
            "email": "employee@redhat.com",
            "realm_access": {
                "roles": [
                    "uma_authorization",
                    "redhat:employees",
                    "default-roles-redhat",
                ]
            },
        }

    @pytest.fixture
    async def non_employee_claims(self):
        """JWT claims for a non-RedHat employee."""
        return {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:user@example.com",
            "realm_access": {"roles": ["uma_authorization", "default-roles-example"]},
        }

    async def test_resolve_roles_redhat_employee(
        self, employee_resolver, employee_claims
    ):
        """Test role extraction for RedHat employee JWT."""
        assert "employee" in await employee_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_no_match(self, employee_resolver, non_employee_claims):
        """Test no roles extracted for non-RedHat employee JWT."""
        assert (
            len(
                await employee_resolver.resolve_roles(
                    claims_to_auth_tuple(non_employee_claims)
                )
            )
            == 0
        )

    async def test_negate_operator(self, employee_role_rule, non_employee_claims):
        """Test role extraction with negated operator."""
        negated_rule = employee_role_rule
        negated_rule.negate = True

        resolver = JwtRolesResolver([negated_rule])

        assert "employee" in await resolver.resolve_roles(
            claims_to_auth_tuple(non_employee_claims)
        )

    @pytest.fixture
    async def email_rule_resolver(self):
        """JwtRolesResolver with a rule for email domain."""
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.email",
                    operator=JsonPathOperator.MATCH,
                    value=r"@redhat\.com$",
                    roles=["redhat_employee"],
                )
            ]
        )

    @pytest.fixture
    async def equals_rule_resolver(self):
        """JwtRolesResolver with a rule for exact email match."""
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.foo",
                    operator=JsonPathOperator.EQUALS,
                    value=["bar"],
                    roles=["foobar"],
                )
            ]
        )

    async def test_resolve_roles_equals_operator(
        self, equals_rule_resolver, employee_claims
    ):
        """Test role extraction using EQUALS operator."""
        assert "foobar" in await equals_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    @pytest.fixture
    async def in_rule_resolver(self):
        """JwtRolesResolver with a rule for IN operator."""
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.foo",
                    operator=JsonPathOperator.IN,
                    value=[["bar"], ["baz"]],
                    roles=["in_role"],
                )
            ]
        )

    async def test_resolve_roles_in_operator(self, in_rule_resolver, employee_claims):
        """Test role extraction using IN operator."""
        assert "in_role" in await in_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_match_operator_email_domain(
        self, email_rule_resolver, employee_claims
    ):
        """Test role extraction using MATCH operator with email domain regex."""
        assert "redhat_employee" in await email_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_match_operator_no_match(
        self, email_rule_resolver, non_employee_claims
    ):
        """Test role extraction using MATCH operator with no match."""
        assert (
            len(
                await email_rule_resolver.resolve_roles(
                    claims_to_auth_tuple(non_employee_claims)
                )
            )
            == 0
        )

    async def test_resolve_roles_match_operator_invalid_regex(self):
        """Test that invalid regex patterns are rejected at rule creation time."""
        with pytest.raises(
            ValueError, match="Invalid regex pattern for MATCH operator"
        ):
            JwtRoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.MATCH,
                value="[invalid regex(",  # Invalid regex pattern
                roles=["test_role"],
            )

    async def test_resolve_roles_match_operator_non_string_pattern(self):
        """Test that non-string regex patterns are rejected at rule creation time."""
        with pytest.raises(
            ValueError, match="MATCH operator requires a string pattern"
        ):
            JwtRoleRule(
                jsonpath="$.user_id",
                operator=JsonPathOperator.MATCH,
                value=123,  # Non-string pattern
                roles=["test_role"],
            )

    async def test_resolve_roles_match_operator_non_string_value(self):
        """Test role extraction using MATCH operator with non-string match value."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.user_id",
                operator=JsonPathOperator.MATCH,
                value=r"\d+",  # Number pattern
                roles=["numeric_user"],
            )
        ]
        jwt_resolver = JwtRolesResolver(role_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "user_id": 12345,  # Non-string value
        }

        auth = ("user", "token", False, claims_to_token(jwt_claims))
        roles = await jwt_resolver.resolve_roles(auth)
        assert len(roles) == 0  # Non-string values don't match regex

    async def test_compiled_regex_property(self):
        """Test that compiled regex pattern is properly created for MATCH operator."""
        # Test MATCH operator creates compiled regex
        match_rule = JwtRoleRule(
            jsonpath="$.email",
            operator=JsonPathOperator.MATCH,
            value=r"@example\.com$",
            roles=["example_user"],
        )
        assert match_rule.compiled_regex is not None
        assert isinstance(match_rule.compiled_regex, re.Pattern)
        assert match_rule.compiled_regex.pattern == r"@example\.com$"

        # Test non-MATCH operator returns None
        equals_rule = JwtRoleRule(
            jsonpath="$.email",
            operator=JsonPathOperator.EQUALS,
            value="test@example.com",
            roles=["example_user"],
        )
        assert equals_rule.compiled_regex is None

    async def test_resolve_roles_with_no_user_token(self, employee_resolver):
        """Test NO_USER_TOKEN returns empty claims."""
        guest_tuple = (
            "user",
            "username",
            False,
            constants.NO_USER_TOKEN,
        )

        with does_not_raise():
            # We don't truly care about the absence of roles,
            # just that no exception is raised
            assert len(await employee_resolver.resolve_roles(guest_tuple)) == 0


class TestGenericAccessResolver:
    """Test cases for GenericAccessResolver."""

    @pytest.fixture
    def admin_access_rules(self):
        """Access rules with admin role for testing."""
        return [AccessRule(role="superuser", actions=[Action.ADMIN])]

    @pytest.fixture
    def multi_role_access_rules(self):
        """Access rules with multiple roles for testing."""
        return [
            AccessRule(role="user", actions=[Action.QUERY, Action.GET_MODELS]),
            AccessRule(role="moderator", actions=[Action.FEEDBACK]),
        ]

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

    def test_admin_action_with_other_actions_raises_error(self):
        """Test admin action with others raises ValueError."""
        with pytest.raises(ValueError):
            GenericAccessResolver(
                [AccessRule(role="superuser", actions=[Action.ADMIN, Action.QUERY])]
            )

    def test_admin_role_allows_all_actions(self, admin_access_rules):
        """Test admin action allows all actions via recursive check."""
        resolver = GenericAccessResolver(admin_access_rules)
        assert resolver.check_access(Action.QUERY, {"superuser"}) is True

    def test_admin_get_actions_excludes_admin_action(self, admin_access_rules):
        """Test get actions on a role with admin returns everything except ADMIN."""
        resolver = GenericAccessResolver(admin_access_rules)
        actions = resolver.get_actions({"superuser"})
        assert Action.ADMIN not in actions
        assert Action.QUERY in actions
        assert len(actions) == len(set(Action)) - 1

    def test_get_actions_for_regular_users(self, multi_role_access_rules):
        """Test non-admin user gets only their specific actions."""
        resolver = GenericAccessResolver(multi_role_access_rules)
        actions = resolver.get_actions({"user", "moderator"})
        assert actions == {Action.QUERY, Action.GET_MODELS, Action.FEEDBACK}

    async def test_responses_action_authorization(self):
        """Test that RESPONSES action can be used in authorization rules."""
        access_rules = [
            AccessRule(role="api_user", actions=[Action.RESPONSES, Action.QUERY])
        ]
        resolver = GenericAccessResolver(access_rules)

        # Test access granted for RESPONSES action
        has_access = resolver.check_access(Action.RESPONSES, {"api_user"})
        assert has_access is True

        # Test access denied for different action
        has_access = resolver.check_access(Action.FEEDBACK, {"api_user"})
        assert has_access is False

        # Test RESPONSES action is included in user's actions
        actions = resolver.get_actions({"api_user"})
        assert Action.RESPONSES in actions
        assert Action.QUERY in actions
