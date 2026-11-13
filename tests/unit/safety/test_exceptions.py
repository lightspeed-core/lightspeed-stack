"""Unit tests for safety.exceptions."""

from safety.exceptions import OutputBlocked, ToolBlocked


class TestOutputBlocked:
    """Tests for OutputBlocked."""

    def test_stores_reason(self) -> None:
        """Test that the block reason is retained on the exception."""
        error = OutputBlocked("unsafe")

        assert error.reason == "unsafe"
        assert error.args == ("unsafe",)

    def test_reason_defaults_to_none(self) -> None:
        """Test that a missing reason is stored as None."""
        assert OutputBlocked().reason is None

    def test_is_a_base_exception(self) -> None:
        """Test that output blocks bypass except Exception handlers."""
        assert issubclass(OutputBlocked, BaseException)
        assert not issubclass(OutputBlocked, Exception)


class TestToolBlocked:
    """Tests for ToolBlocked."""

    def test_is_an_output_block(self) -> None:
        """Test that a tool block can be handled as an output block."""
        error = ToolBlocked("tool unsafe")

        assert isinstance(error, OutputBlocked)
        assert error.reason == "tool unsafe"

    def test_reason_defaults_to_none(self) -> None:
        """Test that a tool block can omit its reason."""
        assert ToolBlocked().reason is None
