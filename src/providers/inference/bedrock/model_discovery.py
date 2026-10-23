"""Resolve invokable Bedrock model ids for catalog discovery.

Lists foundation models and system-defined inference profiles from the
control-plane API. For each foundation model, prefers the on-demand model
id when available; otherwise uses the first matching inference profile id.
Models that cannot be invoked are omitted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Optional

from botocore.client import BaseClient

from providers.inference.bedrock.specs import (
    FoundationModelSummary,
    InferenceProfileSummary,
)
from providers.inference.catalog import DiscoveredModel
from providers.inference.types import ModelType

FOUNDATION_MODEL_ARN_MARKER = "foundation-model/"
ON_DEMAND_INFERENCE_TYPE = "ON_DEMAND"
INFERENCE_PROFILE_INFERENCE_TYPE = "INFERENCE_PROFILE"


def list_foundation_models(client: BaseClient) -> list[FoundationModelSummary]:
    """Return foundation model summaries from the Bedrock control-plane client.

    Args:
        client: Bedrock control-plane client.

    Returns:
        Foundation model summaries used for discovery.

    """
    response = client.list_foundation_models()
    return [
        FoundationModelSummary.model_validate(summary)
        for summary in response.get("modelSummaries", [])
    ]


def list_inference_profiles(client: BaseClient) -> list[InferenceProfileSummary]:
    """Return system-defined inference profiles in API order.

    Args:
        client: Bedrock control-plane client.

    Returns:
        Inference profile summaries used for discovery.

    """
    paginator = client.get_paginator("list_inference_profiles")
    pages = paginator.paginate(typeEquals="SYSTEM_DEFINED")
    return [
        InferenceProfileSummary.model_validate(summary)
        for page in pages
        for summary in page.get("inferenceProfileSummaries", [])
    ]


def foundation_model_id_from_arn(model_arn: str) -> Optional[str]:
    """Extract the foundation model id from a Bedrock model ARN.

    Args:
        model_arn: Bedrock model ARN of the form
            arn:aws:bedrock:<region>::foundation-model/<modelId>.

    Returns:
        Foundation model id, or None when the ARN has no usable suffix.

    """
    _, marker, suffix = model_arn.partition(FOUNDATION_MODEL_ARN_MARKER)
    if not marker or not suffix:
        return None
    return suffix


def first_profile_id_by_foundation_model_id(
    profiles: Iterable[InferenceProfileSummary],
) -> dict[str, str]:
    """Map each foundation model id to the first matching inference profile id.

    Args:
        profiles: Inference profile summaries in API order.

    Returns:
        Foundation model id to first matching inference profile id.

    """
    mapping: dict[str, str] = {}
    for profile in profiles:
        for model in profile.models:
            foundation_model_id = foundation_model_id_from_arn(model.model_arn)
            if foundation_model_id is None or foundation_model_id in mapping:
                continue
            mapping[foundation_model_id] = profile.inference_profile_id
    return mapping


def invokable_model_id(
    model: FoundationModelSummary,
    profile_ids_by_foundation_id: Mapping[str, str],
) -> Optional[str]:
    """Return an invokable model id, or None when the model cannot be called.

    Prefers the foundation model id for on-demand inference. Falls back to a
    matching inference profile id when the model requires a profile.

    Args:
        model: Foundation model summary from discovery.
        profile_ids_by_foundation_id: First profile id per foundation model id.

    Returns:
        Invokable model id, or None when the model should be dropped.

    """
    inference_types = model.inference_types_supported
    if not inference_types:
        return None
    if ON_DEMAND_INFERENCE_TYPE in inference_types:
        return model.model_id
    if INFERENCE_PROFILE_INFERENCE_TYPE not in inference_types:
        return None
    return profile_ids_by_foundation_id.get(model.model_id)


def to_discovered_model(
    model: FoundationModelSummary,
    profile_ids_by_foundation_id: Mapping[str, str],
    model_type: Optional[ModelType],
) -> Optional[DiscoveredModel]:
    """Return a discovered catalog model when type and invokable id are known.

    Args:
        model: Foundation model summary from discovery.
        profile_ids_by_foundation_id: First profile id per foundation model id.
        model_type: Inferred catalog type, or None to drop the model.

    Returns:
        Discovered model with an invokable id, or None when it cannot be used.

    """
    if model_type is None:
        return None
    provider_model_id = invokable_model_id(model, profile_ids_by_foundation_id)
    if provider_model_id is None:
        return None
    return DiscoveredModel(
        provider_model_id=provider_model_id,
        model_type=model_type,
    )
