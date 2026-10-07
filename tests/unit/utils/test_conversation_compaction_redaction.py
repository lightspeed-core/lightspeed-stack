"""Unit tests for redaction in compacted mode (LCORE-4593)."""

from typing import Any, Optional, cast

import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
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


async def _compact(
    mocker: MockerFixture, items: list[Any], redact: Optional[TextRedactor]
) -> cc.CompactionResult:
    """Apply compaction to RAW_QUERY over *items*, far below the trigger."""
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
        inference_config=InferenceConfiguration(context_windows={MODEL: 1_000_000}),
        compaction_config=CompactionConfiguration(enabled=True),
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
