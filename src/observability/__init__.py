"""Observability module for telemetry and event collection.

This module provides functionality for sending telemetry events to external
systems like Splunk HEC for monitoring and analytics.

The splunk module provides a format-agnostic send_splunk_event() function.
Event formats are in the formats subpackage - see formats.rlsapi for the
default implementation, or create your own format module.
"""

from observability.formats import (
    InferenceEventData,
    ResponsesEventData,
    build_inference_event,
    build_responses_event,
)
from observability.splunk import dispatch_splunk_event, send_splunk_event

__all__ = [
    "InferenceEventData",
    "build_inference_event",
    "ResponsesEventData",
    "build_responses_event",
    "dispatch_splunk_event",
    "send_splunk_event",
]
