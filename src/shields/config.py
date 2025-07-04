"""
Configuration support for redaction shields.

Allows loading patterns from configuration files.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _extract_patterns(source: Any) -> Optional[List[Dict[str, str]]]:
    """
    Extract redaction patterns from a given source object.

    Args:
        source: List of dicts or Pydantic models

    Returns:
        List of redaction pattern dictionaries or None
    """
    if not isinstance(source, list) or not source:
        return None

    if isinstance(source[0], dict):
        return source

    try:
        return [item.model_dump() for item in source]
    except ValueError as e:
        logger.warning("Failed to convert redaction patterns to dict: %s", e)
        return None


def load_redaction_patterns_from_config(config: Any) -> Optional[List[Dict[str, str]]]:
    """
    Load redaction patterns from application configuration.

    This checks both the root level and the optional `shields` field
    to support legacy and nested config structures.

    Args:
        config: Application configuration object

    Returns:
        List of redaction patterns as dicts or None if not configured
    """
    try:
        # Try direct root-level config
        if hasattr(config, "redaction_patterns"):
            patterns = _extract_patterns(config.redaction_patterns)
            if patterns:
                logger.info(
                    "Loaded %s redaction patterns from root config", len(patterns)
                )
                return patterns

        # Fallback to shields section
        if hasattr(config, "shields") and hasattr(config.shields, "redaction_patterns"):
            patterns = _extract_patterns(config.shields.redaction_patterns)
            if patterns:
                logger.info(
                    "Loaded %s redaction patterns from shields config", len(patterns)
                )
                return patterns

        logger.info("No redaction patterns found in configuration, using defaults")
        return None

    except ValueError as e:
        logger.error("Error loading redaction patterns from configuration: %s", e)
        return None


def create_shield_with_config(config: Any) -> Any:
    """
    Create a redaction shield using the loaded configuration patterns.

    Args:
        config: Application configuration object

    Returns:
        Configured RedactionShield instance
    """
    from .redaction_shield import (  # pylint: disable=import-outside-toplevel, disable=cyclic-import
        RedactionShield,
    )

    return RedactionShield(load_redaction_patterns_from_config(config))
