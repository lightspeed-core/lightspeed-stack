"""Granite Guardian detector for the prompt guardrails PoC (LCORE-2657 spike).

Invokes a Granite Guardian model served behind any OpenAI-compatible
endpoint (Ollama, vLLM, ...). The guardian is a generative classifier:
the risk to check is selected through the system message and the model
answers "Yes" (risk present) or "No" (risk absent).

All checks for a guardrail point run concurrently, mirroring the Ask Red
Hat production pattern (Granite Guardian does not support batched
requests).
"""

import asyncio
import time

from openai import AsyncOpenAI, OpenAIError

from guardrails.models import (
    DetectionResult,
    GuardrailPoint,
    GuardrailRule,
    GuardrailsPocConfig,
    GuardrailsVerdict,
)
from log import get_logger

logger = get_logger(__name__)


def _guardian_system_prompt(rule: GuardrailRule) -> str:
    """Build the system prompt selecting the risk for the guardian model.

    Parameters:
    ----------
        rule: The guardrail rule to build the prompt for.

    Returns:
    -------
        str: The custom risk definition when present, else the risk id.
    """
    return rule.definition if rule.definition is not None else rule.risk


def _is_flagged(raw_response: str) -> bool:
    """Interpret the guardian model's verdict text.

    Parameters:
    ----------
        raw_response: Verbatim model output; "Yes" means the risk is present.

    Returns:
    -------
        bool: True when the model flags the content.
    """
    return raw_response.strip().lower().startswith("yes")


def _rules_for_point(
    config: GuardrailsPocConfig, point: GuardrailPoint
) -> list[GuardrailRule]:
    """Select the rules configured to run at the given guardrail point.

    Parameters:
    ----------
        config: The PoC guardrails configuration.
        point: The lifecycle point being evaluated.

    Returns:
    -------
        list[GuardrailRule]: Rules whose 'points' include the given point.
    """
    return [rule for rule in config.rules if point in rule.points]


async def check_rule(
    client: AsyncOpenAI,
    model: str,
    rule: GuardrailRule,
    content: str,
    on_detector_error: str = "block",
) -> DetectionResult:
    """Run a single guardrail rule against content via the guardian model.

    A detector failure (timeout, unreachable endpoint, API error) does not
    propagate: it resolves per the configured error posture (Decision T6),
    defaulting to fail-closed so an unavailable guardian blocks rather than
    silently disabling protection.

    Parameters:
    ----------
        client: OpenAI-compatible client pointed at the guardian endpoint.
        model: Guardian model identifier.
        rule: The rule to evaluate.
        content: The text to classify.
        on_detector_error: "block" (fail closed) or "allow" (fail open).

    Returns:
    -------
        DetectionResult: The rule outcome including the raw model verdict.
    """
    started = time.monotonic()
    try:
        completion = await client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _guardian_system_prompt(rule)},
                {"role": "user", "content": content},
            ],
        )
        raw = (
            (completion.choices[0].message.content or "") if completion.choices else ""
        )
        flagged = _is_flagged(raw)
    except (OpenAIError, asyncio.TimeoutError) as exc:
        fail_closed = on_detector_error == "block"
        logger.error(
            "Guardian detector call failed for rule '%s': %s — failing %s",
            rule.name,
            exc,
            "closed (blocking)" if fail_closed else "open (allowing)",
        )
        raw = f"<detector-error: {type(exc).__name__}>"
        flagged = fail_closed

    latency_ms = (time.monotonic() - started) * 1000
    return DetectionResult(
        rule_name=rule.name,
        flagged=flagged,
        blocking=rule.blocking,
        raw_response=raw,
        latency_ms=latency_ms,
    )


async def run_point(
    config: GuardrailsPocConfig,
    point: GuardrailPoint,
    content: str,
) -> GuardrailsVerdict:
    """Run all rules configured for a guardrail point, concurrently.

    Parameters:
    ----------
        config: The PoC guardrails configuration.
        point: The lifecycle point being evaluated.
        content: The text to classify.

    Returns:
    -------
        GuardrailsVerdict: Aggregated outcome; 'blocked' is True when at
        least one blocking rule flagged the content.
    """
    rules = _rules_for_point(config, point)
    if not rules:
        return GuardrailsVerdict(blocked=False)

    client = AsyncOpenAI(
        base_url=config.detector.url,
        api_key=config.detector.api_key.get_secret_value(),
        timeout=config.detector.timeout_seconds,
    )
    results = await asyncio.gather(
        *(
            check_rule(
                client,
                config.detector.model,
                rule,
                content,
                config.on_detector_error,
            )
            for rule in rules
        )
    )
    for result in results:
        logger.info(
            "Guardrail rule '%s' at point '%s': flagged=%s (%.0f ms, raw=%r)",
            result.rule_name,
            point,
            result.flagged,
            result.latency_ms,
            result.raw_response,
        )
    blocked = any(result.flagged and result.blocking for result in results)
    return GuardrailsVerdict(
        blocked=blocked,
        results=list(results),
        message=config.violation_message if blocked else None,
    )
