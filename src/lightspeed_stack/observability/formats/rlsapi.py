"""Event builders for rlsapi v1 Splunk format.

This module provides event builders specific to the rlsapi v1 telemetry format.
To implement a custom format, create a new module in this package with your own
event builder function that returns a dict, then pass the result to send_splunk_event().
"""

from dataclasses import dataclass
from typing import Any

from configuration import configuration


@dataclass
class InferenceEventData:  # pylint: disable=too-many-instance-attributes
    """Data required to build an inference telemetry event."""

    question: str
    response: str
    inference_time: float
    model: str
    org_id: str
    system_id: str
    request_id: str
    cla_version: str
    system_os: str
    system_version: str
    system_arch: str
    input_tokens: int = 0
    output_tokens: int = 0


def build_inference_event(data: InferenceEventData) -> dict[str, Any]:
    """Build an inference telemetry event payload matching rlsapi format.

    Args:
        data: The inference event data.

    Returns:
        A dictionary matching the rlsapi Splunk event format.
    """
    return {
        "question": data.question,
        "refined_questions": [],
        "context": "",
        "response": data.response,
        "inference_time": data.inference_time,
        "model": data.model,
        "deployment": configuration.deployment_environment,
        "org_id": data.org_id,
        "system_id": data.system_id,
        "total_llm_tokens": data.input_tokens + data.output_tokens,
        "request_id": data.request_id,
        "cla_version": data.cla_version,
        "system_os": data.system_os,
        "system_version": data.system_version,
        "system_arch": data.system_arch,
    }
