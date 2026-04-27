"""Event format builders for Splunk telemetry.

Each submodule provides format-specific event builders. The rlsapi module
provides the default format matching Red Hat's rlsapi v1 specification.
"""

from observability.formats.responses import ResponsesEventData, build_responses_event
from observability.formats.rlsapi import InferenceEventData, build_inference_event

__all__ = [
    "InferenceEventData",
    "build_inference_event",
    "ResponsesEventData",
    "build_responses_event",
]
