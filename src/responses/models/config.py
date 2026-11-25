"""Prompt, text format, reasoning, usage, and error objects."""

from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, model_validator


class ResponseError(BaseModel):
    """Error returned when a response fails."""

    code: str
    message: str


class ResponsePrompt(BaseModel):
    """Stored prompt template and optional substitution values."""

    id: str
    variables: Optional[dict[str, str]] = None
    version: Optional[str] = None


class ResponseTextFormat(TypedDict, total=False):
    """How the model should format its text output."""

    type: Literal["text", "json_schema", "json_object"]
    name: str | None
    schema: dict[str, Any] | None
    description: str | None
    strict: bool | None


class ResponseText(BaseModel):
    """Text output format and verbosity."""

    format: Optional[ResponseTextFormat] = None
    verbosity: Optional[Literal["low", "medium", "high"]] = "medium"


class ResponseReasoning(BaseModel):
    """How much the model should reason, and whether to include a summary."""

    effort: Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh"]] = (
        None
    )
    summary: Optional[Literal["auto", "concise", "detailed"]] = None

    @model_validator(mode="before")
    @classmethod
    def accept_generate_summary(cls, data: Any) -> Any:
        """Map generate_summary onto summary when summary is omitted."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        generate_summary = values.pop("generate_summary", None)
        if values.get("summary") is None and generate_summary is not None:
            values["summary"] = generate_summary
        return values


class UsageOutputTokensDetails(BaseModel):
    """How output tokens were spent."""

    reasoning_tokens: int


class UsageInputTokensDetails(BaseModel):
    """How input tokens were spent."""

    cached_tokens: int


class ResponseUsage(BaseModel):
    """Token counts for a completed response."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: UsageInputTokensDetails
    output_tokens_details: UsageOutputTokensDetails


class IncompleteDetails(BaseModel):
    """Why a response stopped before it finished."""

    reason: str
