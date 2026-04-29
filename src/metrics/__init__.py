"""Metrics module for Lightspeed Core Stack."""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
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

# Counter to track authentication attempts by configured authentication module.
auth_attempts_total = Counter(
    "ls_auth_attempts_total",
    "Authentication attempts",
    ["auth_module", "result", "reason"],
)

# Histogram to measure authentication dependency latency.
auth_duration_seconds = Histogram(
    "ls_auth_duration_seconds",
    "Authentication duration",
    ["auth_module", "result"],
)

# Counter to track authorization checks by protected action.
authorization_checks_total = Counter(
    "ls_authorization_checks_total",
    "Authorization checks",
    ["action", "result"],
)

# Histogram to measure authorization check latency by protected action.
authorization_duration_seconds = Histogram(
    "ls_authorization_duration_seconds",
    "Authorization check duration",
    ["action", "result"],
)

# Counter to track pre-request quota checks by bounded quota category.
quota_checks_total = Counter(
    "ls_quota_checks_total",
    "Quota availability checks",
    ["endpoint", "quota_type", "result"],
)

# Histogram to measure quota availability check latency by bounded quota category.
quota_check_duration_seconds = Histogram(
    "ls_quota_check_duration_seconds",
    "Quota availability check duration",
    ["endpoint", "quota_type", "result"],
)

# Histogram to measure the latency of direct LLM inference backend calls.
llm_inference_duration_seconds = Histogram(
    "ls_llm_inference_duration_seconds",
    "LLM inference call duration",
    ["provider", "model", "endpoint", "result"],
)
