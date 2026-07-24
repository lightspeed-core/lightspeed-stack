"""Unit tests for utils/model_list.py helpers."""

from ogx_client.types import ListModelsResponse
from ogx_client.types.model import Model
from ogx_client.types.model_list_response import (
    AnthropicListModelsResponse,
    AnthropicListModelsResponseData,
    GoogleListModelsResponse,
    GoogleListModelsResponseModel,
)

from models.common.models import CatalogModel
from utils.model_list import (
    parse_anthropic_model,
    parse_google_model,
    parse_model_list_response,
    parse_openai_style_model,
)


def test_parse_openai_style_model_with_custom_metadata() -> None:
    """OpenAI-style models map custom_metadata into CatalogModel."""
    model = Model.model_construct(
        id="provider/model",
        created=1,
        owned_by="org",
        object="model",
        custom_metadata={
            "model_type": "llm",
            "provider_id": "provider",
            "provider_resource_id": "model",
            "extra": "value",
        },
    )

    parsed = parse_openai_style_model(model)

    assert isinstance(parsed, CatalogModel)
    assert parsed.identifier == "provider/model"
    assert parsed.model_type == "llm"
    assert parsed.provider_id == "provider"
    assert parsed.provider_resource_id == "model"
    assert parsed.metadata == {"extra": "value"}
    assert parsed.api_model_type == "llm"
    assert parsed.type == "model"


def test_parse_anthropic_model() -> None:
    """Anthropic models are normalized as LLM CatalogModel entries."""
    model = AnthropicListModelsResponseData.model_construct(
        id="claude-sonnet",
        created_at="2024-01-01T00:00:00Z",
        display_name="Claude Sonnet",
        max_input_tokens=200000,
        max_tokens=8192,
        type="model",
    )

    parsed = parse_anthropic_model(model)

    assert parsed.identifier == "claude-sonnet"
    assert parsed.model_type == "llm"
    assert parsed.provider_id == "anthropic"
    assert parsed.metadata["display_name"] == "Claude Sonnet"
    assert parsed.metadata["max_input_tokens"] == 200000
    assert parsed.metadata["max_tokens"] == 8192


def test_parse_google_model() -> None:
    """Google models are normalized as LLM CatalogModel entries."""
    model = GoogleListModelsResponseModel.model_construct(
        name="models/gemini-pro",
        display_name="Gemini Pro",
        description="A Gemini model",
    )

    parsed = parse_google_model(model)

    assert parsed.identifier == "models/gemini-pro"
    assert parsed.model_type == "llm"
    assert parsed.provider_id == "google"
    assert parsed.metadata["display_name"] == "Gemini Pro"
    assert parsed.metadata["description"] == "A Gemini model"


def test_parse_model_list_response_openai() -> None:
    """ListModelsResponse branch returns CatalogModel entries."""
    response = ListModelsResponse.model_construct(
        data=[
            Model.model_construct(
                id="p/m",
                created=1,
                owned_by="x",
                custom_metadata={"model_type": "embedding", "provider_id": "p"},
            )
        ]
    )

    parsed = parse_model_list_response(response)

    assert len(parsed) == 1
    assert parsed[0].identifier == "p/m"
    assert parsed[0].model_type == "embedding"


def test_parse_model_list_response_anthropic() -> None:
    """AnthropicListModelsResponse branch returns CatalogModel entries."""
    response = AnthropicListModelsResponse.model_construct(
        data=[
            AnthropicListModelsResponseData.model_construct(
                id="claude",
                created_at="2024-01-01T00:00:00Z",
                display_name="Claude",
            )
        ]
    )

    parsed = parse_model_list_response(response)

    assert len(parsed) == 1
    assert parsed[0].identifier == "claude"
    assert parsed[0].provider_id == "anthropic"


def test_parse_model_list_response_google() -> None:
    """GoogleListModelsResponse branch returns CatalogModel entries."""
    response = GoogleListModelsResponse.model_construct(
        models=[
            GoogleListModelsResponseModel.model_construct(
                name="models/gemini",
                display_name="Gemini",
            )
        ]
    )

    parsed = parse_model_list_response(response)

    assert len(parsed) == 1
    assert parsed[0].identifier == "models/gemini"
    assert parsed[0].provider_id == "google"


def test_parse_model_list_response_unsupported_type() -> None:
    """Unsupported response types yield an empty catalog list."""
    assert parse_model_list_response(object()) == []  # type: ignore[arg-type]
