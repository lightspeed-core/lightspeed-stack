"""Authorization middleware and decorators."""

from functools import lru_cache, wraps
from typing import Any, Callable, Optional, Tuple

from fastapi import HTTPException
from starlette.requests import Request

import constants
from authorization.resolvers import (
    AccessResolver,
    GenericAccessResolver,
    JwtRolesResolver,
    NoopAccessResolver,
    NoopRolesResolver,
    RolesResolver,
)
from configuration import configuration
from log import get_logger
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
)

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_authorization_resolvers() -> Tuple[RolesResolver, AccessResolver]:
    """Get authorization resolvers from configuration (cached).

    Return the configured RolesResolver and AccessResolver based on
    authentication and authorization settings.

    The selection mirrors configuration: returns noop resolvers for
    NOOP/K8S/NOOP_WITH_TOKEN or when JWT role rules or authorization access
    rules are not set; returns JwtRolesResolver and GenericAccessResolver when
    JWK_TOKEN configuration provides role and access rules. The result is
    cached to avoid recomputing resolvers.

    Returns:
        tuple[RolesResolver, AccessResolver]: (roles_resolver, access_resolver)
        appropriate for the current configuration.
    """
    authorization_cfg = configuration.authorization_configuration
    authentication_config = configuration.authentication_configuration

    match authentication_config.module:
        case (
            constants.AUTH_MOD_NOOP
            | constants.AUTH_MOD_K8S
            | constants.AUTH_MOD_NOOP_WITH_TOKEN
            | constants.AUTH_MOD_APIKEY_TOKEN
        ):
            return (
                NoopRolesResolver(),
                NoopAccessResolver(),
            )
        case constants.AUTH_MOD_JWK_TOKEN:
            jwt_role_rules_unset = (
                len(
                    authentication_config.jwk_configuration.jwt_configuration.role_rules
                )
            ) == 0

            authz_access_rules_unset = len(authorization_cfg.access_rules) == 0

            if jwt_role_rules_unset or authz_access_rules_unset:
                return NoopRolesResolver(), NoopAccessResolver()

            return (
                JwtRolesResolver(
                    role_rules=(
                        authentication_config.jwk_configuration.jwt_configuration.role_rules
                    )
                ),
                GenericAccessResolver(authorization_cfg.access_rules),
            )

        case constants.AUTH_MOD_RH_IDENTITY:
            # rh-identity uses access rules for authorization, but doesn't extract
            # roles from the identity header - all authenticated users get the "*" role
            if len(authorization_cfg.access_rules) == 0:
                return NoopRolesResolver(), NoopAccessResolver()

            return (
                NoopRolesResolver(),
                GenericAccessResolver(authorization_cfg.access_rules),
            )

        case _:
            response = InternalServerErrorResponse.generic()
            raise HTTPException(**response.model_dump())


async def _perform_authorization_check(
    action: Action, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Perform authorization check - common logic for all decorators.

    Performs role resolution and access verification for the supplied `action`
    using configured resolvers. Expects `kwargs` to contain an `auth` value
    from the authentication dependency; if a Request is present in `args` or
    `kwargs` its `state.authorized_actions` will be set to the set of actions
    the resolved roles are authorized to perform.

    Parameters:
        action (Action): The action to authorize.
        args (tuple[Any, ...]): Positional arguments passed to the endpoint;
        used to locate a Request instance if present.
        kwargs (dict[str, Any]): Keyword arguments passed to the endpoint; must
        include `auth` (authentication info) and may include `request`.

    Returns:
        none

    Raises:
        HTTPException: with 500 Internal Server Error if `auth` is missing from `kwargs`.
        HTTPException: with 403 Forbidden if the resolved roles are not
                       permitted to perform `action`.
    """
    role_resolver, access_resolver = get_authorization_resolvers()

    try:
        auth = kwargs["auth"]
    except KeyError as exc:
        logger.error(
            "Authorization only allowed on endpoints that accept "
            "'auth: Any = Depends(get_auth_dependency())'"
        )
        response = InternalServerErrorResponse.generic()
        raise HTTPException(**response.model_dump()) from exc

    # Everyone gets the everyone (aka *) role
    everyone_roles = {"*"}

    user_roles = await role_resolver.resolve_roles(auth) | everyone_roles

    if not access_resolver.check_access(action, user_roles):
        response = ForbiddenResponse.endpoint(user_id=auth[0])
        raise HTTPException(**response.model_dump())

    authorized_actions = access_resolver.get_actions(user_roles)

    req: Optional[Request] = None
    if "request" in kwargs and isinstance(kwargs["request"], Request):
        req = kwargs["request"]
    else:
        for arg in args:
            if isinstance(arg, Request):
                req = arg
                break
    if req is not None:
        req.state.authorized_actions = authorized_actions


def authorize(action: Action) -> Callable:
    """Check authorization for an endpoint (async version).

    Create a decorator that enforces the specified authorization action on an endpoint.

    Parameters:
        action (Action): The action that the decorated endpoint must be
        authorized to perform.

    Returns:
        Callable: A decorator which, when applied to an endpoint function,
        performs the authorization check for the given action before invoking
        the function.
    """

    def decorator(func: Callable) -> Callable:
        """
        Wrap an endpoint function to perform an authorization check before invoking original one.

        Parameters:
            func (Callable): The function to wrap.

        Returns:
            Callable: A wrapper that performs authorization then calls `func`.
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            await _perform_authorization_check(action, args, kwargs)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
