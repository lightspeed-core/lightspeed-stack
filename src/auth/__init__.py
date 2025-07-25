"""This package contains authentication code and modules."""

import logging

from auth.interface import AuthInterface
from auth import noop, noop_with_token, k8s, jwk_token
from configuration import configuration
import constants


logger = logging.getLogger(__name__)


def get_auth_dependency(
    virtual_path: str = constants.DEFAULT_VIRTUAL_PATH,
) -> AuthInterface:
    """Select the configured authentication dependency interface."""
    module = configuration.authentication_configuration.module

    logger.debug(
        "Initializing authentication dependency: module='%s', virtual_path='%s'",
        module,
        virtual_path,
    )

    match module:
        case constants.AUTH_MOD_NOOP:
            return noop.NoopAuthDependency(virtual_path=virtual_path)
        case constants.AUTH_MOD_NOOP_WITH_TOKEN:
            return noop_with_token.NoopWithTokenAuthDependency(
                virtual_path=virtual_path
            )
        case constants.AUTH_MOD_K8S:
            return k8s.K8SAuthDependency(virtual_path=virtual_path)
        case constants.AUTH_MOD_JWK_TOKEN:
            return jwk_token.JwkTokenAuthDependency(
                configuration.authentication_configuration.jwk_configuration,
                virtual_path=virtual_path,
            )
        case _:
            err_msg = f"Unsupported authentication module '{module}'"
            logger.error(err_msg)
            raise ValueError(err_msg)
