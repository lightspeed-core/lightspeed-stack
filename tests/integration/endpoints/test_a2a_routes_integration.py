"""Integration tests for the HTTP routes of the A2A endpoint."""

import pytest
from a2a.types import AgentCapabilities, AgentCard
from fastapi import status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


@pytest.fixture(name="agent_card")
def agent_card_fixture(mocker: MockerFixture) -> AgentCard:
    """Provide the agent card served by the A2A endpoint, without configuring one."""
    card = AgentCard(
        name="Test agent",
        description="Agent card for the A2A route tests",
        url="http://localhost:8080/a2a",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    mocker.patch("app.endpoints.a2a.get_lightspeed_agent_card", return_value=card)
    return card


def test_get_a2a_is_rejected_before_the_a2a_app_is_built(
    integration_http_client: TestClient, mocker: MockerFixture
) -> None:
    """Test that the router answers GET /a2a itself, and points the caller to POST.

    Parameters:
        integration_http_client: Client for the real application.
        mocker: Fixture used to watch the per-request A2A application builder.

    """
    create_a2a_app = mocker.patch("app.endpoints.a2a._create_a2a_app")

    response = integration_http_client.get("/a2a")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "POST"
    assert response.json() == {"detail": "Method Not Allowed"}
    create_a2a_app.assert_not_called()


@pytest.mark.usefixtures("agent_card")
def test_post_a2a_still_reaches_the_json_rpc_dispatcher(
    integration_http_client: TestClient,
) -> None:
    """Test that POST /a2a is answered by the A2A SDK JSON-RPC handler.

    Parameters:
        integration_http_client: Client for the real application.

    """
    response = integration_http_client.post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": "1", "method": "no/such-method", "params": {}},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "1",
        "error": {"code": -32601, "message": "Method not found"},
    }


@pytest.mark.parametrize(
    "path", ["/.well-known/agent.json", "/.well-known/agent-card.json"]
)
def test_agent_card_routes_are_kept(
    integration_http_client: TestClient, agent_card: AgentCard, path: str
) -> None:
    """Test that the agent card stays available at its well-known paths.

    Parameters:
        integration_http_client: Client for the real application.
        agent_card: The agent card the endpoint serves.
        path: Well-known path of the agent card.

    """
    response = integration_http_client.get(path)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == agent_card.name


def test_a2a_health_route_is_kept(integration_http_client: TestClient) -> None:
    """Test that the A2A health check stays available.

    Parameters:
        integration_http_client: Client for the real application.

    """
    response = integration_http_client.get("/a2a/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"
