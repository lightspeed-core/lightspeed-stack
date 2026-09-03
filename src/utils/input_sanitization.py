"""Input sanitization to detect and block obfuscated prompt injection attempts.

Addresses pentest finding OFFSEC-307 (LCORE-2749, CVSS 9.6 Critical):
attackers can bypass content filters by encoding malicious instructions
in unusual Unicode blocks (Elder Futhark, Mathematical Alphanumeric
Symbols) or binary/hex representation.

This module provides:
- Unicode NFC normalization
- Detection of obfuscation techniques (unusual Unicode blocks, binary
  encoding, hex encoding, XML tag injection patterns)

All checks are CPU-only stdlib operations with negligible latency (< 1ms).
"""

import re
import unicodedata
from typing import Optional

from log import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Unicode block ranges considered obfuscation vectors
# ---------------------------------------------------------------------------
# Each tuple is (start, end, label) inclusive.
_SUSPICIOUS_UNICODE_RANGES: list[tuple[int, int, str]] = [
    # Runic block — includes Elder Futhark (used in OFFSEC-307)
    (0x16A0, 0x16FF, "Runic"),
    # Mathematical Alphanumeric Symbols — bold/italic/script variants
    # of Latin letters that visually resemble ASCII but bypass filters
    (0x1D400, 0x1D7FF, "Mathematical Alphanumeric Symbols"),
    # Enclosed Alphanumerics (circled digits/letters)
    (0x2460, 0x24FF, "Enclosed Alphanumerics"),
    # Fullwidth Latin letters only (A-Z, a-z) — visually similar to ASCII.
    # Excludes fullwidth punctuation (U+FF01-FF20, U+FF3B-FF40, U+FF5B-FF5E)
    # which may appear in legitimate CJK-context text.
    (0xFF21, 0xFF3A, "Fullwidth Latin uppercase"),
    (0xFF41, 0xFF5A, "Fullwidth Latin lowercase"),
]

# ---------------------------------------------------------------------------
# Regex patterns for binary/hex encoding detection
# ---------------------------------------------------------------------------
# Binary: 8+ groups of 8 binary digits (space-separated bytes)
_BINARY_PATTERN = re.compile(r"(?:[01]{8}[\s]+){3,}[01]{8}")

# Hex escape sequences: \x41\x42 or 0x41 0x42 patterns
_HEX_ESCAPE_PATTERN = re.compile(r"(?:\\x[0-9a-fA-F]{2}){4,}")
_HEX_PREFIX_PATTERN = re.compile(r"(?:0x[0-9a-fA-F]{2}[\s,]+){4,}")

# ---------------------------------------------------------------------------
# XML/markup injection patterns (per OffSec recommendation)
# ---------------------------------------------------------------------------
_XML_INJECTION_PATTERN = re.compile(
    r"<\s*/?(?:ac:|invoke|function_call|tool_call|system|assistant)[^>]*>",
    re.IGNORECASE,
)


def normalize_unicode(text: str) -> str:
    """Normalize text to Unicode NFC form.

    NFC normalization ensures that composed and decomposed Unicode
    representations are treated identically. For example, 'é' as a
    single codepoint (U+00E9) and 'e' + combining accent (U+0065
    U+0301) are normalized to the same form.

    Parameters:
        text: The input text to normalize.

    Returns:
        NFC-normalized text.
    """
    return unicodedata.normalize("NFC", text)


def _check_suspicious_unicode(text: str) -> Optional[str]:
    """Check for characters from Unicode blocks used for obfuscation.

    Parameters:
        text: The input text to check.

    Returns:
        Description of the detected block, or None if clean.
    """
    for char in text:
        codepoint = ord(char)
        for start, end, label in _SUSPICIOUS_UNICODE_RANGES:
            if start <= codepoint <= end:
                return (
                    f"Input contains characters from the {label} Unicode "
                    f"block (U+{codepoint:04X}), which may be used to "
                    f"obfuscate instructions."
                )
    return None


def _check_binary_encoding(text: str) -> Optional[str]:
    """Check for binary-encoded content (sequences of 0s and 1s).

    Parameters:
        text: The input text to check.

    Returns:
        Description if binary encoding is detected, or None if clean.
    """
    if _BINARY_PATTERN.search(text):
        return "Input appears to contain binary-encoded content."
    return None


def _check_hex_encoding(text: str) -> Optional[str]:
    """Check for hex-encoded content (escape sequences or hex prefixes).

    Parameters:
        text: The input text to check.

    Returns:
        Description if hex encoding is detected, or None if clean.
    """
    if _HEX_ESCAPE_PATTERN.search(text):
        return "Input appears to contain hex-encoded escape sequences."
    if _HEX_PREFIX_PATTERN.search(text):
        return "Input appears to contain hex-encoded content."
    return None


def _check_xml_injection(text: str) -> Optional[str]:
    """Check for XML/markup tag patterns used for tool-call injection.

    Parameters:
        text: The input text to check.

    Returns:
        Description if suspicious XML tags are detected, or None if clean.
    """
    if _XML_INJECTION_PATTERN.search(text):
        return "Input contains suspicious XML/markup injection tags."
    return None


def detect_obfuscation(text: str) -> Optional[str]:
    """Check input text for obfuscation techniques.

    Runs all detection checks and returns the first match.

    Parameters:
        text: The input text to check.

    Returns:
        Description of detected obfuscation, or None if the input is clean.
    """
    checks = [
        _check_suspicious_unicode,
        _check_binary_encoding,
        _check_hex_encoding,
        _check_xml_injection,
    ]
    for check in checks:
        result = check(text)
        if result is not None:
            return result
    return None


def sanitize_input(text: str) -> tuple[str, Optional[str]]:
    """Normalize and check input text for obfuscation.

    First normalizes the text to Unicode NFC form, then runs
    obfuscation detection checks.

    Parameters:
        text: The raw user input text.

    Returns:
        Tuple of (normalized_text, rejection_reason).
        If rejection_reason is None, the input is clean and
        normalized_text should be used for further processing.
        If rejection_reason is not None, the input should be
        rejected with the given reason.
    """
    normalized = normalize_unicode(text)
    rejection_reason = detect_obfuscation(normalized)

    if rejection_reason:
        logger.warning(
            "Input rejected by sanitization: %s",
            rejection_reason,
        )

    return normalized, rejection_reason
