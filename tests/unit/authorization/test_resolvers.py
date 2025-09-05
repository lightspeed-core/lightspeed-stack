"""Unit tests for the authorization resolvers."""

import json
import base64
import re

import pytest

from authorization.resolvers import JwtRolesResolver, GenericAccessResolver
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action


def claims_to_token(claims: dict) -> str:
    """Convert JWT claims dictionary to a JSON string token."""

    string_claims = json.dumps(claims)
    b64_encoded_claims = (
        base64.urlsafe_b64encode(string_claims.encode()).decode().rstrip("=")
    )

    return f"foo_header.{b64_encoded_claims}.foo_signature"


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
        auth = ("user", "token", False, claims_to_token(jwt_claims))
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
        auth = ("user", "token", False, claims_to_token(jwt_claims))
        roles = await jwt_resolver.resolve_roles(auth)
        assert len(roles) == 0

    async def test_resolve_roles_match_operator_email_domain(self):
        """Test role extraction using MATCH operator with email domain regex."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.MATCH,
                value=r"@redhat\.com$",
                roles=["redhat_employee"],
            )
        ]
        jwt_resolver = JwtRolesResolver(role_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:employee@redhat.com",
            "email": "employee@redhat.com",
        }

        auth = ("user", "token", False, claims_to_token(jwt_claims))
        roles = await jwt_resolver.resolve_roles(auth)
        assert "redhat_employee" in roles

    async def test_resolve_roles_match_operator_no_match(self):
        """Test role extraction using MATCH operator with no match."""
        role_rules = [
            JwtRoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.MATCH,
                value=r"@redhat\.com$",
                roles=["redhat_employee"],
            )
        ]
        jwt_resolver = JwtRolesResolver(role_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:123:user@example.com",
            "email": "user@example.com",
        }

        auth = ("user", "token", False, claims_to_token(jwt_claims))
        roles = await jwt_resolver.resolve_roles(auth)
        assert len(roles) == 0

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
