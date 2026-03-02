"""Step definitions for token counter validation."""

import json

from typing import Optional

import requests
from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

DEFAULT_TIMEOUT = 10


@then("The response should contain token counter fields")
def check_token_counter_fields(context: Context) -> None:
    """Check that response contains input_tokens and output_tokens fields."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = context.response.json()

    input_tokens = response_json.get("input_tokens")
    output_tokens = response_json.get("output_tokens")
    assert (
        "input_tokens" in response_json
    ), f"Response should contain 'input_tokens' field. Got: {response_json}"
    assert (
        "output_tokens" in response_json
    ), f"Response should contain 'output_tokens' field. Got: {response_json}"
    assert (
        "available_quotas" in response_json
    ), f"Response should contain 'available_quotas' field. Got: {response_json}"
    assert input_tokens >= 0, f"input_tokens should be non-negative, got {input_tokens}"
    assert (
        output_tokens >= 0
    ), f"output_tokens should be non-negative, got {output_tokens}"


@given("I capture the current token metrics")
def capture_token_metrics(context: Context) -> None:
    """Capture the current Prometheus token metrics values.

    Stores the metrics in context.initial_token_metrics for later comparison.
    """
    context.initial_token_metrics = _get_current_token_metrics(context)
    print(f"Initial token metrics: {context.initial_token_metrics}")


@then("The token metrics should have increased")
def check_token_metrics_increased(context: Context) -> None:
    """Check that token metrics have increased after a query.

    Compares current metrics against context.initial_token_metrics.
    """
    assert hasattr(
        context, "initial_token_metrics"
    ), "Initial metrics not captured. Call 'I capture the current token metrics' first"

    final_metrics = _get_current_token_metrics(context)
    initial_metrics = context.initial_token_metrics

    print(f"Final token metrics: {final_metrics}")

    # Check that both token metrics increased
    sent_increased = final_metrics["token_sent"] > initial_metrics["token_sent"]
    received_increased = (
        final_metrics["token_received"] > initial_metrics["token_received"]
    )

    assert sent_increased and received_increased, (
        f"Both token metrics should have increased. "
        f"Initial: {initial_metrics}, Final: {final_metrics}"
    )


@then("The token metrics should not have changed")
def check_token_metrics_unchanged(context: Context) -> None:
    """Check that token metrics have not changed after an error.

    Compares current metrics against context.initial_token_metrics.
    """
    assert hasattr(
        context, "initial_token_metrics"
    ), "Initial metrics not captured. Call 'I capture the current token metrics' first"

    final_metrics = _get_current_token_metrics(context)
    initial_metrics = context.initial_token_metrics

    print(f"Final token metrics: {final_metrics}")

    assert final_metrics["token_sent"] == initial_metrics["token_sent"], (
        f"token_sent should not have changed. "
        f"Initial: {initial_metrics['token_sent']}, Final: {final_metrics['token_sent']}"
    )
    assert final_metrics["token_received"] == initial_metrics["token_received"], (
        f"token_received should not have changed. "
        f"Initial: {initial_metrics['token_received']}, "
        f"Final: {final_metrics['token_received']}"
    )


@then("The streamed response should contain token counter fields")
def check_streamed_token_counter_fields(context: Context) -> None:
    """Check that streamed response end event contains token fields."""
    assert context.response_data is not None, "Response data needs to be parsed first"

    # Parse the end event from the streaming response to get token info
    end_event_data = _get_end_event_data(context.response.text)
    assert end_event_data is not None, "End event not found in streaming response"

    assert "input_tokens" in end_event_data, (
        f"Streamed response should contain 'input_tokens' in end event. "
        f"Got: {end_event_data}"
    )
    assert "output_tokens" in end_event_data, (
        f"Streamed response should contain 'output_tokens' in end event. "
        f"Got: {end_event_data}"
    )
    assert "available_quotas" in end_event_data, (
        f"Streamed response should contain 'available_quotas' in end event. "
        f"Got: {end_event_data}"
    )
    input_tokens: int = end_event_data["input_tokens"]
    output_tokens: int = end_event_data["output_tokens"]
    assert (
        input_tokens >= 0
    ), f"streamed input_tokens should be non-negative, got {input_tokens}"
    assert (
        output_tokens >= 0
    ), f"streamed output_tokens should be non-negative, got {output_tokens}"


def _get_current_token_metrics(context: Context) -> dict[str, float]:
    """Fetch and parse current token metrics from Prometheus endpoint.

    Parameters:
        context: Behave context containing hostname, port, and auth_headers.

    Returns:
        Dictionary with 'token_sent' and 'token_received' totals.
    """
    base = f"http://{context.hostname}:{context.port}"
    url = f"{base}/metrics"
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}

    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    assert (
        response.status_code == 200
    ), f"Failed to get metrics, status: {response.status_code}"

    return _parse_token_metrics(response.text)


def _get_end_event_data(response_text: str) -> Optional[dict]:
    """Extract the end event data from streaming SSE response.

    Parameters:
        response_text: The raw SSE response text.

    Returns:
        The data dictionary from the end event (including available_quotas),
        or None if not found.
    """
    lines = response_text.strip().split("\n")
    for line in lines:
        if line.startswith("data: "):
            try:
                event = json.loads(line[6:])
                if event.get("event") == "end":
                    # Merge data contents with available_quotas from parent level
                    result = event.get("data", {})
                    result["available_quotas"] = event.get("available_quotas", {})
                    return result
            except json.JSONDecodeError:
                continue
    return None


def _parse_token_metrics(metrics_text: str) -> dict[str, float]:
    """Parse Prometheus metrics text to extract token counter values.

    Parameters:
        metrics_text: Raw Prometheus metrics text output.

    Returns:
        Dictionary with 'token_sent' and 'token_received' totals.
    """
    token_sent_total = 0.0
    token_received_total = 0.0

    # Prometheus format: metric_name{labels} value
    for line in metrics_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract value (last space-separated element)
        if line.startswith("ls_llm_token_sent_total{"):
            value = line.split()[-1]
            token_sent_total += float(value)
        elif line.startswith("ls_llm_token_received_total{"):
            value = line.split()[-1]
            token_received_total += float(value)

    return {
        "token_sent": token_sent_total,
        "token_received": token_received_total,
    }
