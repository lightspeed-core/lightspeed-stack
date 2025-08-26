"""Authorization resolvers for role evaluation and access control."""

from abc import ABC, abstractmethod
import json
import logging
from typing import Any

from jsonpath_ng import parse

from auth.interface import AuthTuple
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action

logger = logging.getLogger(__name__)


UserRoles = set[str]


class RoleResolutionError(Exception):
    """Custom exception for role resolution errors."""


class RolesResolver(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all role resolution strategies."""

    @abstractmethod
    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Given an auth tuple, return the list of user roles."""


class NoopRolesResolver(RolesResolver):  # pylint: disable=too-few-public-methods
    """No-op roles resolver that does not perform any role resolution."""

    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Return an empty list of roles."""
        _ = auth  # Unused
        return set()


class JwtRolesResolver(RolesResolver):  # pylint: disable=too-few-public-methods
    """Processes JWT claims with the given JSONPath rules to get roles."""

    def __init__(self, role_rules: list[JwtRoleRule]):
        """Initialize the resolver with rules."""
        self.role_rules = role_rules

    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Extract roles from JWT claims using configured rules."""
        jwt_claims = self._get_claims(auth)
        return {
            role
            for rule in self.role_rules
            for role in self.evaluate_role_rules(rule, jwt_claims)
        }

    @staticmethod
    def evaluate_role_rules(rule: JwtRoleRule, jwt_claims: dict[str, Any]) -> UserRoles:
        """Get roles from a JWT role rule if it matches the claims."""
        return (
            set(rule.roles)
            if JwtRolesResolver._evaluate_operator(
                rule.negate,
                [match.value for match in parse(rule.jsonpath).find(jwt_claims)],
                rule.operator,
                rule.value,
            )
            else set()
        )

    @staticmethod
    def _get_claims(auth: AuthTuple) -> dict[str, Any]:
        """Get the JWT claims from the auth tuple."""
        _, _, token = auth
        jwt_claims = json.loads(token)

        if not jwt_claims:
            raise RoleResolutionError(
                "Invalid authentication token: no JWT claims found"
            )

        return jwt_claims

    @staticmethod
    def _evaluate_operator(
        negate: bool, match: Any, operator: JsonPathOperator, value: Any
    ) -> bool:  # pylint: disable=too-many-branches
        """Evaluate an operator against a match and value."""
        result = False
        match operator:
            case JsonPathOperator.EQUALS:
                result = match == value
            case JsonPathOperator.CONTAINS:
                result = value in match
            case JsonPathOperator.IN:
                result = match in value

        if negate:
            result = not result

        return result


class AccessResolver(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all access resolution strategies."""

    @abstractmethod
    def check_access(self, action: Action, user_roles: UserRoles) -> bool:
        """Check if the user has access to the specified action based on their roles."""

    @abstractmethod
    def get_actions(self, user_roles: UserRoles) -> set[Action]:
        """Get the actions that the user can perform based on their roles."""


class NoopAccessResolver(AccessResolver):  # pylint: disable=too-few-public-methods
    """No-op access resolver that does not perform any access checks."""

    def check_access(self, action: Action, user_roles: UserRoles) -> bool:
        """Return True always, indicating access is granted."""
        _ = action  # We're noop, it doesn't matter, everyone is allowed
        _ = user_roles  # We're noop, it doesn't matter, everyone is allowed
        return True

    def get_actions(self, user_roles: UserRoles) -> set[Action]:
        """Return an empty set of actions, indicating no specific actions are allowed."""
        _ = user_roles  # We're noop, it doesn't matter, everyone is allowed
        return set(Action) - {Action.ADMIN}


class GenericAccessResolver(AccessResolver):  # pylint: disable=too-few-public-methods
    """Generic role-based access resolver, should apply with most authentication methods.

    This resolver simply checks if a list of roles allow a user to perform a specific
    action. The special action ADMIN will grant the user the ability to perform any action,
    """

    def __init__(self, access_rules: list[AccessRule]):
        """Initialize the access resolver with access rules."""
        for rule in access_rules:
            # Since this is nonsensical, it might be a mistake, so hard fail
            if Action.ADMIN in rule.actions and len(rule.actions) > 1:
                raise ValueError(
                    "Access rule with 'admin' action cannot have other actions"
                )

        self.access_rules = access_rules

        # Build a lookup table for access rules
        self._access_lookup: dict[str, set[Action]] = {}
        for rule in access_rules:
            if rule.role not in self._access_lookup:
                self._access_lookup[rule.role] = set()
            self._access_lookup[rule.role].update(rule.actions)

    def check_access(self, action: Action, user_roles: UserRoles) -> bool:
        """Check if the user has access to the specified action based on their roles."""
        if action != Action.ADMIN and self.check_access(Action.ADMIN, user_roles):
            # Recurse to check if the roles allow the user to perform the admin action,
            # if they do, then we allow any action
            return True

        for role in user_roles:
            if role in self._access_lookup and action in self._access_lookup[role]:
                logger.debug(
                    "Access granted: role '%s' can perform action '%s'", role, action
                )
                return True

        logger.debug(
            "Access denied: roles %s cannot perform action '%s'", user_roles, action
        )
        return False

    def get_actions(self, user_roles: UserRoles) -> set[Action]:
        """Get the actions that the user can perform based on their roles."""
        actions = {
            action
            for role in user_roles
            for action in self._access_lookup.get(role, set())
        }

        # If the user is allowed the admin action, they can perform any action
        if Action.ADMIN in actions:
            return set(Action) - {Action.ADMIN}

        return actions
