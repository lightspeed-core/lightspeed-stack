"""REST API routers."""

from fastapi import FastAPI

from app.endpoints import (
    info,
    models,
    root,
    query,
    health,
    config,
    feedback,
    streaming_query,
)


def include_routers(app: FastAPI) -> None:
    """Include FastAPI routers for different endpoints.

    Args:
        app: The `FastAPI` app instance.
    """
    app.include_router(root.router)
    app.include_router(info.router, prefix="/v1")
    app.include_router(models.router, prefix="/v1")
    app.include_router(query.router, prefix="/v1")
    app.include_router(health.router, prefix="/v1")
    app.include_router(config.router, prefix="/v1")
    app.include_router(feedback.router, prefix="/v1")
    app.include_router(streaming_query.router, prefix="/v1")
