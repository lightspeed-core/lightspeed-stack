"""This package contains authentication code and modules."""

import logging
import os

import constants
from authentication import (
    jwk_token,
    k8s,
    noop,
    noop_with_token,
    rh_identity,
    api_key_token,
)
from authentication.interface import AuthInterface
from configuration import LogicError, configuration

logger = logging.getLogger(__name__)


def get_auth_dependency(
    virtual_path: str = constants.DEFAULT_VIRTUAL_PATH,
) -> AuthInterface:
    """Select the configured authentication dependency interface."""
    try:
        module = configuration.authentication_configuration.module
    except LogicError:
        # Only load once if not already loaded
        config_path = os.getenv(
            "LIGHTSPEED_STACK_CONFIG_PATH",
            "tests/configuration/lightspeed-stack.yaml",
        )
        configuration.load_configuration(config_path)
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
        case constants.AUTH_MOD_RH_IDENTITY:
            rh_identity_config = (
                configuration.authentication_configuration.rh_identity_configuration
            )
            return rh_identity.RHIdentityAuthDependency(
                required_entitlements=rh_identity_config.required_entitlements,
                virtual_path=virtual_path,
            )
        case constants.AUTH_MOD_APIKEY_TOKEN:
            return api_key_token.APIKeyTokenAuthDependency(
                config=configuration.authentication_configuration.api_key_configuration,
                virtual_path=virtual_path,
            )
        case _:
            err_msg = f"Unsupported authentication module '{module}'"
            logger.error(err_msg)
            raise ValueError(err_msg)
