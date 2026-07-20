"""LCS-native prompt guardrails PoC (LCORE-2657 spike).

Proof-of-concept for the "Prompt Guardrails" feature (LCORE-230): a
guardrails layer owned by lightspeed-stack that invokes a guardian model
(Granite Guardian) through any OpenAI-compatible endpoint, independently
of Llama Stack's Safety API.

PoC only — activated exclusively via the ``LCS_GUARDRAILS_POC_CONFIG``
environment variable; removed before the spike PR merges.
"""

from guardrails.models import (
    DetectionResult,
    GuardianDetectorConfig,
    GuardrailPoint,
    GuardrailRule,
    GuardrailsPocConfig,
    GuardrailsVerdict,
)

__all__ = [
    "DetectionResult",
    "GuardianDetectorConfig",
    "GuardrailPoint",
    "GuardrailRule",
    "GuardrailsPocConfig",
    "GuardrailsVerdict",
]
