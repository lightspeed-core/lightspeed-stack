"""Unit tests for markdown repair utilities."""

from lightspeed_stack.utils.markdown_repair import close_open_markdown


class TestCloseOpenMarkdownCodeFences:
    """Tests for closing unclosed code fences."""

    def test_unclosed_backtick_fence(self) -> None:
        """Unclosed triple-backtick fence gets closed."""
        text = "Some text\n```\ncode here"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_unclosed_tilde_fence(self) -> None:
        """Unclosed tilde fence gets closed with tildes."""
        text = "Some text\n~~~\ncode here"
        result = close_open_markdown(text)
        assert result == "\n~~~"

    def test_unclosed_fence_with_language(self) -> None:
        """Unclosed fence with language specifier gets closed."""
        text = "Some text\n```python\ndef foo():\n    pass"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_closed_fence_no_repair(self) -> None:
        """Properly closed fence needs no repair."""
        text = "Some text\n```\ncode\n```\nmore text"
        result = close_open_markdown(text)
        assert result == ""

    def test_multiple_fences_last_unclosed(self) -> None:
        """Multiple fences where only the last is unclosed."""
        text = "```\nfirst\n```\n\n```\nsecond block"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_backticks_mid_line_not_fence(self) -> None:
        """Triple backticks not at line start are not fences."""
        text = "Use ```code``` for inline code"
        result = close_open_markdown(text)
        assert result == ""

    def test_fence_no_trailing_newline(self) -> None:
        """Unclosed fence at end of text without trailing newline."""
        text = "```\ncode"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_fence_with_text_after_backticks(self) -> None:
        """Backticks at line start followed by text is a fence with info string."""
        text = "```this is my sentence"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_shorter_fence_inside_longer_fence_not_closer(self) -> None:
        """A 3-backtick line inside a 4-backtick fence is content, not a closer."""
        text = "````python\ndef foo():\n```\n    pass"
        result = close_open_markdown(text)
        assert result == "\n````"

    def test_fence_with_trailing_text_not_closer(self) -> None:
        """A fence marker with trailing non-whitespace inside a fence is content."""
        text = "```python\nprint('x')\n```not a closer"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_fence_with_trailing_whitespace_is_closer(self) -> None:
        """A fence marker with only trailing whitespace is a valid closer."""
        text = "```python\nprint('x')\n```   "
        result = close_open_markdown(text)
        assert result == ""


class TestCloseOpenMarkdownHtmlTags:
    """Tests for closing unclosed HTML block tags."""

    def test_unclosed_div(self) -> None:
        """Single unclosed div tag gets closed."""
        text = "<div>\nsome content"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_unclosed_table(self) -> None:
        """Single unclosed table tag gets closed."""
        text = "<table>\n<tr><td>cell</td></tr>"
        result = close_open_markdown(text)
        assert result == "\n</table>"

    def test_unclosed_pre(self) -> None:
        """Single unclosed pre tag gets closed."""
        text = "<pre>\nformatted text"
        result = close_open_markdown(text)
        assert result == "\n</pre>"

    def test_multiple_unclosed_tags_reversed(self) -> None:
        """Multiple unclosed tags are closed in reverse order."""
        text = "<div>\n<table>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</table>\n</div>"

    def test_nested_inner_closed(self) -> None:
        """Nested tags where inner is closed but outer is not."""
        text = "<div>\n<table>\ncontent\n</table>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_properly_closed_tags_no_repair(self) -> None:
        """Properly closed tags need no repair."""
        text = "<div>\ncontent\n</div>"
        result = close_open_markdown(text)
        assert result == ""

    def test_self_closing_tag_no_repair(self) -> None:
        """Self-closing tags do not generate closing tags."""
        text = "text with <br/> and <img src='x' />"
        result = close_open_markdown(text)
        assert result == ""

    def test_partial_html_tag_ignored(self) -> None:
        """Incomplete HTML tag (no closing >) is ignored."""
        text = "text with <div"
        result = close_open_markdown(text)
        assert result == ""

    def test_inline_tags_ignored(self) -> None:
        """Inline tags like span, em, strong are not repaired."""
        text = "<span>some <em>text"
        result = close_open_markdown(text)
        assert result == ""

    def test_unclosed_tfoot(self) -> None:
        """Unclosed tfoot inside table gets closed."""
        text = "<table>\n<tfoot>\n<tr><td>total</td></tr>"
        result = close_open_markdown(text)
        assert result == "\n</tfoot>\n</table>"

    def test_unclosed_caption(self) -> None:
        """Unclosed caption inside table gets closed."""
        text = "<table>\n<caption>Title"
        result = close_open_markdown(text)
        assert result == "\n</caption>\n</table>"


class TestCloseOpenMarkdownHtmlComments:
    """Tests for core HTML comment handling."""

    def test_tags_inside_single_line_comment_ignored(self) -> None:
        """Tags inside a closed single-line comment are not tracked."""
        text = "<!-- <table> -->\n<div>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_tags_inside_multi_line_comment_ignored(self) -> None:
        """Tags inside a multi-line comment are not tracked."""
        text = "<!--\n<table>\n-->\n<div>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_unclosed_comment_gets_closed(self) -> None:
        """Unclosed HTML comment gets closed with -->."""
        text = "<!-- partial content"
        result = close_open_markdown(text)
        assert result == "\n-->"

    def test_comment_inside_code_fence_is_literal(self) -> None:
        """Comment markers inside a code fence are literal text."""
        text = "```\n<!-- <div>\n```"
        result = close_open_markdown(text)
        assert result == ""

    def test_open_div_then_open_comment(self) -> None:
        """Open div followed by unclosed comment closes both."""
        text = "<div>\ncontent\n<!-- partial"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"

    def test_multiple_comments_on_one_line(self) -> None:
        """Multiple comments on one line with a tag between them."""
        text = "<!-- a --> <div> <!-- b --> content"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_comment_containing_fence_marker(self) -> None:
        """Fence marker inside a comment is not a real fence."""
        text = "<!-- ``` -->\nreal text"
        result = close_open_markdown(text)
        assert result == ""

    def test_unclosed_comment_with_prior_open_tag(self) -> None:
        """Unclosed comment after an open tag closes both."""
        text = "<div>\n<!-- <table>"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"


class TestCloseOpenMarkdownCommentBoundaryEdgeCases:
    """Tests for HTML comment boundary edge cases."""

    def test_empty_comment(self) -> None:
        """Empty comment is properly recognized and ignored."""
        text = "<!---->\n<div>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_comment_with_only_whitespace(self) -> None:
        """Comment containing only whitespace is properly closed."""
        text = "<!--   -->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_comment_opener_at_end_of_text(self) -> None:
        """Comment opener at the very end of text gets closed."""
        text = "<div>\ntext<!--"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"

    def test_line_is_only_comment_opener(self) -> None:
        """Line that is only <!-- opens a comment."""
        text = "<div>\n<!--"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"

    def test_line_is_only_comment_closer(self) -> None:
        """Bare --> on its own line closes a multi-line comment."""
        text = "<!--\n<table>\n-->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_stray_close_when_not_in_comment(self) -> None:
        """Stray --> when not in a comment is ignored as literal text."""
        text = "-->\n<div>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_extra_dashes_on_close(self) -> None:
        """---> closes a comment because it contains -->."""
        text = "<!-- comment --->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_space_before_close_angle_not_a_close(self) -> None:
        """-- > with space is not a comment close."""
        text = "<!-- text -- > more"
        result = close_open_markdown(text)
        assert result == "\n-->"


class TestCloseOpenMarkdownCommentCrossConstruct:
    """Tests for comments interacting with other constructs."""

    def test_adjacent_comments_no_space(self) -> None:
        """Two adjacent comments with no space between them."""
        text = "<!-- a --><!-- b -->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_three_comments_with_tags_between(self) -> None:
        """Tags between comments on one line are processed normally."""
        text = "<!-- x --> <div> <!-- y --> </div> <!-- z -->"
        result = close_open_markdown(text)
        assert result == ""

    def test_comment_opens_mid_line_rest_eaten(self) -> None:
        """Comment opening mid-line suppresses tags after it."""
        text = "<div> <!-- unclosed <table>"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"

    def test_fence_marker_inside_unclosed_multi_line_comment(self) -> None:
        """Fence marker inside an unclosed multi-line comment is ignored."""
        text = "<div>\n<!-- comment\n```python"
        result = close_open_markdown(text)
        assert result == "\n-->\n</div>"

    def test_tag_split_across_comment_boundary(self) -> None:
        """Partial tag inside comment is harmless."""
        text = "<!-- <di\nv> -->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_nested_comment_like_construct(self) -> None:
        """First --> closes comment; second --> is literal text."""
        text = "<!-- <!-- inner --> outer -->"
        result = close_open_markdown(text)
        assert result == ""

    def test_comment_between_two_tags_same_line(self) -> None:
        """Tags on both sides of a comment are tracked."""
        text = "<div><!-- comment --><table>"
        result = close_open_markdown(text)
        assert result == "\n</table>\n</div>"

    def test_empty_lines_inside_multi_line_comment(self) -> None:
        """Empty lines inside a multi-line comment don't break state."""
        text = "<!--\n\n\n-->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_fence_opens_before_comment_on_same_line(self) -> None:
        """Fence at line start takes priority over <!-- later on the line."""
        text = "```<!-- partial\ncode"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_comment_close_then_fence_on_next_line(self) -> None:
        """Comment closes on one line, fence opens on the next."""
        text = "<!-- comment -->\n```\ncode"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_fence_close_then_comment_on_next_line(self) -> None:
        """Fence closes on one line, comment opens on the next."""
        text = "```\ncode\n```\n<!-- partial"
        result = close_open_markdown(text)
        assert result == "\n-->"

    def test_comment_close_reveals_fence_on_same_line(self) -> None:
        """Comment close mid-line reveals a fence marker after it."""
        text = "<!-- done -->```python\ncode"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_fence_inside_already_open_comment_ignored(self) -> None:
        """Fence marker on a line while comment is open from prior line."""
        text = "<!--\n```python\n-->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_fence_inside_already_open_comment_with_outer_tag(self) -> None:
        """Fence inside open comment with an outer open tag."""
        text = "<div>\n<!--\n```python\n-->\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_closed_comment_then_fence_with_comment_inside(self) -> None:
        """Closed comment before fence does not hide fence opener."""
        text = "<!-- ok -->```<!-- partial\ncode"
        result = close_open_markdown(text)
        assert result == "\n```"


class TestCloseOpenMarkdownRawTags:
    """Tests for raw-content tag zones (script, style)."""

    def test_unclosed_script(self) -> None:
        """Unclosed script tag gets closed."""
        text = "<script>\nvar x = 1;"
        result = close_open_markdown(text)
        assert result == "\n</script>"

    def test_unclosed_style(self) -> None:
        """Unclosed style tag gets closed."""
        text = "<style>\n.cls { color: red; }"
        result = close_open_markdown(text)
        assert result == "\n</style>"

    def test_closed_script_no_repair(self) -> None:
        """Properly closed script needs no repair."""
        text = "<script>\nvar x = 1;\n</script>"
        result = close_open_markdown(text)
        assert result == ""

    def test_tags_inside_closed_script_ignored(self) -> None:
        """Tag-like strings inside script are not tracked."""
        text = "<script>\nvar html = '<div>';\n</script>"
        result = close_open_markdown(text)
        assert result == ""

    def test_tags_inside_unclosed_script_ignored(self) -> None:
        """Tags inside unclosed script are ignored; outer div still tracked."""
        text = "<div>\n<script>\nvar html = '<table>';"
        result = close_open_markdown(text)
        assert result == "\n</script>\n</div>"

    def test_script_open_and_close_same_line(self) -> None:
        """Script opened and closed on same line; subsequent tag tracked."""
        text = "<script>var x=1;</script>\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_content_after_script_close_processed(self) -> None:
        """Content after script close on same line is processed normally."""
        text = "<script>x=1;</script><div>content"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_script_inside_code_fence_is_literal(self) -> None:
        """Script tags inside a code fence are literal text."""
        text = "```\n<script>\n```"
        result = close_open_markdown(text)
        assert result == ""

    def test_script_inside_comment_is_ignored(self) -> None:
        """Script tag inside a comment is not a real script zone."""
        text = "<!-- <script> -->\n<div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_script_after_comment_on_same_line(self) -> None:
        """Script tag after a comment close on the same line is tracked."""
        text = "<!-- comment --><script>\ncode"
        result = close_open_markdown(text)
        assert result == "\n</script>"

    def test_comment_after_script_close_same_line(self) -> None:
        """Comment after script close on same line is handled."""
        text = "<script>x=1;</script><!-- <div> -->"
        result = close_open_markdown(text)
        assert result == ""

    def test_multi_line_script_close_processes_remainder(self) -> None:
        """After multi-line script closes, remainder of line is processed."""
        text = "<script>\nvar x;\n</script><div>content"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_script_opens_before_comment_on_same_line(self) -> None:
        """Script at line start takes priority over <!-- later on the line."""
        text = "<script><!-- partial\ncode"
        result = close_open_markdown(text)
        assert result == "\n</script>"

    def test_style_opens_before_comment_on_same_line(self) -> None:
        """Style at line start takes priority over <!-- later on the line."""
        text = "<style><!-- partial\nbody{}"
        result = close_open_markdown(text)
        assert result == "\n</style>"

    def test_script_same_line_close_after_comment_inside_raw(self) -> None:
        """Script close after <!-- on the same line is still recognized."""
        text = "<script><!-- partial</script><div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_style_same_line_close_after_comment_inside_raw(self) -> None:
        """Style close after <!-- on the same line is still recognized."""
        text = "<style><!-- partial</style><div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_style_same_line_close_after_comment_no_trailing(self) -> None:
        """Style with inner <!-- that closes on same line needs no repair."""
        text = "<style><!-- partial</style>"
        result = close_open_markdown(text)
        assert result == ""


class TestCloseOpenMarkdownRawTagCommentInteraction:
    """Tests for raw-tag and comment interaction on the same line."""

    def test_script_close_then_comment_then_tag_same_line(self) -> None:
        """Closed script then closed comment then open tag on one line."""
        text = "<script>x</script><!-- ok --><div>text"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_closed_comment_then_script_with_comment_inside(self) -> None:
        """Closed comment before script does not hide script close."""
        text = "<!-- ok --><script><!-- partial</script><div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"

    def test_closed_comment_then_script_with_comment_no_trailing(self) -> None:
        """Closed comment before script that closes after inner <!--."""
        text = "<!-- ok --><script><!-- partial</script>"
        result = close_open_markdown(text)
        assert result == ""

    def test_closed_comment_then_style_with_comment_inside(self) -> None:
        """Closed comment before style does not hide style close."""
        text = "<!-- ok --><style><!-- partial</style><div>"
        result = close_open_markdown(text)
        assert result == "\n</div>"


class TestCloseOpenMarkdownCombinations:
    """Tests for combinations of constructs."""

    def test_html_inside_unclosed_fence_ignored(self) -> None:
        """HTML tags inside an unclosed code fence are literal text."""
        text = "```\n<div>\n<table>"
        result = close_open_markdown(text)
        assert result == "\n```"

    def test_html_before_unclosed_fence(self) -> None:
        """HTML opened before a code fence is still tracked."""
        text = "<div>\nsome text\n```\ncode"
        result = close_open_markdown(text)
        assert result == "\n```\n</div>"

    def test_closed_fence_then_unclosed_html(self) -> None:
        """Closed code fence followed by unclosed HTML."""
        text = "```\ncode\n```\n<div>\ncontent"
        result = close_open_markdown(text)
        assert result == "\n</div>"


class TestCloseOpenMarkdownEdgeCases:
    """Tests for edge cases."""

    def test_empty_string(self) -> None:
        """Empty input returns empty suffix."""
        assert close_open_markdown("") == ""

    def test_plain_text(self) -> None:
        """Plain text with no markdown constructs."""
        assert close_open_markdown("Hello world\nThis is plain text.") == ""

    def test_whitespace_only(self) -> None:
        """Whitespace-only input returns empty suffix."""
        assert close_open_markdown("   \n  \n") == ""

    def test_inline_formatting_only(self) -> None:
        """Bold, italic, links do not trigger repair."""
        text = "Some **bold** and *italic* and [link](url)"
        assert close_open_markdown(text) == ""
