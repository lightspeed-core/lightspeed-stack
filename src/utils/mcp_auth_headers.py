"""Utilities for resolving MCP server authorization headers."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_authorization_headers(
    authorization_headers: dict[str, str],
) -> dict[str, str]:
    """
    Resolve authorization headers by reading secret files or preserving special values.

    Parameters:
        authorization_headers: Map of header names to secret locations or special keywords.
            - If value is "kubernetes": live is unchanged. We substitute it during request.
            - If value is "client": live it unchanged. . We substitute it during request.
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
        try:
            if value == "kubernetes":
                # Special case: Keep kubernetes keyword for later substitution
                resolved[header_name] = "kubernetes"
                logger.debug(
                    "Header %s will use Kubernetes token (resolved at request time)",
                    header_name,
                )
            elif value == "client":
                # Special case: Keep client keyword for later substitution
                resolved[header_name] = "client"
                logger.debug(
                    "Header %s will use client-provided token (resolved at request time)",
                    header_name,
                )
            else:
                # Regular case: Read secret from file path
                secret_path = Path(value)
                if secret_path.exists() and secret_path.is_file():
                    with open(secret_path, "r", encoding="utf-8") as secret_file:
                        secret_value = secret_file.read().strip()
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
        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "Failed to resolve authorization header %s with value %s: %s",
                header_name,
                value,
                e,
            )

    return resolved
