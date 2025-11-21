"""REST API routers."""

from fastapi import FastAPI

from app.endpoints import (
    info,
    models,
    shields,
    providers,
    rags,
    root,
    health,
    config,
    feedback,
    streaming_query_v2,
    authorized,
    conversations_v2,
    conversations_v3,
    metrics,
    tools,
    # V2 endpoints for Response API support
    query_v2,
    # RHEL Lightspeed rlsapi v1 compatibility
    rlsapi_v1_infer,
)


def include_routers(app: FastAPI) -> None:
    """Include FastAPI routers for different endpoints.

    Args:
        app: The `FastAPI` app instance.
    """
    app.include_router(root.router)

    app.include_router(info.router, prefix="/v1")
    app.include_router(models.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")
    app.include_router(shields.router, prefix="/v1")
    app.include_router(providers.router, prefix="/v1")
    app.include_router(rags.router, prefix="/v1")
    # V1 endpoints now use V2 implementations (query and streaming_query are deprecated)
    app.include_router(query_v2.router, prefix="/v1")
    app.include_router(streaming_query_v2.router, prefix="/v1")
    app.include_router(config.router, prefix="/v1")
    app.include_router(feedback.router, prefix="/v1")
    # V1 conversations endpoint now uses V3 implementation (conversations is deprecated)
    app.include_router(conversations_v3.router, prefix="/v1")
    app.include_router(
        rlsapi_v1_infer.router, prefix="/v1"
    )  # RHEL Lightspeed rlsapi v1 compatibility
    app.include_router(conversations_v2.router, prefix="/v2")

    # Note: query_v2, streaming_query_v2, and conversations_v3 are now exposed at /v1 above
    # The old query, streaming_query, and conversations modules are deprecated

    # road-core does not version these endpoints
    app.include_router(health.router)
    app.include_router(authorized.router)
    app.include_router(metrics.router)
