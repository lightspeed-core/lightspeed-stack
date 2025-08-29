"""Metrics module for Lightspeed Stack."""

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
    "ls_llm_calls_total", "LLM calls counter", ["provider", "model"]
)

# Metric that counts how many LLM calls failed
llm_calls_failures_total = Counter("ls_llm_calls_failures_total", "LLM calls failures")

# Metric that counts how many LLM calls had validation errors
llm_calls_validation_errors_total = Counter(
    "ls_llm_validation_errors_total", "LLM validation errors"
)

# TODO(lucasagomes): Add metric for token usage
# https://issues.redhat.com/browse/LCORE-411
llm_token_sent_total = Counter(
    "ls_llm_token_sent_total", "LLM tokens sent", ["provider", "model"]
)

# TODO(lucasagomes): Add metric for token usage
# https://issues.redhat.com/browse/LCORE-411
llm_token_received_total = Counter(
    "ls_llm_token_received_total", "LLM tokens received", ["provider", "model"]
)
