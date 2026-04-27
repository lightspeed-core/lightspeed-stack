"""Event builders for Responses API Splunk format.

This module provides event builders specific to the Responses API telemetry format.
To implement a custom format, create a new module in this package with your own
event builder function that returns a dict, then pass the result to send_splunk_event().
"""

from dataclasses import dataclass
from typing import Any

from configuration import configuration


@dataclass
class ResponsesEventData:  # pylint: disable=too-many-instance-attributes
    """Data required to build a responses telemetry event."""

    input_text: str
    response_text: str
    conversation_id: str
    model: str
    org_id: str
    system_id: str
    inference_time: float
    input_tokens: int = 0
    output_tokens: int = 0


def build_responses_event(data: ResponsesEventData) -> dict[str, Any]:
    """Build a responses telemetry event payload matching responses format.

    Args:
        data: The responses event data.

    Returns:
        A dictionary matching the responses Splunk event format.
    """
    return {
        "input_text": data.input_text,
        "response_text": data.response_text,
        "conversation_id": data.conversation_id,
        "inference_time": data.inference_time,
        "model": data.model,
        "deployment": configuration.deployment_environment,
        "org_id": data.org_id,
        "system_id": data.system_id,
        "total_llm_tokens": data.input_tokens + data.output_tokens,
    }
