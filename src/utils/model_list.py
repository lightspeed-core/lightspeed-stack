"""Helpers for normalizing OGX ``models.list()`` union responses."""

from typing import Any

from ogx_client.models.anthropic_list_models_response import AnthropicListModelsResponse
from ogx_client.models.anthropic_model_info import AnthropicModelInfo
from ogx_client.models.google_list_models_response import GoogleListModelsResponse
from ogx_client.models.google_model_info import GoogleModelInfo
from ogx_client.models.list_models_v1_models_get200_response import (
    ListModelsV1ModelsGet200Response,
)
from ogx_client.models.open_ai_list_models_response import OpenAIListModelsResponse
from ogx_client.models.open_ai_model import OpenAIModel

from models.common.models import CatalogModel


def parse_openai_style_model(model: OpenAIModel) -> CatalogModel:
    """
    Parse an OpenAI-style OGX ``OpenAIModel`` into a unified catalog model.

    Reads ``id`` / ``object`` from the model and pulls ``model_type``,
    ``provider_id``, and ``provider_resource_id`` from ``custom_metadata``.
    Remaining custom metadata becomes ``CatalogModel.metadata``.

    Parameters:
        model: Model object from ``OpenAIListModelsResponse.data``.

    Returns:
        CatalogModel: Normalized catalog entry.
    """
    custom_metadata = dict(model.custom_metadata or {})
    model_type = custom_metadata.pop("model_type", None) or "unknown"
    provider_id = custom_metadata.pop("provider_id", "") or ""
    provider_resource_id = custom_metadata.pop("provider_resource_id", "") or ""

    return CatalogModel(
        identifier=model.id,
        metadata=custom_metadata,
        api_model_type=model_type,
        provider_id=provider_id,
        type=model.object or "model",
        provider_resource_id=provider_resource_id,
        model_type=model_type,
    )


def parse_anthropic_model(model: AnthropicModelInfo) -> CatalogModel:
    """Parse an Anthropic model list entry into a unified catalog model.

    Parameters:
        model: Anthropic model object from ``AnthropicListModelsResponse.data``.

    Returns:
        CatalogModel: Normalized catalog entry. Treated as an LLM.
    """
    metadata: dict[str, Any] = {
        "display_name": model.display_name,
        "created_at": model.created_at,
    }
    if model.max_input_tokens is not None:
        metadata["max_input_tokens"] = model.max_input_tokens
    if model.max_tokens is not None:
        metadata["max_tokens"] = model.max_tokens

    return CatalogModel(
        identifier=model.id,
        metadata=metadata,
        api_model_type="llm",
        provider_id="anthropic",
        type=model.type or "model",
        provider_resource_id=model.id,
        model_type="llm",
    )


def parse_google_model(model: GoogleModelInfo) -> CatalogModel:
    """Parse a Google model list entry into a unified catalog model.

    Parameters:
        model: Google model object from ``GoogleListModelsResponse.models``.

    Returns:
        CatalogModel: Normalized catalog entry. Treated as an LLM.
    """
    metadata: dict[str, Any] = {
        "display_name": model.display_name,
    }
    if model.description is not None:
        metadata["description"] = model.description

    return CatalogModel(
        identifier=model.name,
        metadata=metadata,
        api_model_type="llm",
        provider_id="google",
        type="model",
        provider_resource_id=model.name,
        model_type="llm",
    )


def parse_model_list_response(
    response: ListModelsV1ModelsGet200Response,
) -> list[CatalogModel]:
    """Normalize an OGX ``models.list()`` response into catalog models.

    Parameters:
        response: The response returned by ``client.models.list()``.

    Returns:
        list[CatalogModel]: Parsed models in the unified catalog shape.
    """
    match response.actual_instance:
        case OpenAIListModelsResponse(data=data):
            return [parse_openai_style_model(model) for model in data]
        case AnthropicListModelsResponse(data=data):
            return [parse_anthropic_model(model) for model in data]
        case GoogleListModelsResponse(models=models):
            return [parse_google_model(model) for model in models]
        case _:
            return []
