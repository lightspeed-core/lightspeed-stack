"""Metrics module for Lightspeed Core Stack."""

from typing import Final

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
)

LLM_INFERENCE_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.1,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    20.0,
    30.0,
    60.0,
    120.0,
    float("inf"),
)

AUTH_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    float("inf"),
)
# Counter to track REST API calls
# This will be used to count how many times each API endpoint is called
# and the status code of the response
rest_api_calls_total = Counter(
    "ls_rest_api_calls_total", "REST API calls counter", ["path", "status_code"]
)

# Histogram to measure response durations
# This will be used to track how long it takes to handle requests
response_duration_seconds = Histogram(
    "ls_response_duration_seconds", "Response durations", ["path"]
)

# Metric that indicates what provider + model customers are using so we can
# understand what is popular/important
provider_model_configuration = Gauge(
    "ls_provider_model_configuration",
    "LLM provider/models combinations defined in configuration",
    ["provider", "model"],
)

# Metric that counts how many LLM calls were made for each provider + model
llm_calls_total = Counter(
    "ls_llm_calls_total", "LLM calls counter", ["provider", "model", "endpoint"]
)

# Metric that counts how many LLM calls failed
llm_calls_failures_total = Counter(
    "ls_llm_calls_failures_total",
    "LLM calls failures",
    ["provider", "model", "endpoint"],
)

# Metric that counts how many LLM calls had validation errors
llm_calls_validation_errors_total = Counter(
    "ls_llm_validation_errors_total", "LLM validation errors", ["endpoint"]
)

# Metric that counts how many tokens were sent to LLMs
llm_token_sent_total = Counter(
    "ls_llm_token_sent_total", "LLM tokens sent", ["provider", "model", "endpoint"]
)

# Metric that counts how many tokens were received from LLMs
llm_token_received_total = Counter(
    "ls_llm_token_received_total",
    "LLM tokens received",
    ["provider", "model", "endpoint"],
)


# Histogram to measure the latency of direct LLM inference backend calls.
llm_inference_duration_seconds: Final[Histogram] = Histogram(
    "ls_llm_inference_duration_seconds",
    "LLM inference call duration",
    ["provider", "model", "endpoint", "result"],
    buckets=LLM_INFERENCE_DURATION_BUCKETS,
)

# Counter to track authentication attempts with bounded auth_module, result, and reason labels.
auth_attempts_total: Final[Counter] = Counter(
    "ls_auth_attempts_total",
    "Authentication attempts",
    ["auth_module", "result", "reason"],
)

# Histogram to measure authentication dependency latency with bounded module and result labels.
auth_duration_seconds: Final[Histogram] = Histogram(
    "ls_auth_duration_seconds",
    "Authentication duration",
    ["auth_module", "result"],
    buckets=AUTH_DURATION_BUCKETS,
)
