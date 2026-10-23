"""Unit tests for carrying the current prompt's media into the compacted input."""

# pylint: disable=protected-access

import json

import httpx
import pytest
from ogx_api.openai_responses import OpenAIResponseMessage
from pydantic_ai import Agent, ModelMessage
from pydantic_ai.messages import ImageUrl, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.settings import ModelSettings

from models.common.responses.responses_api_params import ResponsesApiParams
from pydantic_ai_lightspeed.ogx._model import (
    OgxResponsesModel,
    _model_settings_from_responses_params,
)
from pydantic_ai_lightspeed.ogx._provider import OgxProvider

IMAGE_B64 = "aW1hZ2UtYnl0ZXM="
IMAGE_URL = f"data:image/png;base64,{IMAGE_B64}"
IMAGE = ImageUrl(url=IMAGE_URL, media_type="image/png")
IMAGE_PART = {"image_url": IMAGE_URL, "type": "input_image", "detail": "auto"}
IMAGE_PROMPT = ["new question", IMAGE]
IMAGE_MESSAGES: list[ModelMessage] = [
    ModelRequest(parts=[UserPromptPart(content=IMAGE_PROMPT)])
]
# The explicit input before the new query: a summary and one recent turn.
HISTORY = [
    {
        "role": "user",
        "content": "Summary of earlier conversation:\nS1",
        "type": "message",
    },
    {"role": "user", "content": "recent q", "type": "message"},
    {"role": "assistant", "content": "recent a", "type": "message"},
]
ANSWER = {
    "id": "resp-1",
    "object": "response",
    "created_at": 0,
    "model": "test-model",
    "status": "completed",
    "output": [
        {
            "id": "msg-1",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "ok", "annotations": []}],
        }
    ],
    "parallel_tool_calls": False,
    "tool_choice": "auto",
    "tools": [],
}


def _make_settings(compacted: bool) -> OpenAIResponsesModelSettings:
    """Build model settings for the new query, in compacted mode or outside it."""
    items = [
        OpenAIResponseMessage(**item)
        for item in [*HISTORY, {"role": "user", "content": "new question"}]
    ]
    params = ResponsesApiParams(
        input=items if compacted else "new question",
        omit_conversation=compacted,
        model="provider/model",
        conversation="conv-1",
        max_infer_iters=3,
        store=True,
        stream=False,
    )
    return _model_settings_from_responses_params(params)


@pytest.fixture(name="bodies")
def bodies_fixture() -> list[bytes]:
    """Collect the request bodies that reach the transport."""
    return []


@pytest.fixture(name="provider")
def provider_fixture(bodies: list[bytes]) -> OgxProvider:
    """Create a provider whose transport records requests and answers them."""

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        if not json.loads(request.content)["stream"]:
            return httpx.Response(200, json=ANSWER)
        event = {"type": "response.created", "sequence_number": 0, "response": ANSWER}
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=f"event: response.created\ndata: {json.dumps(event)}\n\n",
        )

    return OgxProvider(
        base_url="http://ogx.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_settings_without_input_override_are_unchanged(
    provider: OgxProvider,
) -> None:
    """Test that outside compacted mode an image prompt changes nothing."""
    model = OgxResponsesModel("test-model", provider=provider)
    settings = _make_settings(compacted=False)
    assert await model._carry_prompt_media(IMAGE_MESSAGES, settings) is settings


@pytest.mark.asyncio
async def test_text_prompt_keeps_the_override(provider: OgxProvider) -> None:
    """Test that a text-only prompt leaves the explicit input as it was built."""
    model = OgxResponsesModel("test-model", provider=provider)
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="new question")])
    ]
    settings = _make_settings(compacted=True)
    assert await model._carry_prompt_media(messages, settings) is settings


@pytest.mark.asyncio
async def test_image_prompt_adds_the_image_to_the_new_query(
    provider: OgxProvider,
) -> None:
    """Test that the trailing user message is sent with the prompt's image."""
    model = OgxResponsesModel("test-model", provider=provider)
    settings = _make_settings(compacted=True)

    result = await model._carry_prompt_media(IMAGE_MESSAGES, settings)

    new_query = {
        "role": "user",
        "content": [{"text": "new question", "type": "input_text"}, IMAGE_PART],
    }
    assert result == {
        **settings,
        "extra_body": {**settings["extra_body"], "input": [*HISTORY, new_query]},
    }
    # the settings passed in are not modified
    assert settings["extra_body"]["input"][-1]["content"] == "new question"


@pytest.mark.asyncio
async def test_query_text_comes_from_the_explicit_input(provider: OgxProvider) -> None:
    """Test that the query text comes from the explicit input, not from the prompt."""
    model = OgxResponsesModel("test-model", provider=provider)
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=["recent a", IMAGE])])
    ]
    empty_query = {"role": "user", "content": "", "type": "message"}
    settings: ModelSettings = {"extra_body": {"input": [*HISTORY, empty_query]}}

    result = await model._carry_prompt_media(messages, settings)

    assert result is not None
    assert result["extra_body"]["input"] == [
        *HISTORY,
        {"role": "user", "content": [{"text": "", "type": "input_text"}, IMAGE_PART]},
    ]


@pytest.mark.asyncio
async def test_trailing_item_of_another_role_is_kept(provider: OgxProvider) -> None:
    """Test that the image is appended when no user message ends the input."""
    model = OgxResponsesModel("test-model", provider=provider)
    settings: ModelSettings = {"extra_body": {"input": HISTORY}}

    result = await model._carry_prompt_media(IMAGE_MESSAGES, settings)

    assert result is not None
    assert result["extra_body"]["input"] == [
        *HISTORY,
        {"role": "user", "content": [IMAGE_PART]},
    ]


@pytest.mark.asyncio
async def test_request_body_carries_the_image_as_outside_compacted_mode(
    provider: OgxProvider, bodies: list[bytes]
) -> None:
    """Test the serialised compacted request against the non-compacted one.

    The same prompt is sent once without and once with the compacted input
    override, through the real OpenAI client. The new query must go out
    identically both times, in compacted mode after a text-only history.
    """
    for compacted in (False, True):
        model = OgxResponsesModel(
            "test-model", provider=provider, settings=_make_settings(compacted)
        )
        await Agent(model, defer_model_check=True).run(IMAGE_PROMPT)

    plain_body, compacted_body = (json.loads(body) for body in bodies)
    assert plain_body["conversation"] == "conv-1"
    assert "conversation" not in compacted_body
    assert compacted_body["input"][:-1] == HISTORY
    assert compacted_body["input"][-1] == plain_body["input"][-1]
    assert bodies[1].count(IMAGE_B64.encode()) == 1


@pytest.mark.asyncio
async def test_streamed_request_body_carries_the_image(
    provider: OgxProvider, bodies: list[bytes]
) -> None:
    """Test that a streamed compacted request is sent with the image too."""
    settings = _make_settings(compacted=True)
    model = OgxResponsesModel("test-model", provider=provider)

    async with model.request_stream(IMAGE_MESSAGES, settings, ModelRequestParameters()):
        pass

    new_query = json.loads(bodies[0])["input"][-1]
    assert new_query["content"][1]["image_url"] == IMAGE_URL
