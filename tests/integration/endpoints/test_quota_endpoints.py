"""Integration tests for quota enforcement on the endpoints (LCORE-4610).

Every endpoint that calls the model checks the caller's quota first and
charges the usage of the call afterwards: ``/v1/query``,
``/v1/streaming_query``, ``/v1/responses`` (blocking and streaming) and
``/v1/infer`` when ``rlsapi_v1.quota_subject`` is set. The first three also
report the balances left, keyed by limiter class.

The quota is kept by real limiters on a real SQLite file and the handlers are
the real ones; only the model is mocked, and it reports the same usage for
every call. The balances are asserted both as the client sees them and as the
database holds them.
"""

# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=protected-access,redefined-outer-name

import json
import sqlite3
from collections.abc import AsyncIterator, Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from ogx_client.models.open_ai_response_object_stream_response_completed import (
    OpenAIResponseObjectStreamResponseCompleted,
)
from ogx_client.models.open_ai_response_object_stream_response_created import (
    OpenAIResponseObjectStreamResponseCreated,
)
from ogx_client.models.open_ai_response_object_stream_response_in_progress import (
    OpenAIResponseObjectStreamResponseInProgress,
)
from pytest_mock import AsyncMockType, MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.query import query_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from app.endpoints.rlsapi_v1 import infer_endpoint
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from authentication.rh_identity import RHIdentityData
from configuration import AppConfig
from models.api.requests import QueryRequest, ResponsesRequest
from models.api.requests.rlsapi import RlsapiV1InferRequest
from models.api.responses.successful import ResponsesResponse
from models.common.moderation import ShieldModerationBlocked
from models.common.responses.contexts import ResponsesContext
from models.config import QuotaLimiterConfiguration
from models.database.conversations import UserConversation
from quota.quota_limiter import QuotaLimiter
from tests.integration._quota_helpers import (
    CLUSTER,
    CLUSTER_SUBJECT,
    USER_SUBJECT,
    handlers,
    limiter_config,
    read_available,
    read_token_usage,
)
from tests.integration.conftest import (
    TEST_MODEL,
    TEST_MODEL_NAME,
    TEST_PROVIDER,
    make_openai_response_object,
    set_query_agent_run,
    set_streaming_query_agent_run,
)
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

TURN_INPUT, TURN_OUTPUT = 100, 50
TURN = TURN_INPUT + TURN_OUTPUT
"""What the model reports for every call it answers."""

QUESTION = "What is Ansible?"
ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"
ORG = "org-42"
SYSTEM = "cn-7"

QUOTA_EXCEEDED = "The quota has been exceeded"
DATABASE_ERROR = {
    "response": "Database query failed",
    "cause": "Failed to query the database",
}


def user_quota(initial_quota: int) -> QuotaLimiterConfiguration:
    """A user limiter that is never renewed during a test."""
    return limiter_config(
        "user_limiter", initial_quota=initial_quota, quota_increase=0, period="1 day"
    )


def cluster_quota(initial_quota: int) -> QuotaLimiterConfiguration:
    """A cluster limiter that is never renewed during a test."""
    return limiter_config(
        "cluster_limiter",
        initial_quota=initial_quota,
        quota_increase=0,
        period="1 day",
    )


def no_tokens_for_user(user_id: str) -> dict[str, str]:
    """The 429 body a user with an exhausted quota gets."""
    return {
        "response": QUOTA_EXCEEDED,
        "cause": f"User {user_id} has no available tokens",
    }


NO_TOKENS_FOR_CLUSTER = {
    "response": QUOTA_EXCEEDED,
    "cause": "Cluster has no available tokens",
}


def auth_for(user_id: str) -> AuthTuple:
    """The auth tuple the noop authentication produces for a user."""
    return (user_id, "lightspeed-user", True, "")


# ==========================================
# Fixtures
# ==========================================


@dataclass
class Quota:
    """The quota of a test: its configuration and its database.

    Attributes:
        config: The configuration, with the quota handlers set.
        db_path: The SQLite file the limiters and the history write to.

    """

    config: AppConfig
    db_path: Path

    @property
    def limiters(self) -> list[QuotaLimiter]:
        """The real limiters built from the configuration."""
        return self.config.quota_limiters

    def user_balance(self, user_id: str) -> Optional[int]:
        """What the database holds for a user, None when it never saw the user."""
        return read_available(self.db_path, user_id, USER_SUBJECT)

    def cluster_balance(self) -> Optional[int]:
        """What the database holds for the cluster, None when no row exists."""
        return read_available(self.db_path, CLUSTER, CLUSTER_SUBJECT)


ConfigureQuota = Callable[..., Quota]


@pytest.fixture(name="quota")
def quota_fixture(
    test_config: AppConfig, tmp_path: Path
) -> Generator[ConfigureQuota, None, None]:
    """Let a test choose its limiters; they live on a SQLite file in ``tmp_path``.

    Yields:
        A function taking the limiter configurations (and ``token_history``)
        that installs them in the loaded configuration and returns the
        :class:`Quota` of the test.

    """
    assert test_config._configuration is not None
    db_path = tmp_path / "quota.db"

    def _configure(
        *limiters: QuotaLimiterConfiguration, token_history: bool = False
    ) -> Quota:
        """Install the given limiters and reset what was built before."""
        assert test_config._configuration is not None
        test_config._configuration.quota_handlers = handlers(
            db_path, *limiters, enable_token_history=token_history
        )
        test_config._quota_limiters = []
        test_config._token_usage_history = None
        return Quota(test_config, db_path)

    yield _configure
    for limiter in test_config._quota_limiters:
        try:
            limiter.connection.close()
        except sqlite3.ProgrammingError:
            # opened by the thread TestClient served a request from; SQLite
            # refuses to close it from here and closes it with the object
            pass
    test_config._quota_limiters = []
    history = test_config._token_usage_history
    if history is not None and history.connection is not None:
        history.connection.close()
    test_config._token_usage_history = None


async def _responses_stream(response_object: Any) -> AsyncIterator[Any]:
    """Stream a response the way OGX does: created, in progress, completed."""
    yield OpenAIResponseObjectStreamResponseCreated(
        response=response_object, sequence_number=0, type="response.created"
    )
    yield OpenAIResponseObjectStreamResponseInProgress(
        response=response_object, sequence_number=1, type="response.in_progress"
    )
    yield OpenAIResponseObjectStreamResponseCompleted(
        response=response_object, sequence_number=2, type="response.completed"
    )


@pytest.fixture(name="model")
def model_fixture(
    test_config: AppConfig,
    mock_ogx_client: AsyncMockType,
    mock_query_agent: AsyncMockType,
    mock_streaming_query_agent: AsyncMockType,
    mocker: MockerFixture,
) -> AsyncMockType:
    """Make the model report the same usage to every endpoint.

    The query endpoints answer through the agent, ``/v1/responses`` and
    ``/v1/infer`` through ``responses.create`` of the OGX client. The
    responses context is built without validating the mocked client, as in
    the other responses integration tests.

    Returns:
        The mocked OGX client.

    """
    set_query_agent_run(
        mock_query_agent, mocker, input_tokens=TURN_INPUT, output_tokens=TURN_OUTPUT
    )
    set_streaming_query_agent_run(
        mock_streaming_query_agent,
        mocker,
        input_tokens=TURN_INPUT,
        output_tokens=TURN_OUTPUT,
    )

    async def _create(**kwargs: Any) -> Any:
        """Answer like OGX: a response object, or a stream of events."""
        answer = make_openai_response_object(
            input_tokens=TURN_INPUT, output_tokens=TURN_OUTPUT
        )
        return _responses_stream(answer) if kwargs.get("stream") else answer

    mock_ogx_client.responses.create = mocker.AsyncMock(side_effect=_create)
    mocker.patch(
        "app.endpoints.responses.ResponsesContext",
        side_effect=ResponsesContext.model_construct,
    )

    rlsapi_holder = mocker.patch("app.endpoints.rlsapi_v1.AsyncOgxClientHolder")
    rlsapi_holder.return_value.get_client.return_value = mock_ogx_client
    test_config.inference.default_model = TEST_MODEL_NAME
    test_config.inference.default_provider = TEST_PROVIDER
    mock_authorization_resolvers(mocker)
    return mock_ogx_client


# ==========================================
# Requests
# ==========================================


async def query(request: Request, auth: AuthTuple) -> Any:
    """Send a query as the given user."""
    return await query_endpoint_handler(
        request=request,
        query_request=QueryRequest(query=QUESTION),
        auth=auth,
        mcp_headers={},
    )


async def _events(response: Any) -> list[dict[str, Any]]:
    """Read a streaming response to its end and parse its ``data:`` lines."""
    assert isinstance(response, StreamingResponse)
    events: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        for line in str(chunk).splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[len("data: ") :]))
    return events


async def streaming_query(request: Request, auth: AuthTuple) -> dict[str, Any]:
    """Send a streaming query as the given user and return its ``end`` event."""
    response = await streaming_query_endpoint_handler(
        request=request,
        query_request=QueryRequest(query=QUESTION),
        auth=auth,
        mcp_headers={},
    )
    (end,) = [event for event in await _events(response) if event["event"] == "end"]
    return end


async def responses(request: Request, auth: AuthTuple, stream: bool) -> Any:
    """Send a responses request as the given user.

    Returns:
        The response object when blocking, else the ``(type, available_quotas)``
        of every streamed event that carries a response object.

    """
    response = await responses_endpoint_handler(
        request=request,
        responses_request=ResponsesRequest(
            input=QUESTION,
            model=TEST_MODEL,
            stream=stream,
            generate_topic_summary=False,
        ),
        auth=auth,
        mcp_headers={},
    )
    if not stream:
        assert isinstance(response, ResponsesResponse)
        return response
    return [
        (event["type"], event["response"].get("available_quotas"))
        for event in await _events(response)
        if "response" in event
    ]


async def infer(request: Request, auth: AuthTuple) -> Any:
    """Send an rlsapi v1 inference as the given user."""
    return await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question=QUESTION),
        request=request,
        background_tasks=BackgroundTasks(),
        auth=auth,
    )


# ==========================================
# /v1/query
# ==========================================


@pytest.mark.asyncio
async def test_query_charges_the_turn_and_reports_the_balance(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """A turn costs its input and output tokens; the client and the database agree."""
    _ = model
    scene = quota(user_quota(1000))

    response = await query(test_request, test_auth)

    assert (response.input_tokens, response.output_tokens) == (TURN_INPUT, TURN_OUTPUT)
    assert response.available_quotas == {"UserQuotaLimiter": 1000 - TURN}
    assert scene.user_balance(test_auth[0]) == 1000 - TURN


@pytest.mark.asyncio
async def test_query_is_served_while_the_balance_is_positive_then_rejected(
    quota: ConfigureQuota,
    model: AsyncMockType,
    mock_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """One token lets one turn through; the next is a 429 that costs nothing.

    The rejected request calls no model, creates no conversation and leaves
    the balance where the served turn put it.
    """
    _ = model
    user_id = test_auth[0]
    scene = quota(user_quota(1))

    served = await query(test_request, test_auth)
    assert served.available_quotas == {"UserQuotaLimiter": 1 - TURN}

    with pytest.raises(HTTPException) as rejected:
        await query(test_request, test_auth)

    assert rejected.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.value.detail == no_tokens_for_user(user_id)
    assert mock_query_agent.run.await_count == 1
    assert patch_db_session.query(UserConversation).count() == 1
    assert scene.user_balance(user_id) == 1 - TURN


def test_query_over_http_returns_the_429_body(
    integration_http_client: TestClient,
    quota: ConfigureQuota,
    model: AsyncMockType,
) -> None:
    """The quota error reaches an HTTP client as a 429 with the documented body."""
    _ = model
    scene = quota(user_quota(1))
    url = f"/v1/query?user_id={ALICE}"

    served = integration_http_client.post(url, json={"query": QUESTION})
    assert served.status_code == status.HTTP_200_OK, served.text
    assert served.json()["available_quotas"] == {"UserQuotaLimiter": 1 - TURN}

    rejected = integration_http_client.post(url, json={"query": QUESTION})
    assert rejected.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.json() == {"detail": no_tokens_for_user(ALICE)}
    assert scene.user_balance(ALICE) == 1 - TURN


# ==========================================
# /v1/streaming_query
# ==========================================


@pytest.mark.asyncio
async def test_streaming_query_reports_the_balance_in_its_end_event(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """The stream's end event carries the usage of the turn and the balance after it."""
    _ = model
    scene = quota(user_quota(1000))

    end = await streaming_query(test_request, test_auth)

    assert end["data"]["input_tokens"] == TURN_INPUT
    assert end["data"]["output_tokens"] == TURN_OUTPUT
    assert end["available_quotas"] == {"UserQuotaLimiter": 1000 - TURN}
    assert scene.user_balance(test_auth[0]) == 1000 - TURN


@pytest.mark.asyncio
async def test_streaming_query_of_an_exhausted_user_is_rejected_before_streaming(
    quota: ConfigureQuota,
    model: AsyncMockType,
    mock_streaming_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """An exhausted user gets the 429 as a plain error, never a stream."""
    _ = model
    quota(user_quota(1))
    await streaming_query(test_request, test_auth)

    with pytest.raises(HTTPException) as rejected:
        await streaming_query(test_request, test_auth)

    assert rejected.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.value.detail == no_tokens_for_user(test_auth[0])
    assert mock_streaming_query_agent.run_stream_events.call_count == 1


# ==========================================
# /v1/responses
# ==========================================


@pytest.mark.asyncio
async def test_blocking_responses_reports_the_balance(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """A blocking response carries the balance left after its usage was charged."""
    _ = model
    scene = quota(user_quota(1000))

    response = await responses(test_request, test_auth, stream=False)

    assert response.available_quotas == {"UserQuotaLimiter": 1000 - TURN}
    assert scene.user_balance(test_auth[0]) == 1000 - TURN


@pytest.mark.asyncio
async def test_streamed_responses_reports_the_balance_on_the_terminal_event(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Intermediate events carry no balance; the completed event carries the charged one."""
    _ = model
    scene = quota(user_quota(1000))

    events = await responses(test_request, test_auth, stream=True)

    assert events == [
        ("response.created", None),
        ("response.in_progress", {}),
        ("response.completed", {"UserQuotaLimiter": 1000 - TURN}),
    ]
    assert scene.user_balance(test_auth[0]) == 1000 - TURN


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["blocking", "streaming"])
async def test_responses_of_an_exhausted_user_is_rejected(
    stream: bool,
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Blocking or streaming, the second request of a one-token user is a 429."""
    quota(user_quota(1))
    await responses(test_request, test_auth, stream)

    with pytest.raises(HTTPException) as rejected:
        await responses(test_request, test_auth, stream)

    assert rejected.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.value.detail == no_tokens_for_user(test_auth[0])
    assert model.responses.create.await_count == 1


@pytest.mark.asyncio
async def test_a_shield_blocked_streamed_responses_turn_costs_nothing(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """A turn an input shield blocks calls no model and is not charged.

    Its stream still ends with the balance, the one the served turn before
    it left behind.
    """
    scene = quota(user_quota(1000))
    await responses(test_request, test_auth, stream=True)
    balance = 1000 - TURN
    assert scene.user_balance(test_auth[0]) == balance
    mocker.patch(
        "app.endpoints.responses.run_shield_moderation_v2",
        return_value=ShieldModerationBlocked(
            message="Content blocked by safety shield", moderation_id="modr-blocked"
        ),
    )

    events = await responses(test_request, test_auth, stream=True)

    assert events == [
        ("response.created", {}),
        ("response.completed", {"UserQuotaLimiter": balance}),
    ]
    assert model.responses.create.await_count == 1
    assert scene.user_balance(test_auth[0]) == balance


# ==========================================
# /v1/infer
# ==========================================


def _user_identity(org_id: str) -> RHIdentityData:
    """The rh-identity data of a console user of an organization."""
    return RHIdentityData(
        {
            "identity": {
                "type": "User",
                "org_id": org_id,
                "user": {"user_id": "console-user", "username": "console@example"},
            }
        }
    )


def _system_identity(cn: str) -> RHIdentityData:
    """The rh-identity data of a certificate-authenticated system."""
    return RHIdentityData(
        {"identity": {"type": "System", "org_id": ORG, "system": {"cn": cn}}}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quota_subject", "identity", "charged"),
    [
        pytest.param("user_id", None, ALICE, id="user_id"),
        pytest.param("org_id", _user_identity(ORG), ORG, id="org_id"),
        pytest.param("system_id", _system_identity(SYSTEM), SYSTEM, id="system_id"),
        pytest.param("org_id", None, ALICE, id="org_id_without_identity_falls_back"),
        pytest.param(
            "system_id", None, ALICE, id="system_id_without_identity_falls_back"
        ),
    ],
)
async def test_infer_charges_the_configured_quota_subject(
    quota_subject: str,
    identity: Optional[RHIdentityData],
    charged: str,
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """The row charged is the one ``rlsapi_v1.quota_subject`` names, or the user's."""
    _ = model
    scene = quota(user_quota(1000))
    scene.config.configuration.rlsapi_v1.quota_subject = quota_subject  # type: ignore[assignment]
    if identity is not None:
        test_request.state.rh_identity_data = identity

    await infer(test_request, auth_for(ALICE))

    assert scene.user_balance(charged) == 1000 - TURN
    for other in {ALICE, ORG, SYSTEM} - {charged}:
        assert scene.user_balance(other) is None


@pytest.mark.asyncio
async def test_infer_of_an_exhausted_user_is_rejected(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """With a quota subject set, a one-token user gets one inference, then a 429."""
    scene = quota(user_quota(1))
    scene.config.configuration.rlsapi_v1.quota_subject = "user_id"
    await infer(test_request, auth_for(ALICE))

    with pytest.raises(HTTPException) as rejected:
        await infer(test_request, auth_for(ALICE))

    assert rejected.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.value.detail == no_tokens_for_user(ALICE)
    assert model.responses.create.await_count == 1
    assert scene.user_balance(ALICE) == 1 - TURN


@pytest.mark.asyncio
async def test_infer_is_not_enforced_without_a_quota_subject(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """Without ``quota_subject`` the limiters are neither consulted nor charged."""
    scene = quota(user_quota(1))
    assert scene.config.configuration.rlsapi_v1.quota_subject is None

    await infer(test_request, auth_for(ALICE))
    await infer(test_request, auth_for(ALICE))

    assert model.responses.create.await_count == 2
    assert not scene.db_path.exists(), "no limiter was built, so no database either"


# ==========================================
# User and cluster limiters together
# ==========================================


@pytest.mark.asyncio
async def test_the_cluster_balance_is_shared_and_both_balances_are_reported(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """Each user has a balance of their own; the cluster balance is paid by all of them."""
    _ = model
    scene = quota(user_quota(1000), cluster_quota(1000))

    alice = await query(test_request, auth_for(ALICE))
    bob = await query(test_request, auth_for(BOB))

    assert alice.available_quotas == {
        "UserQuotaLimiter": 1000 - TURN,
        "ClusterQuotaLimiter": 1000 - TURN,
    }
    assert bob.available_quotas == {
        "UserQuotaLimiter": 1000 - TURN,
        "ClusterQuotaLimiter": 1000 - 2 * TURN,
    }
    assert scene.user_balance(ALICE) == 1000 - TURN
    assert scene.user_balance(BOB) == 1000 - TURN
    assert scene.cluster_balance() == 1000 - 2 * TURN


@pytest.mark.asyncio
async def test_an_exhausted_cluster_rejects_a_user_who_still_has_tokens(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """The cause names the cluster; the user's own balance is created but not charged."""
    _ = model
    scene = quota(user_quota(1000), cluster_quota(1))
    await query(test_request, auth_for(ALICE))
    assert scene.cluster_balance() == 1 - TURN

    with pytest.raises(HTTPException) as rejected:
        await query(test_request, auth_for(BOB))

    assert rejected.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rejected.value.detail == NO_TOKENS_FOR_CLUSTER
    assert scene.user_balance(BOB) == 1000
    assert scene.cluster_balance() == 1 - TURN


@pytest.mark.asyncio
async def test_an_exhausted_user_is_named_before_the_cluster_is_consulted(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """Limiters are checked in configuration order; the user limiter comes first."""
    _ = model
    scene = quota(user_quota(1), cluster_quota(1000))
    await query(test_request, auth_for(ALICE))

    with pytest.raises(HTTPException) as rejected:
        await query(test_request, auth_for(ALICE))

    assert rejected.value.detail == no_tokens_for_user(ALICE)
    assert scene.cluster_balance() == 1000 - TURN


# ==========================================
# Token usage history
# ==========================================


@pytest.mark.asyncio
@pytest.mark.parametrize("with_limiter", [True, False], ids=["limiter", "no_limiter"])
async def test_token_history_accumulates_per_user_provider_and_model(
    with_limiter: bool,
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
) -> None:
    """With ``enable_token_history`` every turn is added to its user's row.

    The history is kept with or without limiters: the storage alone is enough.
    """
    _ = model
    limiters = [user_quota(1000)] if with_limiter else []
    scene = quota(*limiters, token_history=True)

    await query(test_request, auth_for(ALICE))
    await query(test_request, auth_for(ALICE))
    bob = await query(test_request, auth_for(BOB))

    assert read_token_usage(scene.db_path) == {
        (ALICE, TEST_PROVIDER, TEST_MODEL_NAME): (2 * TURN_INPUT, 2 * TURN_OUTPUT),
        (BOB, TEST_PROVIDER, TEST_MODEL_NAME): (TURN_INPUT, TURN_OUTPUT),
    }
    expected_quotas = {"UserQuotaLimiter": 1000 - TURN} if with_limiter else {}
    assert bob.available_quotas == expected_quotas


# ==========================================
# The quota database goes away
# ==========================================


@pytest.mark.asyncio
async def test_a_limiter_reconnects_after_its_connection_died(
    quota: ConfigureQuota,
    model: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """A lost connection is reopened on the next request, which continues the balance."""
    _ = model
    scene = quota(user_quota(1000))
    await query(test_request, test_auth)
    (limiter,) = scene.limiters
    limiter.connection.close()

    response = await query(test_request, test_auth)

    assert response.available_quotas == {"UserQuotaLimiter": 1000 - 2 * TURN}
    assert scene.user_balance(test_auth[0]) == 1000 - 2 * TURN


@pytest.mark.asyncio
async def test_an_unreachable_quota_database_is_a_500_not_a_served_turn(
    quota: ConfigureQuota,
    model: AsyncMockType,
    mock_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """When the database cannot be reopened the check fails closed with a database error."""
    _ = model
    scene = quota(user_quota(1000))
    await query(test_request, test_auth)
    (limiter,) = scene.limiters
    limiter.connection.close()
    mocker.patch(
        "quota.quota_limiter.connect_sqlite",
        side_effect=sqlite3.OperationalError("unable to open database file"),
    )

    with pytest.raises(HTTPException) as failed:
        await query(test_request, test_auth)

    assert failed.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert failed.value.detail == DATABASE_ERROR
    assert mock_query_agent.run.await_count == 1


def _fail_on_the_second_call(mocker: MockerFixture, limiter: QuotaLimiter) -> None:
    """Let the balance read of the check pass, then fail the one of the report."""
    real_available_quota = limiter.available_quota

    def read_then_fail(subject_id: str = "") -> int:
        """Delegate once, then raise like a lost database."""
        if available_quota.call_count > 1:
            raise sqlite3.OperationalError("database is locked")
        return real_available_quota(subject_id)

    available_quota = mocker.patch.object(
        limiter, "available_quota", side_effect=read_then_fail
    )


def _fail_the_charge(mocker: MockerFixture, limiter: QuotaLimiter) -> None:
    """Fail the consumption of the turn's usage."""
    mocker.patch.object(
        limiter,
        "consume_tokens",
        side_effect=sqlite3.OperationalError("database is locked"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail", "balance_left"),
    [
        pytest.param(_fail_the_charge, 1000, id="charging_the_turn"),
        pytest.param(_fail_on_the_second_call, 1000 - TURN, id="reporting_the_balance"),
    ],
)
async def test_a_database_error_after_the_model_answered_is_a_500(
    fail: Callable[[MockerFixture, QuotaLimiter], None],
    balance_left: int,
    quota: ConfigureQuota,
    model: AsyncMockType,
    mock_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """The check passed and the model answered; then the database fails.

    Whether the usage can not be charged or the balance can not be read for
    the response, the client gets the database error. A charge that went
    through before the read failed stays charged.
    """
    _ = model
    scene = quota(user_quota(1000))
    (limiter,) = scene.limiters
    fail(mocker, limiter)

    with pytest.raises(HTTPException) as failed:
        await query(test_request, test_auth)

    assert failed.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert failed.value.detail == DATABASE_ERROR
    assert mock_query_agent.run.await_count == 1
    assert scene.user_balance(test_auth[0]) == balance_left
