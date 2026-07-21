"""A2A client manager for managing connections to external A2A agents."""

from typing import Any, Optional

import httpx
from a2a.client import (
    A2AClientError,
    ClientConfig,
    ClientFactory,
)
from a2a.client.client import Client
from a2a.client.middleware import ClientCallContext, ClientCallInterceptor
from a2a.types import AgentCard

from log import get_logger
from models.config import A2AAgentsConfiguration
from utils.types import Singleton

logger = get_logger(__name__)


class _BearerTokenInterceptor(
    ClientCallInterceptor
):  # pylint: disable=too-few-public-methods
    """Interceptor that adds a static bearer token to all requests."""

    def __init__(self, token: str) -> None:
        """Initialize with the bearer token.

        Parameters:
            token: Bearer token value.
        """
        self._token = token

    async def intercept(
        self,
        method_name: str,
        request_payload: dict[str, Any],
        http_kwargs: dict[str, Any],
        agent_card: AgentCard | None,
        context: ClientCallContext | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Add Authorization header to the request.

        Parameters:
            method_name: The RPC method name.
            request_payload: The JSON-RPC request payload.
            http_kwargs: HTTP request keyword arguments.
            agent_card: The AgentCard for the client.
            context: Call-specific context.

        Returns:
            Modified request payload and HTTP kwargs.
        """
        http_kwargs = {
            **http_kwargs,
            "headers": {
                **http_kwargs.get("headers", {}),
                "Authorization": f"Bearer {self._token}",
            },
        }
        return request_payload, http_kwargs


class A2AClientManager(metaclass=Singleton):
    """Singleton manager for external A2A agent client connections.

    Discovers agent cards at initialization, creates and caches Client
    instances per configured agent, and manages their lifecycle.
    """

    def __init__(self) -> None:
        """Initialize the client manager."""
        self._clients: dict[str, Client] = {}
        self._cards: dict[str, AgentCard] = {}
        self._initialized: bool = False

    @property
    def is_initialized(self) -> bool:
        """Return whether the manager has been initialized."""
        return self._initialized

    async def initialize(self, config: A2AAgentsConfiguration) -> None:
        """Discover agent cards and create clients for all configured agents.

        Parameters:
            config: A2A clients configuration with agent endpoints.
        """
        if self._initialized:
            return

        for agent_config in config.agents:
            name = agent_config.name
            url = str(agent_config.url)
            httpx_client: httpx.AsyncClient | None = None
            try:
                interceptors: list[ClientCallInterceptor] = []
                if agent_config.auth_token is not None:
                    token = agent_config.auth_token.get_secret_value()
                    interceptors.append(_BearerTokenInterceptor(token))

                transport = httpx.AsyncHTTPTransport(retries=agent_config.max_retries)
                httpx_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(agent_config.timeout),
                    transport=transport,
                )
                client = await ClientFactory.connect(
                    url,
                    client_config=ClientConfig(
                        streaming=True, httpx_client=httpx_client
                    ),
                    interceptors=interceptors or None,
                )
                card = await client.get_card()
                self._clients[name] = client
                self._cards[name] = card
                logger.info("Connected to A2A agent '%s' at %s", name, url)
            except (A2AClientError, httpx.HTTPError, OSError) as e:
                if httpx_client is not None:
                    await httpx_client.aclose()
                logger.warning(
                    "Failed to connect to A2A agent '%s' at %s: %s",
                    name,
                    url,
                    e,
                )

        self._initialized = True
        logger.info(
            "A2A client manager initialized with %d agent(s): %s",
            len(self._clients),
            list(self._clients.keys()),
        )

    def get_client(self, agent_name: str) -> Optional[Client]:
        """Return the Client for a named agent.

        Parameters:
            agent_name: Name of the agent as configured.

        Returns:
            Client instance, or None if the agent is not available.
        """
        return self._clients.get(agent_name)

    def get_card(self, agent_name: str) -> Optional[AgentCard]:
        """Return the cached AgentCard for a named agent.

        Parameters:
            agent_name: Name of the agent as configured.

        Returns:
            AgentCard, or None if the agent is not available.
        """
        return self._cards.get(agent_name)

    def list_agents(self) -> dict[str, AgentCard]:
        """Return all cached agent cards.

        Returns:
            Dictionary mapping agent names to their AgentCards.
        """
        return dict(self._cards)

    async def close(self) -> None:
        """Close all client connections."""
        for name, client in self._clients.items():
            try:
                if hasattr(client, "close"):
                    await client.close()  # pyright: ignore[reportAttributeAccessIssue]
                logger.info("Closed A2A client for agent '%s'", name)
            except (A2AClientError, httpx.HTTPError, OSError) as e:
                logger.warning(
                    "Error closing A2A client for agent '%s': %s",
                    name,
                    e,
                )
        self._clients.clear()
        self._cards.clear()
        self._initialized = False
