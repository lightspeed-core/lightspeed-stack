"""Helpers for normalizing OGX ``models.list()`` union responses."""

from typing import Any

from ogx_client.types import ListModelsResponse
from ogx_client.types.model import Model
from ogx_client.types.model_list_response import (
    AnthropicListModelsResponse,
    AnthropicListModelsResponseData,
    GoogleListModelsResponse,
    GoogleListModelsResponseModel,
    ModelListResponse,
)

from models.common.models import CatalogModel


def parse_openai_style_model(model: Model) -> CatalogModel:
    """
    Parse an OpenAI-style OGX ``Model`` into a unified catalog model.

    Uses the OGX ``Model`` properties for identifier, model_type, provider
    fields, and filtered metadata.

    Parameters:
        model: Model object from ``ListModelsResponse.data``.

    Returns:
        CatalogModel: Normalized catalog entry.
    """
    model_type = model.model_type or "unknown"

    return CatalogModel(
        identifier=model.identifier,
        metadata=model.metadata or {},
        api_model_type=model_type,
        provider_id=model.provider_id or "",
        type=model.object or "model",
        provider_resource_id=model.provider_resource_id or "",
        model_type=model_type,
    )


def parse_anthropic_model(model: AnthropicListModelsResponseData) -> CatalogModel:
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


def parse_google_model(model: GoogleListModelsResponseModel) -> CatalogModel:
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


def parse_model_list_response(response: ModelListResponse) -> list[CatalogModel]:
    """Normalize an OGX ``models.list()`` union response into catalog models.

    OGX returns one of ``ListModelsResponse``, ``AnthropicListModelsResponse``,
    or ``GoogleListModelsResponse``. This helper matches on the concrete type
    and parses every entry into :class:`CatalogModel`.

    Parameters:
        response: The union response returned by ``client.models.list()``.

    Returns:
        list[CatalogModel]: Parsed models in the unified catalog shape.
    """
    match response:
        case ListModelsResponse(data=data):
            return [parse_openai_style_model(model) for model in data]
        case AnthropicListModelsResponse(data=data):
            return [parse_anthropic_model(model) for model in data]
        case GoogleListModelsResponse(models=models):
            return [parse_google_model(model) for model in models]
        case _:
            return []
