"""Unit tests for GraniteGuardian.wrap_run_event_stream (streaming output guardrails)."""

# pylint: disable=protected-access
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from collections.abc import AsyncIterator
from typing import Literal

import pytest
from pydantic_ai.messages import (
    AgentStreamEvent,
    FinalResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.usage import RequestUsage
from pytest_mock import MockerFixture

from models.config import GraniteGuardianConfig, RiskDefinition
from pydantic_ai_lightspeed.capabilities.granite_guardian._capability import (
    GraniteGuardian,
    _OutputGuardrailViolation,
)

_MODULE = "pydantic_ai_lightspeed.capabilities.granite_guardian._capability"


async def _event_stream(
    events: list[AgentStreamEvent],
) -> AsyncIterator[AgentStreamEvent]:
    """Yield a fixed list of stream events for wrap_run_event_stream tests."""
    for event in events:
        yield event


class _FakeCloseableStream:
    """Async iterable that tracks whether ``aclose`` was called."""

    def __init__(self, events: list[AgentStreamEvent]) -> None:
        self._events = list(events)
        self.closed = False

    def __aiter__(self) -> "_FakeCloseableStream":
        return self

    async def __anext__(self) -> AgentStreamEvent:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def aclose(self) -> None:
        """Mark the stream as closed."""
        self.closed = True


class _TrackingStream:
    """Async iterable that records how many events were pulled from it."""

    def __init__(self, events: list[AgentStreamEvent]) -> None:
        self._events = list(events)
        self.pulled = 0

    def __aiter__(self) -> "_TrackingStream":
        return self

    async def __anext__(self) -> AgentStreamEvent:
        if not self._events:
            raise StopAsyncIteration
        self.pulled += 1
        return self._events.pop(0)


def _make_risk(
    name: str = "test_risk",
    description: str = "test description",
    threshold: float = 0.5,
    points: list[Literal["input", "output", "tool"]] | None = None,
    enabled: bool = True,
    violation_message: str = "Blocked.",
) -> RiskDefinition:
    """Build a RiskDefinition for testing."""
    return RiskDefinition(
        name=name,
        description=description,
        threshold=threshold,
        points=points or ["input"],
        enabled=enabled,
        violation_message=violation_message,
    )


def _make_config(
    url: str = "https://example.com/v1",
    risks: list[RiskDefinition] | None = None,
    api_key: str | None = None,
    model_id: str | None = None,
    streaming_output_check_interval_tokens: int | None = None,
) -> GraniteGuardianConfig:
    """Build a GraniteGuardianConfig for testing."""
    kwargs: dict = {
        "url": url,
        "api_key": api_key,
        "risks": risks or [_make_risk()],
    }
    if model_id is not None:
        kwargs["model_id"] = model_id
    if streaming_output_check_interval_tokens is not None:
        kwargs["streaming_output_check_interval_tokens"] = (
            streaming_output_check_interval_tokens
        )
    return GraniteGuardianConfig(**kwargs)


class TestGraniteGuardianWrapRunEventStream:
    """Tests for GraniteGuardian.wrap_run_event_stream (output guardrails)."""

    @pytest.fixture(autouse=True)
    def _mock_init(self, mocker: MockerFixture) -> None:
        """Mock model creation and clear cache for all tests."""
        GraniteGuardian._model_cache.clear()
        mocker.patch(f"{_MODULE}.httpx.AsyncClient")
        mocker.patch(f"{_MODULE}.AsyncOpenAI")
        mocker.patch(f"{_MODULE}.OpenAIProvider")
        mocker.patch(f"{_MODULE}.OpenAIChatModel")

    @pytest.mark.asyncio
    async def test_passthrough_when_no_output_guardrails(
        self, mocker: MockerFixture
    ) -> None:
        """Test that events pass through untouched when no risk targets output."""
        mock_run_risk_check = mocker.patch(f"{_MODULE}._run_risk_check")

        config = _make_config(risks=[_make_risk(points=["input"])])
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="hello"))
        ]
        result = [
            event
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            )
        ]

        assert result == events
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_closes_stream_on_passthrough(self, mocker: MockerFixture) -> None:
        """Test that the underlying stream is closed after a passthrough run."""
        mocker.patch(f"{_MODULE}._run_risk_check")
        config = _make_config(risks=[_make_risk(points=["input"])])
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="hello"))
        ]
        fake_stream = _FakeCloseableStream(events)
        async for _ in guardian.wrap_run_event_stream(
            mocker.Mock(), stream=fake_stream
        ):
            pass

        assert fake_stream.closed is True

    @pytest.mark.asyncio
    async def test_buffers_until_interval_then_flushes(
        self, mocker: MockerFixture
    ) -> None:
        """Test that events are withheld until the token interval is reached."""
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check", return_value=(None, RequestUsage())
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="aa bb")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" cc dd")),
        ]
        result = [
            event
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            )
        ]

        assert result == events
        mock_run_risk_check.assert_called_once()
        prompt = mock_run_risk_check.call_args[0][0]
        assert prompt == "aa bb cc dd"

    @pytest.mark.asyncio
    async def test_checks_only_new_chunk_not_cumulative_text(
        self, mocker: MockerFixture
    ) -> None:
        """Test that each interval check screens only the newly generated chunk.

        Resending everything checked so far would make Guardian's workload
        grow quadratically with response length; each check should cover
        only the text produced since the previous check.
        """
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check", return_value=(None, RequestUsage())
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=2)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="aa bb")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" cc dd")),
        ]
        result = [
            event
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            )
        ]

        assert result == events
        prompts = [call.args[0] for call in mock_run_risk_check.call_args_list]
        assert prompts == ["aa bb", " cc dd"]

    @pytest.mark.asyncio
    async def test_final_check_covers_remainder_below_interval(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a short final chunk is still checked even under the interval."""
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check", return_value=(None, RequestUsage())
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=10)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="short text"))
        ]
        result = [
            event
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            )
        ]

        assert result == events
        mock_run_risk_check.assert_called_once()
        assert mock_run_risk_check.call_args[0][0] == "short text"

    @pytest.mark.asyncio
    async def test_violation_raises_and_drops_buffered_events(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a mid-stream violation raises and withholds buffered events.

        A synthetic ``PartEndEvent`` carrying the violation message is
        yielded in place of the withheld events, so downstream consumers
        that build a response from stream events see the rejection text.
        """
        mocker.patch(f"{_MODULE}.estimate_tokens", return_value=100)
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="bad text"))
        ]

        collected: list[AgentStreamEvent] = []
        with pytest.raises(_OutputGuardrailViolation, match="Blocked output."):
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            ):
                collected.append(event)

        assert len(collected) == 1
        assert isinstance(collected[0], PartEndEvent)
        assert isinstance(collected[0].part, TextPart)
        assert collected[0].part.content == "Blocked output."

    @pytest.mark.asyncio
    async def test_violation_on_final_remainder_check(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a violation found only on the final check still raises."""
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=10)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="short text"))
        ]

        collected: list[AgentStreamEvent] = []
        with pytest.raises(_OutputGuardrailViolation, match="Blocked output."):
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            ):
                collected.append(event)

        assert len(collected) == 1
        assert isinstance(collected[0], PartEndEvent)
        assert isinstance(collected[0].part, TextPart)
        assert collected[0].part.content == "Blocked output."

    @pytest.mark.asyncio
    async def test_closes_stream_on_violation(self, mocker: MockerFixture) -> None:
        """Test that the underlying stream is closed even when a violation is raised."""
        mocker.patch(f"{_MODULE}.estimate_tokens", return_value=100)
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="bad text"))
        ]
        fake_stream = _FakeCloseableStream(events)

        with pytest.raises(_OutputGuardrailViolation):
            async for _ in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=fake_stream
            ):
                pass

        assert fake_stream.closed is True

    @pytest.mark.asyncio
    async def test_drains_remaining_events_on_mid_stream_violation(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a mid-stream violation drains the rest of the stream.

        The underlying provider call must be allowed to run to completion
        (rather than being torn down as soon as a violation is detected) so
        the final usage totals are received and any server-side persistence
        of the turn -- tied to response completion -- isn't left half-done.
        """
        mocker.patch(f"{_MODULE}.estimate_tokens", return_value=100)
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="bad text")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" more")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=" text")),
        ]
        tracking_stream = _TrackingStream(events)

        with pytest.raises(_OutputGuardrailViolation):
            async for _ in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=tracking_stream
            ):
                pass

        # All 3 events were pulled from the underlying stream even though only
        # the violating chunk (the first event) triggered the check.
        assert tracking_stream.pulled == len(events)

    @pytest.mark.asyncio
    async def test_drain_error_does_not_mask_violation(
        self, mocker: MockerFixture
    ) -> None:
        """Test that an error while draining doesn't hide the guardrail violation."""
        mocker.patch(f"{_MODULE}.estimate_tokens", return_value=100)
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        async def _broken_stream() -> AsyncIterator[AgentStreamEvent]:
            yield PartStartEvent(index=0, part=TextPart(content="bad text"))
            raise RuntimeError("connection dropped")

        with pytest.raises(_OutputGuardrailViolation, match="Blocked output."):
            async for _ in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_broken_stream()
            ):
                pass

    @pytest.mark.asyncio
    async def test_non_text_events_are_preserved_in_order(
        self, mocker: MockerFixture
    ) -> None:
        """Test that non-text events are buffered and flushed in original order."""
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mocker.patch(f"{_MODULE}._run_risk_check", return_value=(None, RequestUsage()))

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=2)
        guardian = GraniteGuardian(config=config)

        final_event = FinalResultEvent(tool_name=None, tool_call_id=None)
        events: list[AgentStreamEvent] = [
            PartStartEvent(index=0, part=TextPart(content="aa bb")),
            final_event,
        ]
        result = [
            event
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            )
        ]

        assert result == events

    @pytest.mark.asyncio
    async def test_non_text_event_released_immediately_when_nothing_pending(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a non-text event isn't withheld while no text is buffered.

        A tool-call event (or any other event with no text) shouldn't be
        held back just because output guardrails are configured; it should
        only be buffered once there's pending text it needs to wait behind.
        """
        mocker.patch(f"{_MODULE}.estimate_tokens", side_effect=lambda t: len(t.split()))
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check", return_value=(None, RequestUsage())
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=10)
        guardian = GraniteGuardian(config=config)

        final_event = FinalResultEvent(tool_name=None, tool_call_id=None)
        events: list[AgentStreamEvent] = [final_event]

        collected: list[AgentStreamEvent] = []
        async for event in guardian.wrap_run_event_stream(
            mocker.Mock(), stream=_event_stream(events)
        ):
            collected.append(event)

        # Released immediately, without ever triggering a guardrail check.
        assert collected == events
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_violation_part_end_event_uses_current_part_index(
        self, mocker: MockerFixture
    ) -> None:
        """Test that the synthetic PartEndEvent reports the open part's index.

        The violation should be attributed to the text part actually being
        screened, tracked from the most recent PartStartEvent, rather than
        always assuming index 0.
        """
        mocker.patch(f"{_MODULE}.estimate_tokens", return_value=100)
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked output.", RequestUsage()),
        )

        risk = _make_risk(points=["output"])
        config = _make_config(risks=[risk], streaming_output_check_interval_tokens=3)
        guardian = GraniteGuardian(config=config)

        events: list[AgentStreamEvent] = [
            PartStartEvent(index=2, part=TextPart(content="bad text"))
        ]

        collected: list[AgentStreamEvent] = []
        with pytest.raises(_OutputGuardrailViolation, match="Blocked output."):
            async for event in guardian.wrap_run_event_stream(
                mocker.Mock(), stream=_event_stream(events)
            ):
                collected.append(event)

        assert len(collected) == 1
        assert isinstance(collected[0], PartEndEvent)
        assert collected[0].index == 2
