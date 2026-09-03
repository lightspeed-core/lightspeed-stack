"""Pyroscope CPU profiling initialization for Lightspeed Core Stack."""

import os

from log import get_logger

logger = get_logger(__name__)

PYROSCOPE_SERVER_ADDRESS_ENV_VAR = "PYROSCOPE_SERVER_ADDRESS"


def initialize_pyroscope() -> None:
    """Initialize Pyroscope continuous CPU profiling.

    Reads PYROSCOPE_SERVER_ADDRESS environment variable. If not set, profiling
    is skipped with zero overhead. When active, overhead is approximately 3-5%
    CPU. pyroscope-io must be installed (dev dependency group) for this to work.
    """
    server_address = os.environ.get(PYROSCOPE_SERVER_ADDRESS_ENV_VAR)
    if not server_address:
        logger.debug(
            "Pyroscope profiling disabled (%s not set)",
            PYROSCOPE_SERVER_ADDRESS_ENV_VAR,
        )
        return

    try:
        import pyroscope  # pyright: ignore[reportMissingImports]  # pylint: disable=import-outside-toplevel

        pyroscope.configure(
            application_name="lightspeed-stack",
            server_address=server_address,
        )
        logger.info("Pyroscope CPU profiling enabled")
    except ImportError:
        logger.warning(
            "pyroscope-io is not installed; install dev dependencies to enable CPU profiling"
        )
