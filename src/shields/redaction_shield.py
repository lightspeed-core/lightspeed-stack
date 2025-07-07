"""
Redaction shield for Llama Stack integration.

This implements the same functionality as the old road-core/service query_redactor.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from configuration import configuration
from .config import load_redaction_patterns_from_config

logger = logging.getLogger(__name__)


class RedactionShield:
    """Shield that redacts sensitive information using configurable patterns."""

    def __init__(self, patterns: Optional[List[Dict[str, str]]] = None):
        """
        Initialize the redaction shield.

        If no custom patterns are provided, attempts to load from config. Falls back to defaults.
        """
        if patterns is None:
            try:
                patterns = load_redaction_patterns_from_config(configuration)
            except ValueError as e:
                logger.warning("Could not load patterns from configuration: %s", e)
                patterns = None

        # Use the provided patterns, or fall back to default ones if none are available
        self.patterns = patterns or self._get_default_patterns()
        self.compiled_patterns = self._compile_patterns()
        logger.info("Initialized RedactionShield with %s patterns", len(self.patterns))

    def _get_default_patterns(self) -> List[Dict[str, str]]:
        """
        Fallback redaction patterns when none are configured.

        These cover common sensitive terms like passwords, secrets, tokens, etc.
        """
        return [
            {"pattern": r"\bfoo\b", "replacement": "deployment"},
            {"pattern": r"\bbar\b", "replacement": "openshift"},
            {"pattern": r"\bpassword\b", "replacement": "[REDACTED]"},
            {"pattern": r"\bsecret\b", "replacement": "[REDACTED]"},
            {"pattern": r"\bapi[_-]?key\b", "replacement": "[REDACTED]"},
            {"pattern": r"\btoken\b", "replacement": "[REDACTED]"},
        ]

    def _compile_patterns(self) -> List[Dict[str, Any]]:
        """Precompile regex patterns to improve performance during repeated redaction."""
        compiled = []
        for pattern_config in self.patterns:
            try:
                compiled.append(
                    {
                        "pattern": re.compile(pattern_config["pattern"], re.IGNORECASE),
                        "replacement": pattern_config["replacement"],
                        "original": pattern_config["pattern"],
                    }
                )
                logger.debug(
                    "Compiled pattern: %s -> %s",
                    pattern_config["pattern"],
                    pattern_config["replacement"],
                )
            except (re.error, KeyError) as e:
                logger.error(
                    "Invalid pattern configuration: %s, error: %s", pattern_config, e
                )
        return compiled

    def redact_text(
        self, text: Optional[str], conversation_id: str = "unknown"
    ) -> Optional[str]:
        """
        Redacts sensitive terms in a given text using configured regex patterns.

        Args:
            text: The text content to scan and redact.
            conversation_id: For logging/tracing purposes.
        """
        if text is None:
            return None
        if not text:
            return text

        redacted_text = text
        redactions_made = 0

        for pattern_info in self.compiled_patterns:
            try:
                pattern = pattern_info["pattern"]
                replacement = pattern_info["replacement"]
                original = pattern_info["original"]

                matches = pattern.findall(redacted_text)
                if matches:
                    redacted_text = pattern.sub(replacement, redacted_text)
                    redactions_made += len(matches)
                    logger.debug(
                        "Applied pattern '%s' to conversation %s: %s matches",
                        original,
                        conversation_id,
                        len(matches),
                    )
            except ValueError as e:
                logger.error(
                    "Error applying pattern '%s' to conversation %s: %s",
                    pattern_info["original"],
                    conversation_id,
                    e,
                )

        if redactions_made:
            logger.info(
                "Applied %s redactions for conversation %s",
                redactions_made,
                conversation_id,
            )

        return redacted_text

    def run(self, messages: List[Any], conversation_id: str = "unknown") -> List[Any]:
        """
        Run redaction on a list of messages (e.g., user messages sent to LLM).

        Will not mutate the original message objects.
        """
        try:
            redacted_messages = []

            for message in messages:
                # Copy message to avoid mutating input
                redacted_message = self._copy_message(message)

                # Apply redaction on content
                if hasattr(message, "content") and message.content:
                    redacted_message.content = self.redact_text(
                        message.content, conversation_id
                    )

                redacted_messages.append(redacted_message)

            return redacted_messages
        except ValueError as e:
            logger.error(
                "Error in redaction shield for conversation %s: %s", conversation_id, e
            )
            return messages  # Fallback: return unredacted messages

    def _copy_message(self, message: Any) -> Any:
        """
        Safely clone a message object using available copy methods.

        This supports both Pydantic and dataclass-style models.
        """
        if hasattr(message, "model_copy"):
            return message.model_copy()
        if hasattr(message, "copy"):
            return message.copy()
        return message  # fallback: shallow copy


# Singleton instance for the redaction shield to avoid repeated instantiation
SHIELD_INSTANCE = None


def get_redaction_shield(
    patterns: Optional[List[Dict[str, str]]] = None,
) -> RedactionShield:
    """
    Return a shared singleton instance of the RedactionShield.

    Unless custom patterns are explicitly passed.
    """
    global SHIELD_INSTANCE  # pylint: disable=global-statement
    if SHIELD_INSTANCE is None or patterns is not None:
        SHIELD_INSTANCE = RedactionShield(patterns)
    return SHIELD_INSTANCE


def redact_query(conversation_id: str, query: Optional[str]) -> Optional[str]:
    """
    Redacts sensitive terms in a query string using the global redaction shield.

    Maintains compatibility with legacy road-core signature.
    """
    shield = get_redaction_shield()
    return shield.redact_text(query, conversation_id)


def redact_attachments(conversation_id: str, attachments: List[Any]) -> List[Any]:
    """
    Redacts content inside attachment objects.

    Falls back to unmodified attachments if redaction fails.
    """
    try:
        shield = get_redaction_shield()
        redacted = []

        for attachment in attachments:
            redacted_content = shield.redact_text(
                getattr(attachment, "content", None), conversation_id
            )
            redacted_attachment = type(attachment)(
                attachment_type=attachment.attachment_type,
                content_type=attachment.content_type,
                content=redacted_content,
            )
            redacted.append(redacted_attachment)

        return redacted
    except Exception as redactor_error:  # pylint: disable=broad-exception-caught
        logger.error(
            "Error while redacting attachments for conversation %s: %s",
            conversation_id,
            redactor_error,
        )
        return attachments
