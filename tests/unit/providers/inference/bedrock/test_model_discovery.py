"""Unit tests for Bedrock invokable-id resolution."""

from typing import Any, Optional

import pytest

from providers.inference.bedrock.model_discovery import (
    first_profile_id_by_foundation_model_id,
    foundation_model_id_from_arn,
    invokable_model_id,
    list_foundation_models,
    list_inference_profiles,
    to_discovered_model,
)
from providers.inference.bedrock.specs import (
    FoundationModelSummary,
    InferenceProfileSummary,
)
from providers.inference.types import ModelType


def _foundation(
    model_id: str,
    *,
    inference_types: list[str],
    modalities: Optional[list[str]] = None,
) -> FoundationModelSummary:
    """Build a foundation summary for resolution tests."""
    return FoundationModelSummary.model_validate(
        {
            "modelId": model_id,
            "outputModalities": modalities or ["TEXT"],
            "inferenceTypesSupported": inference_types,
        }
    )


def _profile(
    profile_id: str,
    *foundation_model_ids: str,
) -> InferenceProfileSummary:
    """Build a profile summary with ARNs for the given model ids."""
    return InferenceProfileSummary.model_validate(
        {
            "inferenceProfileId": profile_id,
            "models": [
                {
                    "modelArn": (
                        f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}"
                    )
                }
                for model_id in foundation_model_ids
            ],
        }
    )


def test_list_foundation_models_parses_summaries(mocker: Any) -> None:
    """Parses foundation model summaries from the control-plane response."""
    client = mocker.MagicMock()
    client.list_foundation_models.return_value = {
        "modelSummaries": [
            {
                "modelId": "amazon.titan-embed-text-v2:0",
                "outputModalities": ["EMBEDDING"],
                "inferenceTypesSupported": ["ON_DEMAND"],
            }
        ]
    }

    models = list_foundation_models(client)

    assert len(models) == 1
    assert models[0].model_id == "amazon.titan-embed-text-v2:0"
    client.list_foundation_models.assert_called_once_with()


def test_list_inference_profiles_paginates_system_defined(mocker: Any) -> None:
    """Collects system-defined profiles across pages in API order."""
    client = mocker.MagicMock()
    paginator = mocker.MagicMock()
    paginator.paginate.return_value = [
        {
            "inferenceProfileSummaries": [
                {
                    "inferenceProfileId": "us.openai.gpt-6-astra",
                    "models": [
                        {
                            "modelArn": (
                                "arn:aws:bedrock:us-east-1::foundation-model/"
                                "openai.gpt-6-astra"
                            )
                        }
                    ],
                }
            ]
        },
        {
            "inferenceProfileSummaries": [
                {"inferenceProfileId": "us.amazon.nova-pro-v1:0", "models": []}
            ]
        },
    ]
    client.get_paginator.return_value = paginator

    profiles = list_inference_profiles(client)

    assert [profile.inference_profile_id for profile in profiles] == [
        "us.openai.gpt-6-astra",
        "us.amazon.nova-pro-v1:0",
    ]
    client.get_paginator.assert_called_once_with("list_inference_profiles")
    paginator.paginate.assert_called_once_with(typeEquals="SYSTEM_DEFINED")


@pytest.mark.parametrize(
    ("model_arn", "expected"),
    [
        (
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
            "amazon.nova-pro-v1:0",
        ),
        (
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0:300k",
            "amazon.nova-pro-v1:0:300k",
        ),
        ("arn:aws:bedrock:us-east-1::other/foo", None),
        ("arn:aws:bedrock:us-east-1::foundation-model/", None),
        ("", None),
    ],
    ids=[
        "standard-model-id",
        "model-id-with-suffix",
        "wrong-arn-resource",
        "empty-suffix",
        "empty-arn",
    ],
)
def test_foundation_model_id_from_arn(
    model_arn: str,
    expected: Optional[str],
) -> None:
    """Extracts the foundation model id when the ARN marker is present."""
    assert foundation_model_id_from_arn(model_arn) == expected


def test_first_profile_id_keeps_first_match_by_exact_suffix() -> None:
    """Keeps the first profile for each exact foundation model id."""
    mapping = first_profile_id_by_foundation_model_id(
        [
            _profile("us.amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0"),
            _profile("eu.amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0"),
            _profile(
                "us.amazon.nova-pro-v1:0:300k",
                "amazon.nova-pro-v1:0:300k",
            ),
        ]
    )

    assert mapping == {
        "amazon.nova-pro-v1:0": "us.amazon.nova-pro-v1:0",
        "amazon.nova-pro-v1:0:300k": "us.amazon.nova-pro-v1:0:300k",
    }


def test_first_profile_id_indexes_multiple_models_and_skips_bad_arns() -> None:
    """Indexes usable model ARNs on a profile and ignores malformed ones."""
    profiles = [
        InferenceProfileSummary.model_validate(
            {
                "inferenceProfileId": "us.multi",
                "models": [
                    {
                        "modelArn": (
                            "arn:aws:bedrock:us-east-1::foundation-model/"
                            "openai.gpt-6-astra"
                        )
                    },
                    {"modelArn": "arn:aws:bedrock:us-east-1::other/foo"},
                    {
                        "modelArn": (
                            "arn:aws:bedrock:us-east-1::foundation-model/"
                            "anthropic.claude-sonnet-4-5-20250929-v1:0"
                        )
                    },
                ],
            }
        ),
        _profile("us.empty"),
    ]

    assert first_profile_id_by_foundation_model_id(profiles) == {
        "openai.gpt-6-astra": "us.multi",
        "anthropic.claude-sonnet-4-5-20250929-v1:0": "us.multi",
    }


@pytest.mark.parametrize(
    ("model_id", "inference_types", "profile_ids", "expected"),
    [
        (
            "nvidia.nemotron-nano-12b-v2",
            ["ON_DEMAND"],
            {},
            "nvidia.nemotron-nano-12b-v2",
        ),
        (
            "amazon.nova-pro-v1:0",
            ["ON_DEMAND", "INFERENCE_PROFILE"],
            {"amazon.nova-pro-v1:0": "us.amazon.nova-pro-v1:0"},
            "amazon.nova-pro-v1:0",
        ),
        (
            "openai.gpt-6-astra",
            ["INFERENCE_PROFILE"],
            {"openai.gpt-6-astra": "us.openai.gpt-6-astra"},
            "us.openai.gpt-6-astra",
        ),
        ("openai.gpt-6-astra", ["INFERENCE_PROFILE"], {}, None),
        (
            "amazon.nova-pro-v1:0:300k",
            ["INFERENCE_PROFILE"],
            {"amazon.nova-pro-v1:0": "us.amazon.nova-pro-v1:0"},
            None,
        ),
        ("amazon.nova-pro-v1:0", ["PROVISIONED"], {}, None),
        ("amazon.titan-embed-text-v2:0:8k", [], {}, None),
    ],
    ids=[
        "on-demand",
        "prefer-on-demand-over-profile",
        "profile-only-with-match",
        "profile-only-without-match",
        "profile-match-must-be-exact",
        "provisioned-only",
        "no-inference-types",
    ],
)
def test_invokable_model_id(
    model_id: str,
    inference_types: list[str],
    profile_ids: dict[str, str],
    expected: Optional[str],
) -> None:
    """Resolves an invokable id or rejects unsupported models."""
    model = _foundation(model_id, inference_types=inference_types)

    assert invokable_model_id(model, profile_ids) == expected


def test_to_discovered_model_builds_row() -> None:
    """Builds a discovered row when type and invokable id are present."""
    model = _foundation(
        "nvidia.nemotron-nano-12b-v2",
        inference_types=["ON_DEMAND"],
    )

    discovered = to_discovered_model(model, {}, "llm")

    assert discovered is not None
    assert discovered.provider_model_id == "nvidia.nemotron-nano-12b-v2"
    assert discovered.model_type == "llm"


@pytest.mark.parametrize(
    ("inference_types", "model_type", "profile_ids"),
    [
        (["ON_DEMAND"], None, {}),
        (["INFERENCE_PROFILE"], "llm", {}),
    ],
    ids=["missing-model-type", "missing-invokable-id"],
)
def test_to_discovered_model_skips_unusable(
    inference_types: list[str],
    model_type: Optional[ModelType],
    profile_ids: dict[str, str],
) -> None:
    """Drops models without a type or a usable invokable id."""
    model = _foundation("openai.gpt-6-astra", inference_types=inference_types)

    assert to_discovered_model(model, profile_ids, model_type) is None
