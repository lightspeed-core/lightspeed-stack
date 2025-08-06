"""Authorization engine for role evaluation and access control."""

import logging
from typing import Any

from jsonpath_ng import parse
from jsonpath_ng.exceptions import JSONPathError

from .models import RoleRule, AccessRule, JsonPathOperator, Action

logger = logging.getLogger(__name__)


class AuthorizationEngine:
    """Engine for evaluating authorization rules."""

    def __init__(self, role_rules: list[RoleRule], access_rules: list[AccessRule]):
        """Initialize the authorization engine.

        Args:
            role_rules: Rules for extracting roles from JWT claims
            access_rules: Rules for role-based access control
        """
        self.role_rules = role_rules
        self.access_rules = access_rules

        # Build a lookup table for access rules
        self._access_lookup: dict[str, set[Action]] = {}
        for rule in access_rules:
            if rule.role not in self._access_lookup:
                self._access_lookup[rule.role] = set()
            self._access_lookup[rule.role].update(rule.actions)

    def extract_roles_from_jwt(self, jwt_claims: dict[str, Any]) -> list[str]:
        """Extract roles from JWT claims using configured rules.

        Args:
            jwt_claims: Decoded JWT claims

        Returns:
            List of roles extracted from the JWT
        """
        extracted_roles = []

        for rule in self.role_rules:
            try:
                # Parse the JSONPath expression
                jsonpath_expr = parse(rule.jsonpath)

                # Find all matches in the JWT claims
                matches = [match.value for match in jsonpath_expr.find(jwt_claims)]

                if self._evaluate_rule(matches, rule):
                    extracted_roles.extend(rule.roles)
                    logger.debug(
                        "Rule matched: %s %s %s -> roles: %s",
                        rule.jsonpath,
                        rule.operator,
                        rule.value,
                        rule.roles,
                    )

            except JSONPathError as e:
                logger.warning("Invalid JSONPath expression '%s': %s", rule.jsonpath, e)
            except (ValueError, TypeError, AttributeError) as e:
                logger.error("Error evaluating rule %s: %s", rule.jsonpath, e)

        # Remove duplicates while preserving order
        unique_roles = []
        seen = set()
        for role in extracted_roles:
            if role not in seen:
                unique_roles.append(role)
                seen.add(role)

        logger.debug("Extracted roles from JWT: %s", unique_roles)
        return unique_roles

    def _evaluate_rule(self, matches: list[Any], rule: RoleRule) -> bool:
        """Evaluate a role rule against matched values.

        Args:
            matches: Values found by JSONPath expression
            rule: Rule to evaluate

        Returns:
            True if the rule matches, False otherwise
        """
        if not matches:
            return False

        for match in matches:
            if self._evaluate_operator(match, rule.operator, rule.value):
                return True

        return False

    def _evaluate_operator(
        self, match: Any, operator: JsonPathOperator, value: Any
    ) -> bool:
        """Evaluate an operator against a match and value.

        Args:
            match: Value from JSONPath match
            operator: Operator to use for comparison
            value: Value to compare against

        Returns:
            True if the operator condition is met, False otherwise
        """
        try:
            if operator == JsonPathOperator.EQUALS:
                return match == value
            if operator == JsonPathOperator.NOT_EQUALS:
                return match != value
            if operator == JsonPathOperator.CONTAINS:
                if isinstance(match, str) and isinstance(value, str):
                    return value in match
                if isinstance(match, (list, tuple)):
                    return value in match
                return False
            if operator == JsonPathOperator.NOT_CONTAINS:
                if isinstance(match, str) and isinstance(value, str):
                    return value not in match
                if isinstance(match, (list, tuple)):
                    return value not in match
                return True
            if operator == JsonPathOperator.IN:
                if isinstance(value, (list, tuple)):
                    return match in value
                return False
            if operator == JsonPathOperator.NOT_IN:
                if isinstance(value, (list, tuple)):
                    return match not in value
                return True

            logger.warning("Unknown operator: %s", operator)
            return False
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning("Error evaluating operator %s: %s", operator, e)
            return False

    def check_access(self, roles: list[str], action: Action) -> bool:
        """Check if any of the given roles has access to the specified action.

        Args:
            roles: List of user roles
            action: Action to check access for

        Returns:
            True if access is granted, False otherwise
        """
        for role in roles:
            if role in self._access_lookup and action in self._access_lookup[role]:
                logger.debug(
                    "Access granted: role '%s' can perform action '%s'", role, action
                )
                return True

        logger.debug(
            "Access denied: roles %s cannot perform action '%s'", roles, action
        )
        return False

    def get_allowed_actions(self, roles: list[str]) -> set[Action]:
        """Get all actions allowed for the given roles.

        Args:
            roles: List of user roles

        Returns:
            Set of allowed actions
        """
        allowed_actions = set()
        for role in roles:
            if role in self._access_lookup:
                allowed_actions.update(self._access_lookup[role])

        return allowed_actions
