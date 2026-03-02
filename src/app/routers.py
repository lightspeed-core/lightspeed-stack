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
    streaming_query,
    stream_interrupt,
    authorized,
    conversations_v2,
    conversations_v1,
    metrics,
    tools,
    mcp_auth,
    # Query endpoints for Response API support
    query,
    # RHEL Lightspeed rlsapi v1 compatibility
    rlsapi_v1,
    # A2A (Agent-to-Agent) protocol support
    a2a,
)


def include_routers(app: FastAPI) -> None:
    """Include FastAPI routers for different endpoints.

    Register and mount project routers on the given FastAPI application.

    Registers endpoint routers and assigns URL prefixes: most endpoints are
    mounted under "/v1", v2 routers under "/v2", and core endpoints (health,
    authorized, metrics) are mounted without a version prefix.

    Parameters:
        app (FastAPI): The FastAPI application to which routers will be attached.
    """
    app.include_router(root.router)

    app.include_router(info.router, prefix="/v1")
    app.include_router(models.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")
    app.include_router(mcp_auth.router, prefix="/v1")
    app.include_router(shields.router, prefix="/v1")
    app.include_router(providers.router, prefix="/v1")
    app.include_router(rags.router, prefix="/v1")
    # Query endpoints
    app.include_router(query.router, prefix="/v1")
    app.include_router(streaming_query.router, prefix="/v1")
    app.include_router(stream_interrupt.router, prefix="/v1")
    app.include_router(config.router, prefix="/v1")
    app.include_router(feedback.router, prefix="/v1")
    app.include_router(conversations_v1.router, prefix="/v1")
    app.include_router(conversations_v2.router, prefix="/v2")

    # RHEL Lightspeed rlsapi v1 compatibility - stateless CLA (Command Line Assistant) endpoint
    app.include_router(rlsapi_v1.router, prefix="/v1")

    # road-core does not version these endpoints
    app.include_router(health.router)
    app.include_router(authorized.router)
    app.include_router(metrics.router)

    # A2A (Agent-to-Agent) protocol endpoint
    app.include_router(a2a.router)
