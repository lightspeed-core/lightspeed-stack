"""Unit tests for the authorization resolvers."""

import json
import base64
import re
from contextlib import nullcontext as does_not_raise

from typing import Any
import pytest

from authentication.interface import AuthTuple
from authorization.resolvers import JwtRolesResolver, GenericAccessResolver
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action
import constants


def claims_to_token(claims: dict) -> str:
    """Convert JWT claims dictionary to a JSON string token.

    Create a JWT-like token by encoding the provided claims into a
    base64url JSON payload and wrapping it with placeholder header
    and signature.

    Parameters:
        claims (dict): JWT claims to serialize and encode.

    Returns:
        token (str): A token string in the form "foo_header.<base64url(JSON
        claims)>.foo_signature", where the payload is base64url-encoded without
        padding.
    """
    string_claims = json.dumps(claims)
    b64_encoded_claims = (
        base64.urlsafe_b64encode(string_claims.encode()).decode().rstrip("=")
    )

    return f"foo_header.{b64_encoded_claims}.foo_signature"


def claims_to_auth_tuple(claims: dict) -> AuthTuple:
    """
    Builds an AuthTuple from JWT claims for use in tests.

    Parameters:
        claims (dict): JWT claims to encode into the returned token.

    Returns:
        AuthTuple: A 4-tuple (username, token_id, expired, jwt_token) where
        `username` is the fixed string "user", `token_id` is the fixed string
        "token", `expired` is False, and `jwt_token` is the token produced from
        `claims`.
    """
    return ("user", "token", False, claims_to_token(claims))


class TestJwtRolesResolver:
    """Test cases for JwtRolesResolver."""

    @pytest.fixture
    async def employee_role_rule(self) -> JwtRoleRule:
        """Role rule for RedHat employees.

        JwtRoleRule that grants the "employee" role when
        `realm_access.roles` contains "redhat:employees".

        Returns:
            JwtRoleRule: Configured to match `$.realm_access.roles[*]` with a
            CONTAINS operator for the value `"redhat:employees"` and map
            matches to the `["employee"]` role.
        """
        return JwtRoleRule(
            jsonpath="$.realm_access.roles[*]",
            operator=JsonPathOperator.CONTAINS,
            value="redhat:employees",
            roles=["employee"],
            negate=False,
        )

    @pytest.fixture
    async def employee_resolver(
        self, employee_role_rule: JwtRoleRule
    ) -> JwtRolesResolver:
        """JwtRolesResolver with a rule for RedHat employees.

        Create a JwtRolesResolver configured with the provided
        employee role rule.

        Parameters:
            employee_role_rule (JwtRoleRule): Rule used to map JWT claims to the employee role.

        Returns:
            JwtRolesResolver: Resolver initialized with the given rule.
        """
        return JwtRolesResolver([employee_role_rule])

    @pytest.fixture
    async def employee_claims(self) -> dict[str, Any]:
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
    async def non_employee_claims(self) -> dict[str, Any]:
        """JWT claims for a non-RedHat employee.

        Provide JWT claims representing a non-Red Hat employee.

        Returns:
            dict: JWT claims where `realm_access.roles` does not include the Red Hat employee role
            (e.g., contains `"uma_authorization"` and `"default-roles-example"`).
        """
        return {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:user@example.com",
            "realm_access": {"roles": ["uma_authorization", "default-roles-example"]},
        }

    async def test_resolve_roles_redhat_employee(
        self, employee_resolver: JwtRolesResolver, employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction for RedHat employee JWT."""
        assert "employee" in await employee_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_no_match(
        self, employee_resolver: JwtRolesResolver, non_employee_claims: dict[str, Any]
    ) -> None:
        """Test no roles extracted for non-RedHat employee JWT."""
        assert (
            len(
                await employee_resolver.resolve_roles(
                    claims_to_auth_tuple(non_employee_claims)
                )
            )
            == 0
        )

    async def test_negate_operator(
        self, employee_role_rule: JwtRoleRule, non_employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction with negated operator."""
        negated_rule = employee_role_rule
        negated_rule.negate = True

        resolver = JwtRolesResolver([negated_rule])

        assert "employee" in await resolver.resolve_roles(
            claims_to_auth_tuple(non_employee_claims)
        )

    @pytest.fixture
    async def email_rule_resolver(self) -> JwtRolesResolver:
        """JwtRolesResolver with a rule for email domain.

        Returns:
            JwtRolesResolver: Resolver configured with a single MATCH rule on
            `$.email` using the regex with RedHat domain that yields the
            `redhat_employee` role.
        """
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.email",
                    operator=JsonPathOperator.MATCH,
                    value=r"@redhat\.com$",
                    roles=["redhat_employee"],
                    negate=False,
                )
            ]
        )

    @pytest.fixture
    async def equals_rule_resolver(self) -> JwtRolesResolver:
        """JwtRolesResolver with a rule for exact email match.

        Returns:
            JwtRolesResolver: Resolver configured with one JwtRoleRule
            (jsonpath="$.foo", operator=EQUALS, value=["bar"],
            roles=["foobar"]).
        """
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.foo",
                    operator=JsonPathOperator.EQUALS,
                    value=["bar"],
                    roles=["foobar"],
                    negate=False,
                )
            ]
        )

    async def test_resolve_roles_equals_operator(
        self, equals_rule_resolver: JwtRolesResolver, employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction using EQUALS operator."""
        assert "foobar" in await equals_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    @pytest.fixture
    async def in_rule_resolver(self) -> JwtRolesResolver:
        """JwtRolesResolver with a rule for IN operator.

        Returns:
            JwtRolesResolver: Resolver that maps the JSONPath value ['bar'] or
            ['baz'] at "$.foo" to the role "in_role".
        """
        return JwtRolesResolver(
            [
                JwtRoleRule(
                    jsonpath="$.foo",
                    operator=JsonPathOperator.IN,
                    value=[["bar"], ["baz"]],
                    roles=["in_role"],
                    negate=False,
                )
            ]
        )

    async def test_resolve_roles_in_operator(
        self, in_rule_resolver: JwtRolesResolver, employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction using IN operator."""
        assert "in_role" in await in_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_match_operator_email_domain(
        self, email_rule_resolver: JwtRolesResolver, employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction using MATCH operator with email domain regex."""
        assert "redhat_employee" in await email_rule_resolver.resolve_roles(
            claims_to_auth_tuple(employee_claims)
        )

    async def test_resolve_roles_match_operator_no_match(
        self, email_rule_resolver: JwtRolesResolver, non_employee_claims: dict[str, Any]
    ) -> None:
        """Test role extraction using MATCH operator with no match."""
        assert (
            len(
                await email_rule_resolver.resolve_roles(
                    claims_to_auth_tuple(non_employee_claims)
                )
            )
            == 0
        )

    async def test_resolve_roles_match_operator_invalid_regex(self) -> None:
        """Test that invalid regex patterns are rejected at rule creation time."""
        with pytest.raises(
            ValueError, match="Invalid regex pattern for MATCH operator"
        ):
            JwtRoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.MATCH,
                value="[invalid regex(",  # Invalid regex pattern
                roles=["test_role"],
                negate=False,
            )

    async def test_resolve_roles_match_operator_non_string_pattern(self) -> None:
        """Test that non-string regex patterns are rejected at rule creation time."""
        with pytest.raises(
            ValueError, match="MATCH operator requires a string pattern"
        ):
            JwtRoleRule(
                jsonpath="$.user_id",
                operator=JsonPathOperator.MATCH,
                value=123,  # Non-string pattern
                roles=["test_role"],
                negate=False,
            )

    async def test_resolve_roles_match_operator_non_string_value(self) -> None:
        """Test role extraction using MATCH operator with non-string match value."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.user_id",
                operator=JsonPathOperator.MATCH,
                value=r"\d+",  # Number pattern
                roles=["numeric_user"],
                negate=False,
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

    async def test_compiled_regex_property(self) -> None:
        """Test that compiled regex pattern is properly created for MATCH operator."""
        # Test MATCH operator creates compiled regex
        match_rule = JwtRoleRule(
            jsonpath="$.email",
            operator=JsonPathOperator.MATCH,
            value=r"@example\.com$",
            roles=["example_user"],
            negate=False,
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
            negate=False,
        )
        assert equals_rule.compiled_regex is None

    async def test_resolve_roles_with_no_user_token(
        self, employee_resolver: JwtRolesResolver
    ) -> None:
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
    def admin_access_rules(self) -> list[AccessRule]:
        """Access rules with admin role for testing.

        Returns:
            list[AccessRule]: A list with one AccessRule for role "superuser"
            whose actions include Action.ADMIN.
        """
        return [AccessRule(role="superuser", actions=[Action.ADMIN])]

    @pytest.fixture
    def multi_role_access_rules(self) -> list[AccessRule]:
        """Access rules with multiple roles for testing.

        Returns:
            list[AccessRule]: A list containing two AccessRule instances — the
            "user" role allowing `Action.QUERY` and `Action.GET_MODELS`, and
            the "moderator" role allowing `Action.FEEDBACK`.
        """
        return [
            AccessRule(role="user", actions=[Action.QUERY, Action.GET_MODELS]),
            AccessRule(role="moderator", actions=[Action.FEEDBACK]),
        ]

    async def test_check_access_with_valid_role(self) -> None:
        """Test access check with valid role."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        # Test access granted
        has_access = resolver.check_access(Action.QUERY, {"employee"})
        assert has_access is True

        # Test access denied
        has_access = resolver.check_access(Action.FEEDBACK, {"employee"})
        assert has_access is False

    async def test_check_access_with_invalid_role(self) -> None:
        """Test access check with invalid role."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        has_access = resolver.check_access(Action.QUERY, {"visitor"})
        assert has_access is False

    async def test_check_access_with_no_roles(self) -> None:
        """Test access check with no roles."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]
        resolver = GenericAccessResolver(access_rules)

        has_access = resolver.check_access(Action.QUERY, set())
        assert has_access is False

    def test_admin_action_with_other_actions_raises_error(self) -> None:
        """Test admin action with others raises ValueError."""
        with pytest.raises(ValueError):
            GenericAccessResolver(
                [AccessRule(role="superuser", actions=[Action.ADMIN, Action.QUERY])]
            )

    def test_admin_role_allows_all_actions(
        self, admin_access_rules: list[AccessRule]
    ) -> None:
        """Test admin action allows all actions via recursive check."""
        resolver = GenericAccessResolver(admin_access_rules)
        assert resolver.check_access(Action.QUERY, {"superuser"}) is True

    def test_admin_get_actions_excludes_admin_action(
        self, admin_access_rules: list[AccessRule]
    ) -> None:
        """Test get actions on a role with admin returns everything except ADMIN."""
        resolver = GenericAccessResolver(admin_access_rules)
        actions = resolver.get_actions({"superuser"})
        assert Action.ADMIN not in actions
        assert Action.QUERY in actions
        assert len(actions) == len(set(Action)) - 1

    def test_get_actions_for_regular_users(
        self, multi_role_access_rules: list[AccessRule]
    ) -> None:
        """Test non-admin user gets only their specific actions."""
        resolver = GenericAccessResolver(multi_role_access_rules)
        actions = resolver.get_actions({"user", "moderator"})
        assert actions == {Action.QUERY, Action.GET_MODELS, Action.FEEDBACK}
