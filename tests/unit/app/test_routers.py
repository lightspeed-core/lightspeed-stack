"""Unit tests for routers.py."""

from typing import Any, Optional, Sequence, Callable

from fastapi import FastAPI

from app.routers import include_routers  # noqa:E402

from app.endpoints import (
    conversations_v2,
    conversations_v1,
    root,
    info,
    models,
    shields,
    rags,
    providers,
    health,
    config,
    feedback,
    stream_interrupt,
    streaming_query,
    authorized,
    metrics,
    tools,
    mcp_auth,
    rlsapi_v1,
    a2a,
    query,
)  # noqa:E402


class MockFastAPI(FastAPI):
    """Mock class for FastAPI."""

    def __init__(self) -> None:  # pylint: disable=super-init-not-called
        """Initialize mock class.

        Create a mock FastAPI-like app and initialize its router
        registry.

        The instance attribute `routers` is initialized as an empty
        list that will store tuples of (router, prefix), where
        `prefix` is the route prefix string or `None`.
        """
        self.routers: list[tuple[Any, Optional[str]]] = []

    def include_router(  # pylint: disable=too-many-arguments
        self,
        router: Any,
        *,
        prefix: str = "",
        tags: Optional[list] = None,
        dependencies: Optional[Sequence] = None,
        responses: Optional[dict] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: Optional[bool] = None,
        default_response_class: Optional[Any] = None,
        callbacks: Optional[list] = None,
        generate_unique_id_function: Optional[Callable] = None,
    ) -> None:
        """Register new router.

        Register a router and its mount prefix on the mock FastAPI
        app for test inspection.

        Parameters:
            router (Any): Router object to register.
            prefix (str): Mount prefix to associate with the router.

        Notes:
            Accepts additional FastAPI-compatible parameters for
            API compatibility but ignores them; only the (router,
            prefix) pair is recorded.
        """
        self.routers.append((router, prefix))

    def get_routers(self) -> list[Any]:
        """Retrieve all routers defined in mocked REST API.

        Returns:
            routers (list[Any]): List of registered router objects in the order they were added.
        """
        return [r[0] for r in self.routers]

    def get_router_prefix(self, router: Any) -> Optional[str]:
        """Retrieve router prefix configured for mocked REST API.

        Get the prefix associated with a registered router in the mock FastAPI.

        Parameters:
            router (Any): Router object to look up.

        Returns:
            Optional[str]: The prefix string for the router, or `None` if the
            router was registered without a prefix.

        Raises:
            IndexError: If the router is not registered in the mock app.
        """
        return list(filter(lambda r: r[0] == router, self.routers))[0][1]


def test_include_routers() -> None:
    """Test the function include_routers."""
    app = MockFastAPI()
    include_routers(app)

    # are all routers added?
    assert len(app.routers) == 20
    assert root.router in app.get_routers()
    assert info.router in app.get_routers()
    assert models.router in app.get_routers()
    assert tools.router in app.get_routers()
    assert mcp_auth.router in app.get_routers()
    assert shields.router in app.get_routers()
    assert providers.router in app.get_routers()
    assert query.router in app.get_routers()
    assert streaming_query.router in app.get_routers()
    assert config.router in app.get_routers()
    assert feedback.router in app.get_routers()
    assert health.router in app.get_routers()
    assert authorized.router in app.get_routers()
    # assert conversations.router in app.get_routers()
    assert conversations_v2.router in app.get_routers()
    assert conversations_v1.router in app.get_routers()
    assert metrics.router in app.get_routers()
    assert rlsapi_v1.router in app.get_routers()
    assert a2a.router in app.get_routers()
    assert stream_interrupt.router in app.get_routers()


def test_check_prefixes() -> None:
    """Test the router prefixes.

    Verify that include_routers registers the expected routers with their configured URL prefixes.

    Asserts that 16 routers are registered on a MockFastAPI instance and that
    each router's prefix matches the expected value (e.g., root, health,
    authorized, metrics use an empty prefix; most API routers use "/v1";
    conversations_v2 uses "/v2").
    """
    app = MockFastAPI()
    include_routers(app)

    # are all routers added?
    assert len(app.routers) == 20
    assert app.get_router_prefix(root.router) == ""
    assert app.get_router_prefix(info.router) == "/v1"
    assert app.get_router_prefix(models.router) == "/v1"
    assert app.get_router_prefix(tools.router) == "/v1"
    assert app.get_router_prefix(mcp_auth.router) == "/v1"
    assert app.get_router_prefix(shields.router) == "/v1"
    assert app.get_router_prefix(providers.router) == "/v1"
    assert app.get_router_prefix(rags.router) == "/v1"
    assert app.get_router_prefix(query.router) == "/v1"
    assert app.get_router_prefix(streaming_query.router) == "/v1"
    assert app.get_router_prefix(config.router) == "/v1"
    assert app.get_router_prefix(feedback.router) == "/v1"
    assert app.get_router_prefix(health.router) == ""
    assert app.get_router_prefix(authorized.router) == ""
    # assert app.get_router_prefix(conversations.router) == "/v1"
    assert app.get_router_prefix(conversations_v2.router) == "/v2"
    assert app.get_router_prefix(conversations_v1.router) == "/v1"
    assert app.get_router_prefix(metrics.router) == ""
    assert app.get_router_prefix(rlsapi_v1.router) == "/v1"
    assert app.get_router_prefix(a2a.router) == ""
    assert app.get_router_prefix(stream_interrupt.router) == "/v1"
