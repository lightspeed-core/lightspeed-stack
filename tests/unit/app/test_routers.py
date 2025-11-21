"""Unit tests for routers.py."""

from typing import Any, Optional, Sequence, Callable

from fastapi import FastAPI

from app.routers import include_routers  # noqa:E402

from app.endpoints import (
    conversations_v2,
    conversations_v3,
    root,
    info,
    models,
    shields,
    rags,
    providers,
    query_v2,
    health,
    config,
    feedback,
    streaming_query_v2,
    authorized,
    metrics,
    tools,
    rlsapi_v1_infer,
)  # noqa:E402


class MockFastAPI(FastAPI):
    """Mock class for FastAPI."""

    def __init__(self) -> None:  # pylint: disable=super-init-not-called
        """Initialize mock class."""
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
        """Register new router."""
        self.routers.append((router, prefix))

    def get_routers(self) -> list[Any]:
        """Retrieve all routers defined in mocked REST API."""
        return [r[0] for r in self.routers]

    def get_router_prefix(self, router: Any) -> Optional[str]:
        """Retrieve router prefix configured for mocked REST API."""
        return list(filter(lambda r: r[0] == router, self.routers))[0][1]


def test_include_routers() -> None:
    """Test the function include_routers."""
    app = MockFastAPI()
    include_routers(app)

    # are all routers added?
    assert len(app.routers) == 17
    assert root.router in app.get_routers()
    assert info.router in app.get_routers()
    assert models.router in app.get_routers()
    assert tools.router in app.get_routers()
    assert shields.router in app.get_routers()
    assert providers.router in app.get_routers()
    # assert query.router in app.get_routers()
    assert query_v2.router in app.get_routers()
    # assert streaming_query.router in app.get_routers()
    assert streaming_query_v2.router in app.get_routers()
    assert config.router in app.get_routers()
    assert feedback.router in app.get_routers()
    assert health.router in app.get_routers()
    assert authorized.router in app.get_routers()
    # assert conversations.router in app.get_routers()
    assert conversations_v2.router in app.get_routers()
    assert conversations_v3.router in app.get_routers()
    assert metrics.router in app.get_routers()
    assert rlsapi_v1_infer.router in app.get_routers()


def test_check_prefixes() -> None:
    """Test the router prefixes."""
    app = MockFastAPI()
    include_routers(app)

    # are all routers added?
    assert len(app.routers) == 17
    assert app.get_router_prefix(root.router) == ""
    assert app.get_router_prefix(info.router) == "/v1"
    assert app.get_router_prefix(models.router) == "/v1"
    assert app.get_router_prefix(tools.router) == "/v1"
    assert app.get_router_prefix(shields.router) == "/v1"
    assert app.get_router_prefix(providers.router) == "/v1"
    assert app.get_router_prefix(rags.router) == "/v1"
    # assert app.get_router_prefix(query.router) == "/v1"
    # assert app.get_router_prefix(streaming_query.router) == "/v1"
    assert app.get_router_prefix(query_v2.router) == "/v1"
    assert app.get_router_prefix(streaming_query_v2.router) == "/v1"
    assert app.get_router_prefix(config.router) == "/v1"
    assert app.get_router_prefix(feedback.router) == "/v1"
    assert app.get_router_prefix(health.router) == ""
    assert app.get_router_prefix(authorized.router) == ""
    # assert app.get_router_prefix(conversations.router) == "/v1"
    assert app.get_router_prefix(conversations_v2.router) == "/v2"
    assert app.get_router_prefix(conversations_v3.router) == "/v1"
    assert app.get_router_prefix(rlsapi_v1_infer.router) == "/v1"
    assert app.get_router_prefix(metrics.router) == ""
