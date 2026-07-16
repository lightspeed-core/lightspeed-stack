"""Sentry error tracking initialization and configuration."""

import os

import sentry_sdk  # pyright: ignore[reportMissingImports]
from sentry_sdk.integrations.fastapi import (  # pyright: ignore[reportMissingImports]
    FastApiIntegration,
)

import version
from constants import (
    SENTRY_CA_CERTS_ENV_VAR,
    SENTRY_DEFAULT_ENVIRONMENT,
    SENTRY_DEFAULT_TRACES_SAMPLE_RATE,
    SENTRY_DSN_ENV_VAR,
    SENTRY_ENVIRONMENT_ENV_VAR,
    SENTRY_EXCLUDED_ROUTES,
)
from log import get_logger

logger = get_logger(__name__)


def sentry_traces_sampler(tracing_context: dict) -> float:
    """
    Determine the trace sample rate for a given request.

    Excludes health check, metrics, and root routes from trace sampling to
    reduce noise. All other routes use the default sample rate.

    Parameters:
    ----------
        tracing_context (dict): The Sentry tracing context containing ASGI
            scope information, including the request path.

    Returns:
    -------
        float: 0.0 for excluded routes (no sampling), or
            SENTRY_DEFAULT_TRACES_SAMPLE_RATE for all other routes.
    """
    asgi_scope = tracing_context.get("asgi_scope", {})
    path = asgi_scope.get("path") if isinstance(asgi_scope, dict) else None

    if path is not None:
        if path == "/":
            return 0.0
        if any(
            route != "/" and path.endswith(route) for route in SENTRY_EXCLUDED_ROUTES
        ):
            return 0.0

    return SENTRY_DEFAULT_TRACES_SAMPLE_RATE


def initialize_sentry() -> None:
    """
    Initialize Sentry error tracking if a DSN is configured.

    Reads the SENTRY_DSN environment variable. If not set or empty, logs an
    informational message and returns without initializing Sentry. When a DSN
    is present, initializes the Sentry SDK with custom trace sampling, FastAPI
    integration, and optional CA certificate configuration.

    When SENTRY_CA_CERTS is set to a file path, that certificate bundle is
    passed to the SDK for Sentry instances using private or internal CAs.

    The DSN value is never logged to prevent accidental credential exposure.

    Parameters:
    ----------
        None

    Returns:
    -------
        None
    """
    dsn = os.environ.get(SENTRY_DSN_ENV_VAR)

    if not dsn:
        logger.info("Sentry DSN not configured, skipping initialization")
        return

    ca_certs = None
    ca_certs_path = os.environ.get(SENTRY_CA_CERTS_ENV_VAR)
    if ca_certs_path:
        if os.path.exists(ca_certs_path):
            ca_certs = ca_certs_path
        else:
            logger.warning(
                "CA cert file specified by %s not found at %s; "
                "proceeding without custom CA certs",
                SENTRY_CA_CERTS_ENV_VAR,
                ca_certs_path,
            )

    environment = os.environ.get(SENTRY_ENVIRONMENT_ENV_VAR, SENTRY_DEFAULT_ENVIRONMENT)

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sampler=sentry_traces_sampler,
            send_default_pii=False,
            ca_certs=ca_certs,
            integrations=[FastApiIntegration(http_methods_to_capture=("POST",))],
            release=f"lightspeed-stack@{version.__version__}",
        )
        logger.info("Sentry initialized")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Failed to initialize Sentry, continuing without error tracking"
        )
