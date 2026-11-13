"""Unit tests for safety.types."""

from pydantic_ai.messages import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)

from safety.types import GuardrailResult, OutputState


def _text_start(content: str, index: int = 0) -> PartStartEvent:
    """Return a text part-start event."""
    return PartStartEvent(index=index, part=TextPart(content=content))


def _text_delta(content: str, index: int = 0) -> PartDeltaEvent:
    """Return a text part-delta event."""
    return PartDeltaEvent(index=index, delta=TextPartDelta(content_delta=content))


def _text_end(content: str, index: int = 0) -> PartEndEvent:
    """Return a text part-end event."""
    return PartEndEvent(index=index, part=TextPart(content=content))


class TestGuardrailResult:
    """Tests for GuardrailResult factories."""

    def test_allow(self) -> None:
        """Test that allow carries no message or replacement."""
        result = GuardrailResult.allow()

        assert result == GuardrailResult(action="allow")
        assert result.message is None
        assert result.replacement is None

    def test_block_with_message(self) -> None:
        """Test that block stores the caller-facing message."""
        result = GuardrailResult.block("stop")

        assert result.action == "block"
        assert result.message == "stop"
        assert result.replacement is None

    def test_block_without_message(self) -> None:
        """Test that block can omit the caller-facing message."""
        assert GuardrailResult.block().message is None

    def test_replace(self) -> None:
        """Test that replace stores the replacement value."""
        result = GuardrailResult.replace({"safe": True})

        assert result.action == "replace"
        assert result.replacement == {"safe": True}
        assert result.message is None


class TestOutputState:
    """Tests for the streamed-output buffer."""

    def test_text_joins_start_and_delta_without_a_separator(self) -> None:
        """Test that buffered text parts are concatenated in order."""
        state = OutputState()
        state.append(_text_start("A"))
        state.append(_text_delta("B"))
        state.append(_text_start("C", index=1))

        assert state.text() == "ABC"
        assert state.text() == "ABC"

    def test_text_ignores_non_text_events(self) -> None:
        """Test that tool-call events do not contribute buffered text."""
        state = OutputState()
        state.append(_text_start("keep"))
        state.append(
            PartStartEvent(index=1, part=ToolCallPart("lookup", {"q": "pods"}))
        )

        assert state.text() == "keep"

    def test_ready_when_enough_events_have_accumulated(self) -> None:
        """Test that the buffer is ready once it reaches the interval."""
        state = OutputState()
        state.append(_text_start("a"))

        assert state.ready(2) is False

        state.append(_text_delta("b"))

        assert state.ready(2) is True

    def test_ready_when_a_part_ends_before_the_interval(self) -> None:
        """Test that a completed part is ready before the interval is reached."""
        state = OutputState()
        state.append(_text_start("a"))
        state.append(_text_end("a"))

        assert state.ready(50) is True

    def test_empty_buffer_is_not_ready_for_a_positive_interval(self) -> None:
        """Test that an empty buffer waits until an event arrives."""
        assert OutputState().ready(1) is False

    def test_flush_returns_a_copy_and_clears_the_buffer(self) -> None:
        """Test that flush hands back the buffered events and then resets."""
        state = OutputState()
        start = _text_start("ab")
        delta = _text_delta("c")
        state.append(start)
        state.append(delta)

        text, events = state.flush()

        assert text == "abc"
        assert events == [start, delta]
        assert events is not state.events
        assert not state.events
        assert state.text() == ""
        events.append(_text_end("abc"))
        assert not state.events

    def test_part_end_text_is_not_appended_again(self) -> None:
        """Test that a part-end event triggers a check without duplicating its text."""
        state = OutputState()
        state.append(_text_start(""))
        state.append(_text_delta("hello"))
        state.append(_text_end("hello"))

        assert state.text() == "hello"
