"""Wire models for Bedrock discovery API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FoundationModelSummary(BaseModel):
    """Subset of a Bedrock modelSummary used for discovery."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    model_id: str = Field(alias="modelId")
    output_modalities: list[str] = Field(
        default_factory=list,
        alias="outputModalities",
    )
    inference_types_supported: list[str] = Field(
        default_factory=list,
        alias="inferenceTypesSupported",
    )


class InferenceProfileModel(BaseModel):
    """Foundation model referenced by an inference profile."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    model_arn: str = Field(alias="modelArn")


class InferenceProfileSummary(BaseModel):
    """Subset of a Bedrock inferenceProfileSummary used for discovery."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    inference_profile_id: str = Field(alias="inferenceProfileId")
    models: list[InferenceProfileModel] = Field(default_factory=list)
