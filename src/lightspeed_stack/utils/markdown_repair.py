"""Utilities for repairing truncated markdown content.

Used when a streaming response is interrupted mid-content to close
any open markdown constructs (code fences, HTML block tags, HTML
comments, raw-content tags) that would otherwise break rendering.
"""

import re
from typing import Final, Optional

BLOCK_HTML_TAGS: Final[frozenset[str]] = frozenset(
    {
        "div",
        "table",
        "tr",
        "td",
        "th",
        "thead",
        "tbody",
        "tfoot",
        "caption",
        "details",
        "summary",
        "pre",
    }
)

RAW_HTML_TAGS: Final[frozenset[str]] = frozenset(
    {
        "script",
        "style",
    }
)

_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"^(\s{0,3})((`{3,})|(~{3,}))")
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<(/?)(\w+)([^>]*?)(/?)>")

_COMMENT_OPEN: Final[str] = "<!--"
_COMMENT_CLOSE: Final[str] = "-->"


def _process_html_tags(line: str, html_stack: list[str]) -> Optional[str]:
    """Update *html_stack* with block-level HTML open/close tags found in *line*.

    When a raw-content tag (``<script>``, ``<style>``) is encountered,
    block-tag processing stops.  If the matching close tag appears on the
    same line, processing resumes after it.  Otherwise the raw tag name
    is returned so the caller can enter raw-tag mode.

    Parameters:
        line: A single line of text to scan for HTML tags.
        html_stack: Mutable stack tracking open block-level tags.

    Returns:
        The name of a raw tag that was opened and not closed on this
        line, or ``None`` if no raw-content zone was entered.
    """
    in_raw: Optional[str] = None

    for tag_match in _TAG_RE.finditer(line):
        is_closing = tag_match.group(1) == "/"
        tag_name = tag_match.group(2).lower()
        is_self_closing = tag_match.group(4) == "/"

        if in_raw:
            if is_closing and tag_name == in_raw:
                in_raw = None
            continue

        if is_self_closing:
            continue

        if tag_name in RAW_HTML_TAGS:
            if not is_closing:
                in_raw = tag_name
            continue

        if tag_name not in BLOCK_HTML_TAGS:
            continue

        if is_closing:
            if html_stack and html_stack[-1] == tag_name:
                html_stack.pop()
        else:
            html_stack.append(tag_name)

    return in_raw


def _find_raw_close(line: str, raw_tag: str) -> Optional[int]:
    """Find the closing tag for a raw-content element in *line*.

    Parameters:
        line: A single line of text to scan.
        raw_tag: The raw tag name to look for (e.g. ``"script"``).

    Returns:
        The character position immediately after the closing tag,
        or ``None`` if no close tag was found.
    """
    for tag_match in _TAG_RE.finditer(line):
        if tag_match.group(1) == "/" and tag_match.group(2).lower() == raw_tag:
            return tag_match.end()
    return None


def _raw_tag_open_at(line: str, position: int) -> bool:
    """Return whether an unclosed raw-tag zone spans *position* in *line*.

    Scans all HTML tags before *position*, tracking raw-tag open/close
    state.  Returns ``True`` only if a raw tag is still open at
    *position* (i.e. it opened but did not close before *position*).

    Parameters:
        line: A single line of text to scan.
        position: Character index to check against.

    Returns:
        True if a raw-tag zone is open at *position*.
    """
    open_raw: Optional[str] = None
    for tag_match in _TAG_RE.finditer(line):
        if tag_match.start() >= position:
            break
        tag_name = tag_match.group(2).lower()
        if tag_name not in RAW_HTML_TAGS:
            continue
        if tag_match.group(1) == "/":
            if open_raw == tag_name:
                open_raw = None
        elif tag_match.group(4) != "/":
            open_raw = tag_name
    return open_raw is not None


def _strip_comments_with_zone_priority(line: str, in_comment: bool) -> tuple[str, bool]:
    """Strip comments from *line*, respecting zone-marker priority.

    Processes comments incrementally.  After each closed comment is
    consumed, the remaining visible suffix is re-evaluated: if a fence
    marker or raw-tag opener appears before the next ``<!--``, that
    zone takes priority and comment stripping stops.

    Parameters:
        line: A single line of text to process.
        in_comment: Whether we are inside an HTML comment from a
            previous line.

    Returns:
        A tuple of (processed_line, updated_in_comment).
    """
    result: list[str] = []
    remaining = line

    while remaining:
        if in_comment:
            end = remaining.find(_COMMENT_CLOSE)
            if end == -1:
                return "".join(result), True
            remaining = remaining[end + len(_COMMENT_CLOSE) :]
            in_comment = False
            continue

        if _FENCE_RE.match(remaining):
            result.append(remaining)
            return "".join(result), False

        comment_pos = remaining.find(_COMMENT_OPEN)
        if comment_pos == -1:
            result.append(remaining)
            return "".join(result), False

        if _raw_tag_open_at(remaining, comment_pos):
            result.append(remaining)
            return "".join(result), False

        result.append(remaining[:comment_pos])
        remaining = remaining[comment_pos + len(_COMMENT_OPEN) :]
        in_comment = True

    return "".join(result), in_comment


def _process_fence_match(
    fence_match: re.Match[str],
    line: str,
    in_code_fence: bool,
    fence_char: str,
    fence_len: int,
) -> tuple[bool, str, int]:
    """Update fence state based on a fence regex match.

    Parameters:
        fence_match: A successful ``_FENCE_RE`` match object.
        line: The full line containing the match.
        in_code_fence: Whether we are currently inside a code fence.
        fence_char: The character used for the current fence.
        fence_len: The length of the current fence marker.

    Returns:
        Updated ``(in_code_fence, fence_char, fence_len)`` tuple.
    """
    group_3 = fence_match.group(3)
    matched_group = group_3 or fence_match.group(4)
    char = "`" if group_3 else "~"
    if not in_code_fence:
        return True, char, len(matched_group)
    if (
        char == fence_char
        and len(matched_group) >= fence_len
        and line[fence_match.end() :].strip(" \t") == ""
    ):
        return False, "", 0
    return in_code_fence, fence_char, fence_len


def close_open_markdown(text: str) -> str:
    """Return a suffix that closes any open markdown constructs in *text*.

    Scans for unclosed fenced code blocks, unclosed HTML block-level
    tags, unclosed HTML comments, and unclosed raw-content tags
    (``<script>``, ``<style>``).  Returns only the closing characters
    (callers append the result).  Returns an empty string when nothing
    needs closing.

    Parameters:
        text: Partial markdown content that may contain open constructs.

    Returns:
        A suffix string to append that closes open constructs.
    """
    if not text or not text.strip():
        return ""

    lines = text.split("\n")
    in_code_fence = False
    fence_char = ""
    fence_len = 0
    in_comment = False
    in_raw_tag = ""
    html_stack: list[str] = []

    for line in lines:
        if in_raw_tag:
            end_pos = _find_raw_close(line, in_raw_tag)
            if end_pos is None:
                continue
            in_raw_tag = ""
            line = line[end_pos:]

        if not in_code_fence:
            line, in_comment = _strip_comments_with_zone_priority(line, in_comment)

        fence_match = _FENCE_RE.match(line)

        if not fence_match:
            if not in_code_fence:
                raw_tag = _process_html_tags(line, html_stack)
                if raw_tag:
                    in_raw_tag = raw_tag
                    in_comment = False
            continue

        in_code_fence, fence_char, fence_len = _process_fence_match(
            fence_match, line, in_code_fence, fence_char, fence_len
        )

    suffix_parts: list[str] = []

    if in_comment:
        suffix_parts.append(f"\n{_COMMENT_CLOSE}")
    elif in_code_fence:
        suffix_parts.append(f"\n{fence_char * fence_len}")
    elif in_raw_tag:
        suffix_parts.append(f"\n</{in_raw_tag}>")

    for tag in reversed(html_stack):
        suffix_parts.append(f"\n</{tag}>")

    return "".join(suffix_parts)
