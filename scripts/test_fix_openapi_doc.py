"""Behavioral tests for the OpenAPI documentation command-line filter."""

from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

SCRIPT = Path(__file__).with_name("fix_openapi_doc.py")


class TestFixOpenapiDoc:
    """Tests for the standalone OpenAPI documentation filter script."""

    def assert_filter(self, source, expected, *filenames) -> None:
        """Run the filter script and assert that it transforms stdin as expected."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, filenames)],
            input=source,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout == expected

    @pytest.mark.parametrize(
        "source, expected",
        [
            ("", ""),
            ("\n", "\n"),
            ("last line", "last line\n"),
            ("first\n\nlast\n", "first\n\nlast\n"),
            ("first\r\nlast\r\n", "first\nlast\n"),
            (
                "  indented\t \nUnicode: λ 日本語\n",
                "  indented\t \nUnicode: λ 日本語\n",
            ),
        ],
    )
    def test_plain_text_and_line_boundaries(self, source, expected) -> None:
        """Plain text should pass through unchanged, with normalized line endings."""
        self.assert_filter(source, expected)

    def test_only_exact_examples_heading_is_removed(self) -> None:
        """Remove only exact 'Examples' headings, not similar lines."""
        self.assert_filter(
            "Examples\nExamples of use\n Examples\nExamples \nexamples\nExamples",
            "Examples of use\n Examples\nExamples \nexamples\n",
        )

    @pytest.mark.parametrize(
        "source, expected",
        [
            ("```json\n```\n", ""),
            ('before\n```json\n{\n  "key": 1\n}\n```\nafter\n', "before\nafter\n"),
            ("```json\n{}\n``` \t\nafter", "after\n"),
            ("```json\n{}\n```\nmiddle\n```json\n[]\n```", "middle\n"),
            ("before\n```json\nunterminated", "before\n"),
            ("```json", ""),
            ("```json\n```python\nExamples\n |\n```\nafter\n", "after\n"),
        ],
    )
    def test_json_blocks_are_removed(self, source, expected) -> None:
        """Strip JSON code blocks and their contents from the output."""
        self.assert_filter(source, expected)

    def test_python_and_text_blocks_preserve_filter_markers(self) -> None:
        """Python and text blocks should preserve embedded filter markers verbatim."""
        for language in ("python", "text"):
            for closing in ("```\n", "``` \t\n", ""):
                block = (
                    f"```{language}\nExamples\n```json\n"
                    '{"example": true}\n| row\n |\n' + closing
                )
                self.assert_filter(block, block)

    def test_filtering_resumes_after_protected_code(self) -> None:
        """Filtering should resume after exiting a protected code block."""
        for language in ("python", "text"):
            self.assert_filter(
                f"```{language}\nExamples\n``` \t\n"
                "Examples\n```json\n{}\n```\n| row\n |\nend\n",
                f"```{language}\nExamples\n``` \t\n| row |\nend\n",
            )

    def test_unmatched_closing_fence_is_preserved(self) -> None:
        """An unmatched closing fence should be left unchanged."""
        self.assert_filter("before\n``` \t\nafter\n", "before\n``` \t\nafter\n")

    @pytest.mark.parametrize(
        "source, expected",
        [
            ("| row\n |\nafter\n", "| row |\nafter\n"),
            ("| row\n |", "| row |\n"),
            ("| row\r\n |\r\n", "| row |\n"),
            ("| first\n |\n| second\n |\n", "| first |\n| second |\n"),
            ("| row\n |\n |\nafter\n", "| row |\nafter\n"),
            ("| complete |\nlast", "| complete |\nlast\n"),
        ],
    )
    def test_table_continuations(self, source, expected) -> None:
        """Table continuation lines should be merged into the preceding row."""
        self.assert_filter(source, expected)

    @pytest.mark.parametrize(
        "continuation",
        ["|", "  |", " | ", "\t|", " | extra"],
    )
    def test_near_match_continuations_are_preserved(self, continuation) -> None:
        """Near-matching lines should not be treated as table continuations."""
        source = f"| row\n{continuation}\nend\n"
        self.assert_filter(source, source)

    def test_multiple_input_files_are_processed_as_one_stream(self) -> None:
        """Multiple input files should be concatenated and processed as a single stream."""
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.md"
            second = Path(directory) / "second.md"
            first.write_text("before\n```json\n{}\n", encoding="utf-8")
            second.write_text("```\n| row\n |\n", encoding="utf-8")
            self.assert_filter("", "before\n| row |\n", first, second)

    def test_explicit_stdin_filename(self) -> None:
        """A literal '-' argument should be treated as standard input."""
        self.assert_filter("Examples\nkept\n", "kept\n", "-")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
