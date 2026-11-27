"""Unit tests for utils/tiered_compaction."""

import asyncio
from typing import Optional

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    CapabilityEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from constants import DEFAULT_CONTEXT_WINDOW
from models.common.agents import AgentRunDeps
from models.config import CompactionConfiguration
from utils.tiered_compaction import (
    CLAMP_MAX_PART_TOKENS,
    CompactionStartedEvent,
    SignallingTieredCompaction,
    build_tiered_compaction,
)
from utils.token_estimator import estimate_tokens

ENABLED = CompactionConfiguration(
    enabled=True, threshold_ratio=0.5, buffer_turns=6, buffer_max_ratio=0.25
)


def _build(
    config: CompactionConfiguration = ENABLED,
    model: Optional[TestModel] = None,
    context_window: Optional[int] = None,
) -> TieredCompaction[object]:
    """Build the capability for an enabled configuration and assert it exists."""
    compaction = build_tiered_compaction(config, model or TestModel(), context_window)
    assert compaction is not None
    return compaction


def _summarizer(compaction: TieredCompaction[object]) -> SummarizingCompaction[object]:
    """Return the summarizing tier, which the builder puts last."""
    summarizer = compaction.tiers[-1]
    assert isinstance(summarizer, SummarizingCompaction)
    return summarizer


def test_disabled_configuration_builds_nothing() -> None:
    """A disabled configuration yields no capability, whatever else is passed."""
    config = CompactionConfiguration(enabled=False, summary_prompt="{messages}")
    assert build_tiered_compaction(config, TestModel(), 128_000) is None


def test_builder_returns_the_signalling_capability() -> None:
    """The built capability announces compaction on the run stream (LCORE-4693)."""
    assert isinstance(_build(), SignallingTieredCompaction)


def test_tiers_come_in_fixed_order() -> None:
    """Clamp, then clear tool results, then summarize."""
    tiers = _build().tiers
    assert [type(tier) for tier in tiers] == [
        ClampOversizedMessages,
        ClearToolResults,
        SummarizingCompaction,
    ]
    assert isinstance(tiers[0], ClampOversizedMessages)
    assert tiers[0].max_part_tokens == CLAMP_MAX_PART_TOKENS


@pytest.mark.parametrize("context_window", [None, 32_000])
def test_threshold_and_context_window_mapping(context_window: Optional[int]) -> None:
    """threshold_ratio becomes target_fraction; the window passes through."""
    compaction = _build(context_window=context_window)
    assert compaction.target_fraction == 0.5
    assert compaction.target_tokens is None
    assert compaction.context_window == context_window
    assert compaction.fallback_context_window == DEFAULT_CONTEXT_WINDOW


@pytest.mark.parametrize(
    ("context_window", "expected_keep_tokens"),
    [(None, None), (10_000, 2_500), (999, 249)],
)
def test_summarizing_tier_mapping(
    context_window: Optional[int], expected_keep_tokens: Optional[int]
) -> None:
    """buffer_turns and buffer_max_ratio map onto the summarizing tier."""
    model = TestModel()
    summarizer = _summarizer(_build(model=model, context_window=context_window))
    assert summarizer.model is model
    assert summarizer.keep_messages == 6
    assert summarizer.keep_tokens == expected_keep_tokens
    assert summarizer.incremental
    assert summarizer.preserve_first_user_message
    assert summarizer.keep_user_messages


def test_estimate_tokens_is_the_tokenizer_everywhere() -> None:
    """The orchestrator and every tier count tokens with estimate_tokens."""
    compaction = _build(context_window=32_000)
    assert compaction.tokenizer is estimate_tokens
    for tier in compaction.tiers:
        assert isinstance(
            tier, (ClampOversizedMessages, ClearToolResults, SummarizingCompaction)
        )
        assert tier.tokenizer is estimate_tokens


def test_token_floor_is_ignored() -> None:
    """Builds that differ only in token_floor are identical."""
    model = TestModel()
    low = ENABLED.model_copy(update={"token_floor": 0})
    high = ENABLED.model_copy(update={"token_floor": 100_000})
    assert _build(low, model, 32_000) == _build(high, model, 32_000)


def test_zero_threshold_ratio_is_rejected() -> None:
    """The harness cannot compact at a zero fraction of the window."""
    config = ENABLED.model_copy(update={"threshold_ratio": 0.0})
    with pytest.raises(ValueError, match="target_fraction"):
        build_tiered_compaction(config, TestModel())


def test_default_summary_prompt_is_kept() -> None:
    """Without a configured prompt the harness default stays in place."""
    default = SummarizingCompaction[object](max_messages=1).summary_prompt
    assert _summarizer(_build()).summary_prompt == default


@pytest.mark.parametrize(
    "summary_prompt",
    ["Summarize for support:\n{messages}", "Keep {{literal}} braces.\n{messages}"],
)
def test_configured_summary_prompt_is_used(summary_prompt: str) -> None:
    """The configured prompt replaces the harness default."""
    config = CompactionConfiguration.model_validate(
        ENABLED.model_dump() | {"summary_prompt": summary_prompt}
    )
    summarizer = _summarizer(_build(config))
    assert summarizer.summary_prompt == summary_prompt


@pytest.mark.asyncio
async def test_capability_summarizes_history_inside_an_agent() -> None:
    """An agent with the capability sends the summary, not the old turns."""
    sent: list[list[ModelMessage]] = []

    def chat(messages: list[ModelMessage], _: AgentInfo) -> ModelResponse:
        """Record what the chat model receives and answer."""
        sent.append(messages)
        return ModelResponse(parts=[TextPart(content="answer")])

    # User turns outgrow keep_tokens (250): none is kept, so tail loss spares the query.
    history: list[ModelMessage] = []
    for turn in range(3):
        history.append(
            ModelRequest(parts=[UserPromptPart(content=f"q{turn} " + "x " * 300)])
        )
        history.append(
            ModelResponse(parts=[TextPart(content=f"a{turn} " + "y " * 300)])
        )
    compaction = _build(
        model=TestModel(custom_output_text="SUMMARY"), context_window=1_000
    )
    await Agent(FunctionModel(chat), capabilities=[compaction]).run(
        "current question", message_history=history
    )
    assert "SUMMARY" in repr(sent[-1])
    assert "current question" in repr(sent[-1])
    assert "q0 " not in repr(sent[-1])


def _long_history(turns: int = 3) -> list[ModelMessage]:
    """Build a history of *turns* user/assistant pairs, each far above keep_tokens."""
    history: list[ModelMessage] = []
    for turn in range(turns):
        history.append(
            ModelRequest(parts=[UserPromptPart(content=f"q{turn} " + "x " * 300)])
        )
        history.append(
            ModelResponse(parts=[TextPart(content=f"a{turn} " + "y " * 300)])
        )
    return history


def _signalling(
    summarizer_model: TestModel | FunctionModel,
) -> TieredCompaction[object]:
    """Build the signalling capability with the builder's summarizer settings and a tiny window."""
    summarizer = SummarizingCompaction[object](
        model=summarizer_model,
        max_messages=1,
        keep_messages=6,
        keep_tokens=250,
        tokenizer=estimate_tokens,
        incremental=True,
        preserve_first_user_message=True,
        keep_user_messages=True,
    )
    return SignallingTieredCompaction[object](
        tiers=[summarizer],
        target_fraction=0.5,
        context_window=1_000,
        tokenizer=estimate_tokens,
    )


class TestCompactionStartedEvent:
    """The start event announces compaction on the run stream (LCORE-4693)."""

    def test_event_kind_is_namespaced(self) -> None:
        """The event registers under the LCORE compaction namespace."""
        event = CompactionStartedEvent(message_count=6, target_tokens=500)
        assert event.kind == "lcore_compaction.compaction_started"
        assert event.event_dispatch == "stream"

    async def test_event_precedes_the_answer_on_the_stream(self) -> None:
        """The start event is yielded once, before the first part of the answer."""
        summarized = asyncio.Event()

        def summarize(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
            """Summarize and record that the summarizer ran."""
            summarized.set()
            return ModelResponse(parts=[TextPart(content="SUMMARY")])

        compaction = _signalling(FunctionModel(summarize))
        agent = Agent(TestModel(custom_output_text="answer"), capabilities=[compaction])
        kinds: list[str] = []
        started: list[CompactionStartedEvent] = []
        async with agent.run_stream_events(
            "current question", message_history=_long_history()
        ) as stream:
            async for event in stream:
                if isinstance(event, CompactionStartedEvent):
                    started.append(event)
                    kinds.append(event.kind)
                else:
                    kinds.append(event.event_kind)
        assert summarized.is_set()
        assert len(started) == 1
        assert started[0].message_count == 7
        assert started[0].target_tokens == 500
        assert started[0].capability_id
        assert kinds.index("lcore_compaction.compaction_started") < kinds.index(
            "part_start"
        )

    async def test_no_event_when_the_history_fits(self) -> None:
        """A history under the target leaves the stream without a start event."""
        compaction = _signalling(TestModel(custom_output_text="SUMMARY"))
        agent = Agent(TestModel(custom_output_text="answer"), capabilities=[compaction])
        kinds: list[str] = []
        async with agent.run_stream_events("hi") as stream:
            async for event in stream:
                if isinstance(event, CapabilityEvent):
                    kinds.append(event.kind)
        assert "lcore_compaction.compaction_started" not in kinds

    async def test_history_is_still_compacted(self) -> None:
        """Signalling does not change what the chat model receives."""
        sent: list[list[ModelMessage]] = []

        def chat(messages: list[ModelMessage], _: AgentInfo) -> ModelResponse:
            """Record the request and answer."""
            sent.append(messages)
            return ModelResponse(parts=[TextPart(content="answer")])

        compaction = _signalling(TestModel(custom_output_text="SUMMARY"))
        await Agent(FunctionModel(chat), capabilities=[compaction]).run(
            "current question", message_history=_long_history()
        )
        assert "SUMMARY" in repr(sent[-1])
        assert "q0 " not in repr(sent[-1])


class TestContextStatusOnTheRunDeps:
    """A compaction that changed the history marks the run as compacted (LCORE-4694)."""

    async def test_compacted_history_marks_the_run(self) -> None:
        """The run deps say compacted once a tier changed what the model receives."""
        compaction = _signalling(TestModel(custom_output_text="SUMMARY"))
        agent = Agent(TestModel(custom_output_text="answer"), capabilities=[compaction])
        deps = AgentRunDeps()
        await agent.run("current question", message_history=_long_history(), deps=deps)
        assert deps.context_status == "compacted"

    async def test_history_under_the_target_leaves_the_run_full(self) -> None:
        """No compaction, no change to the default."""
        compaction = _signalling(TestModel(custom_output_text="SUMMARY"))
        agent = Agent(TestModel(custom_output_text="answer"), capabilities=[compaction])
        deps = AgentRunDeps()
        await agent.run("hi", deps=deps)
        assert deps.context_status == "full"

    async def test_run_without_deps_still_compacts(self) -> None:
        """The capability does not require the run to carry deps."""
        sent: list[list[ModelMessage]] = []

        def chat(messages: list[ModelMessage], _: AgentInfo) -> ModelResponse:
            """Record the request and answer."""
            sent.append(messages)
            return ModelResponse(parts=[TextPart(content="answer")])

        compaction = _signalling(TestModel(custom_output_text="SUMMARY"))
        await Agent(FunctionModel(chat), capabilities=[compaction]).run(
            "current question", message_history=_long_history()
        )
        assert "SUMMARY" in repr(sent[-1])
