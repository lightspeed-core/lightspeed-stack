"""Custom Presidio recognizer for email addresses."""

from typing import Optional

from presidio_analyzer import Pattern, PatternRecognizer


class EmailRecognizer(PatternRecognizer):
    """
    Recognize Email addresses using regex.

    This custom recognizer uses improved boundary detection to properly
    handle emails separated by special characters like /, -, etc.
    """

    # Improved email regex with negative lookahead/lookbehind for better boundary detection
    # Only @ and alphanumeric in boundaries - allows -, _, +, ., and other chars as separators
    # This means emails can be separated by: space, /, |, -, _, +, ;, :, comma, tab, newline, etc.
    EMAIL_REGEX = r"(?<![a-zA-Z0-9@])[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?![a-zA-Z0-9@])"

    PATTERNS = [Pattern("Email pattern", EMAIL_REGEX, 1)]

    CONTEXT = ["email", "mail", "contact"]

    def __init__(
        self,
        patterns: Optional[list[Pattern]] = None,
        context: Optional[list[str]] = None,
        supported_language: str = "en",
        supported_entity: str = "EMAIL_ADDRESS",
    ):
        """Initialize the email recognizer with its default pattern and context."""
        patterns = patterns if patterns else self.PATTERNS
        context = context if context else self.CONTEXT
        super().__init__(
            supported_entity=supported_entity,
            patterns=patterns,
            context=context,
            supported_language=supported_language,
        )
