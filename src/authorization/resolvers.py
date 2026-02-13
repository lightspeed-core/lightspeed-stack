"""Authorization resolvers for role evaluation and access control."""

from abc import ABC, abstractmethod
import base64
import json
from typing import Any

from jsonpath_ng import parse

from authentication.interface import AuthTuple
from models.config import JwtRoleRule, AccessRule, JsonPathOperator, Action
import constants
from log import get_logger

logger = get_logger(__name__)


UserRoles = set[str]


class RoleResolutionError(Exception):
    """Custom exception for role resolution errors."""


class RolesResolver(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all role resolution strategies."""

    @abstractmethod
    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Given an auth tuple, return the list of user roles.

        Resolve and return the set of user roles extracted from the provided authentication tuple.

        Parameters:
            auth (AuthTuple): Authentication tuple (for example, a token and
            associated metadata) used to determine roles.

        Returns:
            UserRoles: A set of role names associated with the authenticated subject.
        """


class NoopRolesResolver(RolesResolver):  # pylint: disable=too-few-public-methods
    """No-op roles resolver that does not perform any role resolution."""

    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Return an empty list of roles.

        Produce an empty set of user roles; no role resolution is performed.

        The provided `auth` tuple is accepted but ignored.

        Returns:
            An empty set of role names.
        """
        _ = auth  # Unused
        return set()


def unsafe_get_claims(token: str) -> dict[str, Any]:
    """Get claims from a token without validating the signature.

    A somewhat hacky way to get JWT claims without verifying the signature.
    We assume verification has already been done during authentication.

    Returns:
        dict[str, Any]: Claims dictionary parsed from the JWT payload.
    """
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


class JwtRolesResolver(RolesResolver):  # pylint: disable=too-few-public-methods
    """Processes JWT claims with the given JSONPath rules to get roles."""

    def __init__(self, role_rules: list[JwtRoleRule]):
        """Initialize the resolver with rules.

        Create a JwtRolesResolver configured with JWT-to-role extraction rules.

        Parameters:
            role_rules (list[JwtRoleRule]): Ordered list of rules that map JWT
            claim matches to roles. Each rule specifies a JSONPath to evaluate,
            an operator to apply to matches, the roles to grant when the rule
            matches, and optional negation or regex matching.
        """
        self.role_rules = role_rules

    async def resolve_roles(self, auth: AuthTuple) -> UserRoles:
        """Extract roles from JWT claims using configured rules.

        Determine user roles by evaluating configured JwtRoleRule objects
        against JWT claims extracted from the provided AuthTuple.

        Returns:
            roles (UserRoles): Set of role names derived from all configured
            rules that match the token's claims.
        """
        jwt_claims = self._get_claims(auth)
        return {
            role
            for rule in self.role_rules
            for role in self.evaluate_role_rules(rule, jwt_claims)
        }

    @staticmethod
    def evaluate_role_rules(rule: JwtRoleRule, jwt_claims: dict[str, Any]) -> UserRoles:
        """Get roles from a JWT role rule if it matches the claims.

        Determine which roles from a JwtRoleRule apply to the provided JWT claims.

        Parameters:
            rule (JwtRoleRule): Rule containing a JSONPath expression,
            operator, and associated roles to grant when matched.
            jwt_claims (dict[str, Any]): Decoded JWT claims to evaluate against
            the rule's JSONPath.

        Returns:
            roles (set[str]): The set of roles from `rule.roles` if the rule
            matches `jwt_claims`, otherwise an empty set.
        """
        return (
            set(rule.roles)
            if JwtRolesResolver._evaluate_operator(
                rule,
                [match.value for match in parse(rule.jsonpath).find(jwt_claims)],
            )
            else set()
        )

    @staticmethod
    def _get_claims(auth: AuthTuple) -> dict[str, Any]:
        """Get the JWT claims from the auth tuple.

        Extract JWT claims from an AuthTuple.

        Parameters:
            auth (AuthTuple): Authentication tuple where the fourth element is the JWT token.

        Returns:
            dict[str, Any]: Decoded JWT claims as a dictionary. Returns an
            empty dict when the token equals constants.NO_USER_TOKEN (guest).
            The token payload is decoded without validating the JWT signature.
        """
        _, _, _, token = auth
        if token == constants.NO_USER_TOKEN:
            # No claims for guests
            return {}

        jwt_claims = unsafe_get_claims(token)
        return jwt_claims

    @staticmethod
    def _evaluate_operator(
        rule: JwtRoleRule, match: Any
    ) -> bool:  # pylint: disable=too-many-branches
        """Evaluate an operator against a match and rule.

        Determine whether a single JSONPath rule condition matches the provided value.

        Evaluates the rule's operator against the given match and applies rule.negate if set.
        Supported operators:
        - EQUALS: match equals rule.value.
        - CONTAINS: rule.value is contained in match.
        - IN: match is contained in rule.value.
        - MATCH: any string item in match matches rule.compiled_regex (if
          compiled_regex is provided).

        Parameters:
            rule (JwtRoleRule): The role rule containing operator, value,
                                negate flag, and optionally compiled_regex.
            match (Any): The value(s) produced by evaluating the JSONPath; may
                         be a single value or an iterable of values for MATCH.

        Returns:
            bool: `true` if the operator evaluation (after applying negation
            when set) succeeds, `false` otherwise.
        """
        result = False
        match rule.operator:
            case JsonPathOperator.EQUALS:
                result = match == rule.value
            case JsonPathOperator.CONTAINS:
                result = rule.value in match
            case JsonPathOperator.IN:
                result = match in rule.value
            case JsonPathOperator.MATCH:
                # Use the pre-compiled regex pattern for better performance
                if rule.compiled_regex is not None:
                    result = any(
                        isinstance(item, str) and bool(rule.compiled_regex.search(item))
                        for item in match
                    )

        if rule.negate:
            result = not result

        return result


class AccessResolver(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all access resolution strategies."""

    @abstractmethod
    def check_access(self, action: Action, user_roles: UserRoles) -> bool:
        """Check if the user has access to the specified action based on their roles.

        Determine whether any of the given user roles permit performing the specified action.

        Parameters:
            action (Action): The action to authorize.
            user_roles (UserRoles): Set of role names assigned to the user.

        Returns:
            bool: `true` if at least one role in `user_roles` grants the
            requested `action`, `false` otherwise.
        """

    @abstractmethod
    def get_actions(self, user_roles: UserRoles) -> set[Action]:
        """Get the actions that the user can perform based on their roles.

        Compute the set of actions permitted for the provided user roles.

        Parameters:
            user_roles (UserRoles): Set of role names to evaluate.

        Returns:
            set[Action]: The aggregated set of allowed actions for the given
            roles. If `ADMIN` is included in the aggregated actions, returns
            all available non-`ADMIN` actions.
        """


class NoopAccessResolver(AccessResolver):  # pylint: disable=too-few-public-methods
    """No-op access resolver that does not perform any access checks."""

    def check_access(self, action: Action, user_roles: UserRoles) -> bool:
        """Return True always, indicating access is granted.

        Grant all access unconditionally.

        Parameters:
            action (Action): Ignored.
            user_roles (UserRoles): Ignored.

        Returns:
            `true` always (access is always granted).
        """
        _ = action  # We're noop, it doesn't matter, everyone is allowed
        _ = user_roles  # We're noop, it doesn't matter, everyone is allowed
        return True

    def get_actions(self, user_roles: UserRoles) -> set[Action]:
        """Return an empty set of actions, indicating no specific actions are allowed.

        Determine the set of actions permitted for any user under the noop access resolver.

        Returns:
            allowed_actions (set[Action]): All defined `Action` values except `Action.ADMIN`.
        """
        _ = user_roles  # We're noop, it doesn't matter, everyone is allowed
        return set(Action) - {Action.ADMIN}


class GenericAccessResolver(AccessResolver):  # pylint: disable=too-few-public-methods
    """Generic role-based access resolver, should apply with most authentication methods.

    This resolver simply checks if a list of roles allow a user to perform a specific
    action. The special action ADMIN will grant the user the ability to perform any action,
    """

    def __init__(self, access_rules: list[AccessRule]):
        """Initialize the access resolver with access rules.

        Create a GenericAccessResolver and build an internal mapping of roles to allowed actions.

        Parameters:
            access_rules (list[AccessRule]): List of access rules used to
            populate the resolver. Each rule's `role` is mapped to the union of
            its `actions`.

        Raises:
            ValueError: If any rule contains the `Action.ADMIN` action together
                        with other actions.
        """
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
        """Check if the user has access to the specified action based on their roles.

        Determine whether the provided roles permit performing the specified action.

        If any role grants the ADMIN action, that role permits all non-ADMIN
        actions (ADMIN acts as a full override).

        Parameters:
            action (Action): The action to check.
            user_roles (UserRoles): The set of roles assigned to the user.

        Returns:
            true if at least one role permits the action or ADMIN override
            applies, false otherwise.
        """
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
        """Get the actions that the user can perform based on their roles.

        Determine which actions are permitted for the given user roles.

        Returns:
            allowed_actions (set[Action]): Set of actions the user may perform.
            If any role grants Action.ADMIN, returns every Action except
            Action.ADMIN.
        """
        actions = {
            action
            for role in user_roles
            for action in self._access_lookup.get(role, set())
        }

        # If the user is allowed the admin action, they can perform any action
        if Action.ADMIN in actions:
            return set(Action) - {Action.ADMIN}

        return actions
