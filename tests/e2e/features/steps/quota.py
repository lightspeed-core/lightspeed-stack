"""Step definitions for the quota management e2e feature (LCORE-4610).

The steps talk to the service over HTTP only. A scenario acts as a user the
service has never seen, a fresh uuid handed to the noop authentication as the
``user_id`` query parameter, so the balances it reads are its own whatever
the quota database already holds. The cluster balance is shared, so it is
only ever compared with an earlier reading of the same scenario.
"""

import json
import time
import uuid
from typing import Any

from behave import (
    given,
    step,
    then,
    when,
)  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    DEFAULT_LLM_TIMEOUT,
    parse_responses_sse_final_response_object,
    parse_streaming_query_end_event,
    read_streamed_response,
    replace_placeholders,
    request_with_transient_retry,
)

QUOTA_EXCEEDED_RESPONSE = "The quota has been exceeded"
CLUSTER_LIMITER = "ClusterQuotaLimiter"
HTTP_TOO_MANY_REQUESTS = 429
POLL_INTERVAL_SECONDS = 1.0


@given("I am a user the service has not seen before")
def fresh_user(context: Context) -> None:
    """Act as a user with a fresh id from now on."""
    context.quota_user_id = str(uuid.uuid4())


def _ask(context: Context, endpoint: str, payload: dict[str, Any]) -> None:
    """Send the payload to the endpoint as the scenario's user and keep the response."""
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = f"{base}{path}?user_id={context.quota_user_id}"
    streamed = endpoint == "streaming_query" or (
        endpoint == "responses" and bool(payload.get("stream"))
    )
    response = request_with_transient_retry(
        method="POST",
        url=url,
        json=payload,
        timeout=DEFAULT_LLM_TIMEOUT,
        stream=streamed,
    )
    if streamed:
        body = read_streamed_response(response)
        response._content = body.encode(  # pylint: disable=protected-access
            response.encoding or "utf-8"
        )
    context.response = response
    # the steps of this module read the raw response, not a parsed stream
    context.use_streaming_response_data = False


@step('I use "{endpoint}" to ask question as that user')
def ask_as_that_user(context: Context, endpoint: str) -> None:
    """Send the question in the step text as the scenario's user."""
    payload = json.loads(replace_placeholders(context, context.text or "{}"))
    context.quota_last_request = (endpoint, payload)
    _ask(context, endpoint, payload)


@when(
    "I repeat the question as that user until it is no longer rejected, "
    "within {budget:d} seconds"
)
def repeat_until_served(context: Context, budget: int) -> None:
    """Resend the last question every second while it gets a 429, up to the budget.

    A rejected request costs no tokens, so repeating it cannot delay the
    renewal it waits for. The last response, served or not, is kept.
    """
    endpoint, payload = context.quota_last_request
    deadline = time.monotonic() + budget
    attempts = 0
    while True:
        attempts += 1
        _ask(context, endpoint, payload)
        if context.response.status_code != HTTP_TOO_MANY_REQUESTS:
            return
        if time.monotonic() + POLL_INTERVAL_SECONDS > deadline:
            raise AssertionError(
                f"Still rejected after {attempts} attempts within {budget} seconds: "
                f"{context.response.text}"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def _end_event(text: str) -> dict[str, Any]:
    """Return the ``end`` event of a streaming_query body, merged with its quotas."""
    end = parse_streaming_query_end_event(text)
    assert end is not None, "No end event found in the streaming response"
    return end


def _result(context: Context) -> dict[str, Any]:
    """Return the object of a served request that carries its usage and quotas.

    That is the JSON body of ``query``, ``responses`` and ``infer``, the ``end``
    event of ``streaming_query`` and the terminal event's response object of a
    streamed ``responses`` call.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert (
        context.response.status_code == 200
    ), f"Expected a served request, got {context.response.status_code}"
    endpoint, payload = context.quota_last_request
    if endpoint == "streaming_query":
        return _end_event(context.response.text)
    if endpoint == "responses" and bool(payload.get("stream")):
        return parse_responses_sse_final_response_object(context.response.text)
    return context.response.json()


def _turn_tokens(result: dict[str, Any]) -> int:
    """Return the input plus output tokens a served request reports."""
    usage = result.get("usage", result)
    assert (
        "input_tokens" in usage and "output_tokens" in usage
    ), f"The response does not report its token usage: {result}"
    return int(usage["input_tokens"]) + int(usage["output_tokens"])


def _available_quota(context: Context, name: str) -> int:
    """Return the balance a served request reports for the named limiter."""
    result = _result(context)
    quotas = result.get("available_quotas")
    assert isinstance(quotas, dict), f"No available_quotas in the response: {result}"
    assert name in quotas, f"No {name!r} in available_quotas {quotas}"
    return int(quotas[name])


@then("The response reports a positive token usage of the turn")
def positive_turn_usage(context: Context) -> None:
    """Keep the tokens of the turn; a provider counting none makes this step fail."""
    tokens = _turn_tokens(_result(context))
    assert tokens > 0, "The turn used no tokens, so it could not exhaust anything"
    context.quota_turn_tokens = tokens


@then('The available quota "{name}" is {initial:d} minus the tokens of the turn')
def available_quota_is(context: Context, name: str, initial: int) -> None:
    """Check that the reported balance is the initial quota less what the turn used."""
    expected = initial - context.quota_turn_tokens
    actual = _available_quota(context, name)
    assert actual == expected, f"{name}: expected {expected}, got {actual}"


@then(
    'The available quota "{name}" is at least {initial:d} minus the tokens of the turn'
)
def available_quota_is_at_least(context: Context, name: str, initial: int) -> None:
    """Check that the reported balance is at least the initial quota less the turn.

    Used where a renewal may have been applied more than once by the time the
    balance was read.
    """
    expected = initial - context.quota_turn_tokens
    actual = _available_quota(context, name)
    assert actual >= expected, f"{name}: expected at least {expected}, got {actual}"


@then('The available quota "{name}" is reported')
def available_quota_is_reported(context: Context, name: str) -> None:
    """Check that the named limiter is among the reported balances."""
    _available_quota(context, name)


@step("I remember the available cluster quota")
def remember_cluster_quota(context: Context) -> None:
    """Keep the cluster balance the last served request reported."""
    context.quota_remembered_cluster = _available_quota(context, CLUSTER_LIMITER)


@then(
    "The available cluster quota went down by the tokens of the turn "
    "since I remembered it"
)
def cluster_quota_went_down_by_the_turn(context: Context) -> None:
    """Only the turn was charged to the cluster since the balance was remembered."""
    expected = context.quota_remembered_cluster - context.quota_turn_tokens
    actual = _available_quota(context, CLUSTER_LIMITER)
    assert actual == expected, (
        f"Cluster balance {context.quota_remembered_cluster} should have gone down "
        f"by {context.quota_turn_tokens} to {expected}, got {actual}"
    )


@then("The response is the quota exceeded error for that user")
def quota_exceeded_error(context: Context) -> None:
    """Check that the body is the quota error naming the scenario's user."""
    assert context.response is not None, "Request needs to be performed first"
    body = context.response.json()
    assert "detail" in body, f"No detail in the error body: {body}"
    assert body["detail"] == {
        "response": QUOTA_EXCEEDED_RESPONSE,
        "cause": f"User {context.quota_user_id} has no available tokens",
    }, f"Unexpected error body: {body}"
