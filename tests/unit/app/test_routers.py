"""Unit tests for routers.py."""

from typing import Any, Optional

from app.routers import include_routers  # noqa:E402

from app.endpoints import (
    conversations,
    root,
    info,
    models,
    query,
    health,
    config,
    feedback,
    streaming_query,
    authorized,
    metrics,
)  # noqa:E402


class MockFastAPI:
    """Mock class for FastAPI."""

    def __init__(self) -> None:
        """Initialize mock class."""
        self.routers: list[tuple[Any, Optional[str]]] = []

    def include_router(self, router: Any, prefix: Optional[str] = None) -> None:
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
    assert len(app.routers) == 11
    assert root.router in app.get_routers()
    assert info.router in app.get_routers()
    assert models.router in app.get_routers()
    assert query.router in app.get_routers()
    assert streaming_query.router in app.get_routers()
    assert config.router in app.get_routers()
    assert feedback.router in app.get_routers()
    assert health.router in app.get_routers()
    assert authorized.router in app.get_routers()
    assert conversations.router in app.get_routers()
    assert metrics.router in app.get_routers()


def test_check_prefixes() -> None:
    """Test the router prefixes."""
    app = MockFastAPI()
    include_routers(app)

    # are all routers added?
    assert len(app.routers) == 11
    assert app.get_router_prefix(root.router) is None
    assert app.get_router_prefix(info.router) == "/v1"
    assert app.get_router_prefix(models.router) == "/v1"
    assert app.get_router_prefix(query.router) == "/v1"
    assert app.get_router_prefix(streaming_query.router) == "/v1"
    assert app.get_router_prefix(config.router) == "/v1"
    assert app.get_router_prefix(feedback.router) == "/v1"
    assert app.get_router_prefix(health.router) is None
    assert app.get_router_prefix(authorized.router) is None
    assert app.get_router_prefix(conversations.router) == "/v1"
    assert app.get_router_prefix(metrics.router) is None
