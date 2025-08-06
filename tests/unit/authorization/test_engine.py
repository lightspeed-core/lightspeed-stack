"""Unit tests for authorization engine."""

from authorization.engine import AuthorizationEngine
from authorization.models import RoleRule, AccessRule, JsonPathOperator, Action


class TestAuthorizationEngine:
    """Test cases for AuthorizationEngine."""

    def test_init(self):
        """Test engine initialization."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            )
        ]
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS])
        ]

        engine = AuthorizationEngine(role_rules, access_rules)

        assert engine.role_rules == role_rules
        assert engine.access_rules == access_rules
        assert "employee" in engine._access_lookup  # pylint: disable=protected-access
        assert (
            Action.QUERY in engine._access_lookup["employee"]
        )  # pylint: disable=protected-access
        assert (
            Action.GET_MODELS in engine._access_lookup["employee"]
        )  # pylint: disable=protected-access

    def test_extract_roles_from_jwt_redhat_employee(self):
        """Test role extraction for RedHat employee JWT."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            )
        ]
        access_rules = []
        engine = AuthorizationEngine(role_rules, access_rules)

        jwt_claims = {
            "exp": 1754489339,
            "iat": 1754488439,
            "sub": "f:528d76ff-f708-43ed-8cd5-fe16f4fe0ce6:otuchfel@redhat.com",
            "realm_access": {
                "roles": [
                    "authenticated",
                    "redhat:employees",
                    "portal_manage_subscriptions",
                ]
            },
            "account_number": "5910538",
            "preferred_username": "otuchfel@redhat.com",
            "email": "otuchfel@redhat.com",
        }

        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["employee"]

    def test_extract_roles_from_jwt_no_match(self):
        """Test role extraction when no rules match."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            )
        ]
        access_rules = []
        engine = AuthorizationEngine(role_rules, access_rules)

        jwt_claims = {
            "exp": 1754489339,
            "realm_access": {"roles": ["authenticated", "portal_user"]},
        }

        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_extract_roles_multiple_rules(self):
        """Test role extraction with multiple rules."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat:employees",
                roles=["employee"],
            ),
            RoleRule(
                jsonpath="$.account_number",
                operator=JsonPathOperator.EQUALS,
                value="5910538",
                roles=["premium_user"],
            ),
            RoleRule(
                jsonpath="$.preferred_username",
                operator=JsonPathOperator.CONTAINS,
                value="@redhat.com",
                roles=["redhat_user"],
            ),
        ]
        access_rules = []
        engine = AuthorizationEngine(role_rules, access_rules)

        jwt_claims = {
            "realm_access": {"roles": ["authenticated", "redhat:employees"]},
            "account_number": "5910538",
            "preferred_username": "otuchfel@redhat.com",
        }

        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert set(roles) == {"employee", "premium_user", "redhat_user"}

    def test_operators_equals(self):
        """Test equals operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.account_number",
                operator=JsonPathOperator.EQUALS,
                value="12345",
                roles=["test_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match
        jwt_claims = {"account_number": "12345"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["test_user"]

        # No match
        jwt_claims = {"account_number": "54321"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_operators_not_equals(self):
        """Test not equals operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.type",
                operator=JsonPathOperator.NOT_EQUALS,
                value="service",
                roles=["human_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match (not service)
        jwt_claims = {"type": "User"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["human_user"]

        # No match (is service)
        jwt_claims = {"type": "service"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_operators_contains(self):
        """Test contains operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.CONTAINS,
                value="@redhat.com",
                roles=["redhat_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match
        jwt_claims = {"email": "user@redhat.com"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["redhat_user"]

        # No match
        jwt_claims = {"email": "user@example.com"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_operators_not_contains(self):
        """Test not contains operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.NOT_CONTAINS,
                value="@test.com",
                roles=["production_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match (does not contain test.com)
        jwt_claims = {"email": "user@redhat.com"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["production_user"]

        # No match (contains test.com)
        jwt_claims = {"email": "user@test.com"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_operators_in(self):
        """Test in operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.account_number",
                operator=JsonPathOperator.IN,
                value=["12345", "67890", "11111"],
                roles=["privileged_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match
        jwt_claims = {"account_number": "67890"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["privileged_user"]

        # No match
        jwt_claims = {"account_number": "99999"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_operators_not_in(self):
        """Test not in operator."""
        role_rules = [
            RoleRule(
                jsonpath="$.account_number",
                operator=JsonPathOperator.NOT_IN,
                value=["blocked1", "blocked2"],
                roles=["allowed_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        # Match (not in blocked list)
        jwt_claims = {"account_number": "12345"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["allowed_user"]

        # No match (in blocked list)
        jwt_claims = {"account_number": "blocked1"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles

    def test_invalid_jsonpath(self):
        """Test handling of invalid JSONPath expressions."""
        role_rules = [
            RoleRule(
                jsonpath="$.invalid[syntax",  # Invalid JSONPath
                operator=JsonPathOperator.EQUALS,
                value="test",
                roles=["test_user"],
            )
        ]
        engine = AuthorizationEngine(role_rules, [])

        jwt_claims = {"valid_field": "test"}
        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert not roles  # Should handle gracefully

    def test_check_access_granted(self):
        """Test access check when permission is granted."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS]),
            AccessRule(role="admin", actions=[Action.GET_CONFIG, Action.GET_METRICS]),
        ]
        engine = AuthorizationEngine([], access_rules)

        # Employee can query
        assert engine.check_access(["employee"], Action.QUERY) is True
        assert engine.check_access(["employee"], Action.GET_MODELS) is True

        # Admin can access config
        assert engine.check_access(["admin"], Action.GET_CONFIG) is True

        # User with multiple roles
        assert engine.check_access(["employee", "admin"], Action.QUERY) is True
        assert engine.check_access(["employee", "admin"], Action.GET_CONFIG) is True

    def test_check_access_denied(self):
        """Test access check when permission is denied."""
        access_rules = [AccessRule(role="employee", actions=[Action.QUERY])]
        engine = AuthorizationEngine([], access_rules)

        # Employee cannot access config
        assert engine.check_access(["employee"], Action.GET_CONFIG) is False

        # Unknown role
        assert engine.check_access(["unknown"], Action.QUERY) is False

        # No roles
        assert engine.check_access([], Action.QUERY) is False

    def test_get_allowed_actions(self):
        """Test getting all allowed actions for roles."""
        access_rules = [
            AccessRule(role="employee", actions=[Action.QUERY, Action.GET_MODELS]),
            AccessRule(role="admin", actions=[Action.GET_CONFIG, Action.GET_METRICS]),
        ]
        engine = AuthorizationEngine([], access_rules)

        # Single role
        allowed = engine.get_allowed_actions(["employee"])
        assert allowed == {Action.QUERY, Action.GET_MODELS}

        # Multiple roles
        allowed = engine.get_allowed_actions(["employee", "admin"])
        assert allowed == {
            Action.QUERY,
            Action.GET_MODELS,
            Action.GET_CONFIG,
            Action.GET_METRICS,
        }

        # Unknown role
        allowed = engine.get_allowed_actions(["unknown"])
        assert allowed == set()

    def test_complex_jsonpath_array_access(self):
        """Test complex JSONPath expressions with array access."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.EQUALS,
                value="redhat:employees",
                roles=["employee"],
            ),
            RoleRule(
                jsonpath="$.resource_access.account.roles[0]",
                operator=JsonPathOperator.EQUALS,
                value="manage-account",
                roles=["account_manager"],
            ),
        ]
        engine = AuthorizationEngine(role_rules, [])

        jwt_claims = {
            "realm_access": {"roles": ["authenticated", "redhat:employees"]},
            "resource_access": {
                "account": {"roles": ["manage-account", "view-profile"]}
            },
        }

        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert set(roles) == {"employee", "account_manager"}

    def test_duplicate_roles_removed(self):
        """Test that duplicate roles are removed while preserving order."""
        role_rules = [
            RoleRule(
                jsonpath="$.realm_access.roles[*]",
                operator=JsonPathOperator.CONTAINS,
                value="redhat",
                roles=["redhat_user"],
            ),
            RoleRule(
                jsonpath="$.email",
                operator=JsonPathOperator.CONTAINS,
                value="@redhat.com",
                roles=["redhat_user"],  # Same role as above
            ),
        ]
        engine = AuthorizationEngine(role_rules, [])

        jwt_claims = {
            "realm_access": {"roles": ["redhat:employees"]},
            "email": "user@redhat.com",
        }

        roles = engine.extract_roles_from_jwt(jwt_claims)
        assert roles == ["redhat_user"]  # Should only appear once
