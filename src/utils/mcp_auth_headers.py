"""Utilities for resolving MCP server authorization headers."""

from pathlib import Path

import constants
from log import get_logger

logger = get_logger(__name__)


def resolve_authorization_headers(
    authorization_headers: dict[str, str],
) -> dict[str, str]:
    """
    Resolve authorization headers by reading secret files or preserving special values.

    Parameters:
        authorization_headers: Map of header names to secret locations or special keywords.
            - If value is "kubernetes": leave is unchanged. We substitute it during request.
            - If value is "client": leave it unchanged. . We substitute it during request.
            - Otherwise: Treat as file path and read the secret from that file

    Returns:
        dict[str, str]: Map of header names to resolved header values or special keywords

    Examples:
        >>> # With file paths
        >>> resolve_authorization_headers({"Authorization": "/var/secrets/token"})
        {"Authorization": "secret-value-from-file"}

        >>> # With kubernetes special case (kept as-is)
        >>> resolve_authorization_headers({"Authorization": "kubernetes"})
        {"Authorization": "kubernetes"}

        >>> # With client special case (kept as-is)
        >>> resolve_authorization_headers({"Authorization": "client"})
        {"Authorization": "client"}
    """
    resolved: dict[str, str] = {}

    for header_name, value in authorization_headers.items():
        value = value.strip()
        try:
            if value == constants.MCP_AUTH_KUBERNETES:
                # Special case: Keep kubernetes keyword for later substitution
                resolved[header_name] = constants.MCP_AUTH_KUBERNETES
                logger.debug(
                    "Header %s will use Kubernetes token (resolved at request time)",
                    header_name,
                )
            elif value == constants.MCP_AUTH_CLIENT:
                # Special case: Keep client keyword for later substitution
                resolved[header_name] = constants.MCP_AUTH_CLIENT
                logger.debug(
                    "Header %s will use client-provided token (resolved at request time)",
                    header_name,
                )
            else:
                # Regular case: Read secret from file path
                secret_path = Path(value).expanduser()
                if secret_path.exists() and secret_path.is_file():
                    secret_value = secret_path.read_text(encoding="utf-8").strip()
                    if not secret_value:
                        logger.warning(
                            "Secret file %s for header %s is empty",
                            secret_path,
                            header_name,
                        )
                    else:
                        resolved[header_name] = secret_value
                        logger.debug(
                            "Resolved header %s from secret file %s",
                            header_name,
                            secret_path,
                        )
                else:
                    logger.warning(
                        "Secret file not found or not a file: %s for header %s",
                        secret_path,
                        header_name,
                    )
        except Exception:  # pylint: disable=broad-except
            # Don't log value: it might be a literal token.
            logger.exception(
                "Failed to resolve authorization header %s (value treated as path)",
                header_name,
            )

    return resolved
