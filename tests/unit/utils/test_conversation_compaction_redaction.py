"""Unit tests for redaction in compacted mode (LCORE-4593)."""

from typing import Any, Optional, cast

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.compaction import ConversationSummary
from models.config import (
    CompactionConfiguration,
    InferenceConfiguration,
    RedactionConfig,
    RedactionRule,
    RedactionShieldConfiguration,
)
from pydantic_ai_lightspeed.ogx._model import _model_settings_from_responses_params
from utils import conversation_compaction as cc
from utils.shields import request_redactor
from utils.types import TextRedactor

MODEL = "openai/gpt-4o-mini"
RAW_QUERY = "mail me at jane@example.com"
REDACTED_QUERY = "mail me at [EMAIL]"
SHIELD = RedactionShieldConfiguration(
    name="pii-redaction",
    provider_id="redaction",
    config=RedactionConfig(
        rules=[RedactionRule(pattern=r"\S+@\S+", replacement="[EMAIL]")]
    ),
)


def _msg(role: str, text: str) -> OpenAIResponseMessage:
    """Build a typed OGX message item for tests."""
    return OpenAIResponseMessage(role=cast("Any", role), content=text)


# A conversation compacted once, with a buffer of two turns: the marker covers
# the first turn and sits behind the two turns that compaction kept.
HISTORY = [
    _msg("user", "q1"),
    _msg("assistant", "a1"),
    _msg("user", "ask bob@example.org"),
    _msg("assistant", "bob@example.org is out"),
    _msg("user", "then ask ann@example.net"),
    _msg("assistant", "ann@example.net replied"),
    _msg(
        "user", f"{cc.MARKER_SENTINEL} {cc.MARKER_COVERS_PREFIX}2] met eve@example.com"
    ),
    _msg("user", "q4"),
    _msg("assistant", "a4"),
]


async def _compact(
    mocker: MockerFixture,
    items: list[Any],
    redact: Optional[TextRedactor],
    window: int = 1_000_000,
    **compaction: Any,
) -> cc.CompactionResult:
    """Apply compaction to RAW_QUERY over *items*, by default far below the trigger."""
    mocker.patch.object(
        cc, "get_all_conversation_items", mocker.AsyncMock(return_value=items)
    )
    return await cc.apply_compaction_blocking(
        client=mocker.AsyncMock(),
        params=ResponsesApiParams(
            input=RAW_QUERY,
            model=MODEL,
            conversation="conv_abc123",
            store=True,
            stream=False,
        ),
        inference_config=InferenceConfiguration(context_windows={MODEL: window}),
        compaction_config=CompactionConfiguration(enabled=True, **compaction),
        redact=redact,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shield_ids", "expected_query"),
    [(None, REDACTED_QUERY), ([], RAW_QUERY)],
    ids=["shield selected", "shield deselected"],
)
async def test_compacted_turn_carries_the_redacted_query(
    mocker: MockerFixture, shield_ids: Optional[list[str]], expected_query: str
) -> None:
    """A compacted turn sends and stores the query as the selected shields redact it.

    The explicit input, the ``extra_body`` override built from it (which
    replaces the input on the wire) and the text the endpoints store all carry
    the redacted query. Without a redaction shield they carry it as it arrived.
    """
    items = [
        _msg("user", "old q"),
        _msg("assistant", "old a"),
        _msg("user", f"{cc.MARKER_SENTINEL} {cc.MARKER_COVERS_PREFIX}2] earlier"),
    ]

    result = await _compact(mocker, items, request_redactor([SHIELD], shield_ids))

    assert result.compacted is True
    assert isinstance(result.params.input, list)
    assert result.params.input[-1].content == expected_query
    settings = _model_settings_from_responses_params(result.params)
    override = cast("dict[str, Any]", settings["extra_body"])["input"]
    assert override[-1]["content"] == expected_query
    assert result.original_input == expected_query


@pytest.mark.asyncio
async def test_replayed_user_turns_and_summaries_are_redacted(
    mocker: MockerFixture,
) -> None:
    """What is replayed as user messages is redacted; other turns are not."""
    items = [*HISTORY, _msg("system", "ops@example.com owns the report")]
    result = await _compact(mocker, items, request_redactor([SHIELD]))

    assert [message.content for message in result.params.input] == [
        "Summary of earlier conversation:\nmet [EMAIL]",
        "ask [EMAIL]",
        "bob@example.org is out",
        "then ask [EMAIL]",
        "ann@example.net replied",
        "q4",
        "a4",
        "ops@example.com owns the report",
        REDACTED_QUERY,
    ]


@pytest.mark.asyncio
async def test_summarizer_gets_redacted_user_turns(mocker: MockerFixture) -> None:
    """The summarizer is handed redacted user turns, and the boundary stays put.

    The first kept turn is looked up in the stored items by identity
    (LCORE-4219), so the kept turns must not be replaced by redacted copies
    before that: with the older marker among them the fallback count is 5.
    """
    summary = ConversationSummary(
        summary_text="second summary",
        summarized_through_turn=4,
        token_count=2,
        created_at="2026-10-07T00:00:00Z",
        model_used=MODEL,
    )
    summarize = mocker.patch.object(
        cc, "summarize_chunk", mocker.AsyncMock(return_value=summary)
    )
    mocker.patch.object(cc, "_write_summary_marker", mocker.AsyncMock())

    await _compact(
        mocker,
        HISTORY,
        request_redactor([SHIELD]),
        window=1000,
        threshold_ratio=0.01,
        token_floor=0,
        buffer_turns=2,
    )

    summarized = summarize.await_args.args[2]
    assert [item.content for item in summarized] == [
        "ask [EMAIL]",
        "bob@example.org is out",
    ]
    assert summarize.await_args.kwargs["summarized_through_turn"] == 4
