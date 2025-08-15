"""Authorization middleware and decorators."""

import logging
from functools import wraps, lru_cache
from typing import Any, Callable
import json

from fastapi import HTTPException, status

from authorization.engine import AuthorizationEngine
from authorization.models import Action
from configuration import configuration
import constants

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_authorization_engine() -> AuthorizationEngine | None:
    """Get authorization engine from configuration (cached)."""
    try:
        auth_config = configuration.authentication_configuration

        if auth_config.module != constants.AUTH_MOD_JWK_TOKEN:
            logger.info("Authorization disabled: not using JWK authentication")
            return None

        jwk_config = auth_config.jwk_configuration
        if not jwk_config.authorization_configuration:
            logger.info("Authorization disabled: no authorization config provided")
            return None

        auth_cfg = jwk_config.authorization_configuration
        engine = AuthorizationEngine(auth_cfg.role_rules, auth_cfg.access_rules)
        logger.info(
            "Authorization engine initialized with %d role rules and %d access rules",
            len(auth_cfg.role_rules),
            len(auth_cfg.access_rules),
        )
        return engine

    except (ValueError, KeyError, AttributeError) as e:
        logger.error("Failed to initialize authorization engine: %s", e)
        return None


def _perform_authorization_check(action: Action, kwargs: dict[str, Any]) -> None:
    """Perform authorization check - common logic for all decorators."""
    auth_engine = get_authorization_engine()

    # If no authorization configured, allow access
    if not auth_engine:
        return

    auth = None
    for key, value in kwargs.items():
        if key in ["auth", "_auth"] and isinstance(value, tuple) and len(value) >= 3:
            auth = value
            break

    if not auth:
        logger.error(
            "Authorization only allowed on endpoints that accept "
            "'auth: Any = Depends(get_auth_dependency())'"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    user_id, _, token = auth
    jwt_claims = json.loads(token)

    if not jwt_claims:
        logger.error("No JWT claims found in auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    user_roles = auth_engine.extract_roles_from_jwt(jwt_claims)

    if not auth_engine.check_access(user_roles, action):
        logger.warning(
            "Access denied for user %s with roles %s to action %s",
            user_id,
            user_roles,
            action,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for action: {action}",
        )

    logger.debug(
        "Access granted for user %s with roles %s to action %s",
        user_id,
        user_roles,
        action,
    )


def check_authorization(action: Action) -> Callable:
    """Decorator to check authorization for an endpoint (sync version)."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            _perform_authorization_check(action, kwargs)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def authorize(action: Action) -> Callable:
    """Universal authorization decorator that works with both sync and async functions."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            _perform_authorization_check(action, kwargs)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            _perform_authorization_check(action, kwargs)
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if func.__code__.co_flags & 0x80:  # Check if function is async
            return async_wrapper
        return sync_wrapper

    return decorator
