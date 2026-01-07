"""Unit tests for JwtRoleRule model."""

import pytest

from pydantic import ValidationError

from models.config import JwtRoleRule, JsonPathOperator


def test_jwt_role_rule_missing_attributes() -> None:
    """Check the JwtRoleRule config class.

    Ensure constructing JwtRoleRule without any attributes raises a ValidationError.

    Asserts that instantiating JwtRoleRule with no fields provided raises a
    ValidationError whose message contains "validation errors".
    """
    with pytest.raises(ValidationError, match="validation errors"):
        _ = JwtRoleRule()


def test_jwt_role_rule_correct_attributes() -> None:
    """Check the JwtRoleRule config class.

    Verify that a JwtRoleRule instantiated with valid attributes is created and
    does not compile a regex for non-MATCH operators.

    Asserts that an instance is returned and that `compiled_regex` is `None`
    when the operator is not `JsonPathOperator.MATCH`.
    """
    r = JwtRoleRule(
        jsonpath="$.id",
        negate=False,
        value="xyz",
        roles=["admin"],
        operator=JsonPathOperator.EQUALS,
    )

    assert r is not None
    assert r.compiled_regex is None


def test_jwt_role_rule_invalid_json_path() -> None:
    """Check the JwtRoleRule config class.

    Verifies that constructing JwtRoleRule with an invalid JSONPath expression
    raises a ValidationError.

    Asserts the raised ValidationError contains the message "Invalid JSONPath expression".
    """
    with pytest.raises(ValidationError, match="Invalid JSONPath expression"):
        _ = JwtRoleRule(
            jsonpath="this/is/not/valid",
            negate=False,
            value="xyz",
            roles=["admin"],
            operator=JsonPathOperator.EQUALS,
        )


def test_jwt_role_rule_no_roles_specified() -> None:
    """Check the JwtRoleRule config class."""
    with pytest.raises(
        ValidationError, match="At least one role must be specified in the rule"
    ):
        _ = JwtRoleRule(
            jsonpath="$.id",
            negate=False,
            value="xyz",
            roles=[],
            operator=JsonPathOperator.EQUALS,
        )


def test_jwt_role_rule_star_role_specified() -> None:
    """Check the JwtRoleRule config class."""
    with pytest.raises(
        ValidationError, match="The wildcard '\\*' role is not allowed in role rules"
    ):
        _ = JwtRoleRule(
            jsonpath="$.id",
            negate=False,
            value="xyz",
            roles=["*"],
            operator=JsonPathOperator.EQUALS,
        )


def test_jwt_role_rule_same_roles() -> None:
    """Check the JwtRoleRule config class."""
    with pytest.raises(ValidationError, match="Roles must be unique in the rule"):
        _ = JwtRoleRule(
            jsonpath="$.id",
            negate=False,
            value="xyz",
            roles=["admin", "admin", "user"],
            operator=JsonPathOperator.EQUALS,
        )


def test_jwt_role_rule_invalid_value() -> None:
    """Check the JwtRoleRule config class."""
    with pytest.raises(
        ValidationError, match="MATCH operator requires a string pattern"
    ):
        _ = JwtRoleRule(
            jsonpath="$.id",
            negate=False,
            value=True,  # not a string
            roles=["admin", "user"],
            operator=JsonPathOperator.MATCH,
        )


def test_jwt_role_rule_valid_regexp() -> None:
    """Check the JwtRoleRule config class."""
    j = JwtRoleRule(
        jsonpath="$.id",
        negate=False,
        value=".*",  # valid regexp
        roles=["admin", "user"],
        operator=JsonPathOperator.MATCH,
    )
    assert j.compiled_regex is not None


def test_jwt_role_rule_invalid_regexp() -> None:
    """Check the JwtRoleRule config class.

    Ensure creating a JwtRoleRule with an invalid regex pattern for the MATCH
    operator raises a ValidationError.

    Attempts to construct JwtRoleRule with operator set to
    JsonPathOperator.MATCH and a malformed regex value; the constructor must
    raise a ValidationError with message "Invalid regex pattern for MATCH
    operator".

    Raises:
        ValidationError: if the provided regex pattern for MATCH is invalid
        (message contains "Invalid regex pattern for MATCH operator").
    """
    with pytest.raises(
        ValidationError, match="Invalid regex pattern for MATCH operator"
    ):
        _ = JwtRoleRule(
            jsonpath="$.id",
            negate=False,
            value="[[[",  # invalid regexp
            roles=["admin", "user"],
            operator=JsonPathOperator.MATCH,
        )
