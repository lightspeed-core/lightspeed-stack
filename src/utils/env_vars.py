"""Normalize environment references and resolve them using OGX semantics."""

import re
from typing import Any, Final

from ogx.core.stack import replace_env_vars

# Match ${VAR} and ${env.VAR}, optionally with :=default or :+value.
# Names use OGX's uppercase/digit/underscore grammar; operands end at the first }.
_ENV_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\$\{(?:env\.)?[A-Z0-9_]+(?::[=+][^}]*)?\}"
)


def canonicalize_reference(match: re.Match[str]) -> str:
    """Preserve OGX references and prefix short references with env.

    Parameters:
        match: A supported reference found by the normalizer's regex.

    Returns:
        The reference in canonical ${env.VAR} syntax, without resolving it.

    """
    # group(0) is the complete matched reference, including ${ and }.
    reference = match.group(0)
    if reference.startswith("${env."):
        return reference
    return reference.replace("${", "${env.", 1)


def normalize_env_references(config: Any) -> Any:
    """Convert supported ${VAR} references to ${env.VAR} without resolving them.

    Recursively visit dictionary values and list elements, rebuilding each
    container and normalizing its strings. Keys and existing OGX references are
    unchanged. Variable names and operators follow OGX's resolver grammar.

    Parameters:
        config: A configuration value, including nested containers and scalars.

    Returns:
        The configuration with supported short references canonicalized.

    """
    if isinstance(config, str):
        # sub calls the canonicalizer for each match, preserving surrounding text.
        # For ${HOST}:${PORT}, each reference gets its own canonical replacement.
        return _ENV_REFERENCE_PATTERN.sub(canonicalize_reference, config)
    if isinstance(config, dict):
        return {key: normalize_env_references(value) for key, value in config.items()}
    if isinstance(config, list):
        return [normalize_env_references(value) for value in config]
    return config


def resolve_env_references(config: Any) -> Any:
    """Normalize environment references, then delegate their resolution to OGX.

    Parameters:
        config: A configuration value, including nested containers and scalars.

    Returns:
        The recursively resolved configuration. OGX may convert substituted
        strings to numbers, booleans, or None; other scalar values pass through.

    """
    normalized_config = normalize_env_references(config)
    return replace_env_vars(normalized_config)
