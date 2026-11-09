"""Unit tests for Bedrock discovery wire specs."""

from providers.inference.bedrock.specs import (
    FoundationModelSummary,
    InferenceProfileSummary,
)


def test_foundation_model_summary_parses_wire_fields() -> None:
    """Maps camelCase Bedrock fields and ignores unknown extras."""
    model = FoundationModelSummary.model_validate(
        {
            "modelId": "amazon.titan-embed-text-v2:0",
            "outputModalities": ["EMBEDDING"],
            "inferenceTypesSupported": ["ON_DEMAND"],
            "providerName": "Amazon",
        }
    )

    assert model.model_id == "amazon.titan-embed-text-v2:0"
    assert model.output_modalities == ["EMBEDDING"]
    assert model.inference_types_supported == ["ON_DEMAND"]

    bare = FoundationModelSummary.model_validate(
        {"modelId": "stability.stable-diffusion-xl-v1"}
    )
    assert bare.output_modalities == []
    assert bare.inference_types_supported == []


def test_inference_profile_summary_parses_wire_fields() -> None:
    """Maps camelCase profile fields and ignores unknown extras."""
    profile = InferenceProfileSummary.model_validate(
        {
            "inferenceProfileId": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "inferenceProfileName": "US Anthropic Claude Sonnet 4.5",
            "type": "SYSTEM_DEFINED",
            "models": [
                {
                    "modelArn": (
                        "arn:aws:bedrock:us-east-1::foundation-model/"
                        "anthropic.claude-sonnet-4-5-20250929-v1:0"
                    )
                }
            ],
        }
    )

    assert profile.inference_profile_id == (
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    assert profile.models[0].model_arn.endswith(
        "anthropic.claude-sonnet-4-5-20250929-v1:0"
    )

    empty = InferenceProfileSummary.model_validate(
        {"inferenceProfileId": "us.amazon.nova-pro-v1:0"}
    )
    assert empty.models == []
