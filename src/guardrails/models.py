"""Data models for the LCS-native prompt guardrails PoC (LCORE-2657 spike)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, PositiveFloat

# A guardrail point is the place in the request lifecycle where a rule runs:
# - "input": the raw user prompt, before the LLM call
# - "output": the generated answer, before it is returned to the client
# - "tool_content": content returned by tools (MCP/RAG) entering the context
GuardrailPoint = Literal["input", "output", "tool_content"]


def _default_points() -> list[GuardrailPoint]:
    """Return the default guardrail points for a rule."""
    return ["input"]


class GuardrailRule(BaseModel):
    """A single guardrail rule bound to one or more guardrail points."""

    name: str = Field(description="Human-readable rule identifier.")
    risk: str = Field(
        default="harm",
        description="Guardian risk id (e.g. 'harm', 'jailbreak') or a label "
        "for a custom risk when 'definition' is provided.",
    )
    definition: Optional[str] = Field(
        default=None,
        description="Custom risk definition text (bring-your-own-criteria). "
        "When set, it is sent to the guardian model instead of the "
        "out-of-the-box risk id.",
    )
    points: list[GuardrailPoint] = Field(
        default_factory=_default_points,
        description="Lifecycle points at which this rule runs.",
    )
    blocking: bool = Field(
        default=True,
        description="Whether a flagged result blocks the request (True) or "
        "is only recorded as advisory (False).",
    )


class GuardianDetectorConfig(BaseModel):
    """Connection settings for the guardian model endpoint."""

    url: str = Field(
        description="Base URL of an OpenAI-compatible endpoint serving the "
        "guardian model (e.g. an Ollama or vLLM server)."
    )
    model: str = Field(description="Guardian model identifier at the endpoint.")
    api_key: str = Field(
        default="unused",
        description="API key for the endpoint; local servers ignore it.",
    )
    timeout_seconds: PositiveFloat = Field(
        default=30.0, description="Per-inference timeout."
    )


class GuardrailsPocConfig(BaseModel):
    """Top-level PoC configuration: one detector plus a list of rules."""

    detector: GuardianDetectorConfig
    rules: list[GuardrailRule] = Field(default_factory=list)
    violation_message: str = Field(
        default="I cannot process this request due to policy restrictions.",
        description="Message returned to the client when a blocking rule "
        "flags the content.",
    )


class DetectionResult(BaseModel):
    """Outcome of running one rule against one piece of content."""

    rule_name: str
    flagged: bool
    blocking: bool
    raw_response: str = Field(
        description="Verbatim guardian model output (expected 'Yes'/'No')."
    )
    latency_ms: float


class GuardrailsVerdict(BaseModel):
    """Aggregated outcome of all rules that ran at one guardrail point."""

    blocked: bool
    results: list[DetectionResult] = Field(default_factory=list)
    message: Optional[str] = Field(
        default=None,
        description="Violation message when blocked; None otherwise.",
    )
