"""Authorization middleware and decorators."""

import logging
from functools import lru_cache, wraps
from typing import Any, Callable, Tuple

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
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_authorization_resolvers() -> Tuple[RolesResolver, AccessResolver]:
    """Get authorization resolvers from configuration (cached)."""
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

        case _:
            response = InternalServerErrorResponse.generic()
            raise HTTPException(**response.model_dump())


async def _perform_authorization_check(
    action: Action, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Perform authorization check - common logic for all decorators."""
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

    req: Request | None = None
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
    """Check authorization for an endpoint (async version)."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            await _perform_authorization_check(action, args, kwargs)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
