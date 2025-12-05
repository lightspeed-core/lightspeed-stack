"""Definition of FastAPI based web service."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute

import metrics
import version
from app import routers
from app.database import create_tables, initialize_database
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.responses import InternalServerErrorResponse
from utils.common import register_mcp_servers_async
from utils.llama_stack_version import check_llama_stack_version

logger = get_logger(__name__)

logger.info("Initializing app")


service_name = configuration.configuration.name


# running on FastAPI startup
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Initialize app resources.

    FastAPI lifespan context: initializes configuration, Llama client, MCP servers,
    logger, and database before serving requests.
    """
    configuration.load_configuration(os.environ["LIGHTSPEED_STACK_CONFIG_PATH"])
    await AsyncLlamaStackClientHolder().load(configuration.configuration.llama_stack)
    client = AsyncLlamaStackClientHolder().get_client()
    # check if the Llama Stack version is supported by the service
    await check_llama_stack_version(client)

    logger.info("Registering MCP servers")
    await register_mcp_servers_async(logger, configuration.configuration)
    get_logger("app.endpoints.handlers")
    logger.info("App startup complete")

    initialize_database()
    create_tables()

    yield


app = FastAPI(
    title=f"{service_name} service - OpenAPI",
    summary=f"{service_name} service API specification.",
    description=f"{service_name} service API specification.",
    version=version.__version__,
    contact={
        "name": "Pavel Tisnovsky",
        "url": "https://github.com/tisnik/",
        "email": "ptisnovs@redhat.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    servers=[
        {"url": "http://localhost:8080/", "description": "Locally running service"}
    ],
    lifespan=lifespan,
)

cors = configuration.service_configuration.cors

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors.allow_origins,
    allow_credentials=cors.allow_credentials,
    allow_methods=cors.allow_methods,
    allow_headers=cors.allow_headers,
)


@app.middleware("")
async def rest_api_metrics(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware with REST API counter update logic."""
    path = request.url.path
    logger.debug("Received request for path: %s", path)

    # ignore paths that are not part of the app routes
    if path not in app_routes_paths:
        return await call_next(request)

    logger.debug("Processing API request for path: %s", path)

    # measure time to handle duration + update histogram
    with metrics.response_duration_seconds.labels(path).time():
        response = await call_next(request)

    # ignore /metrics endpoint that will be called periodically
    if not path.endswith("/metrics"):
        # just update metrics
        metrics.rest_api_calls_total.labels(path, response.status_code).inc()
    return response


@app.middleware("http")
async def global_exception_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware to handle uncaught exceptions from all endpoints."""
    try:
        response = await call_next(request)
        return response
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Uncaught exception in endpoint: %s", exc)
        error_response = InternalServerErrorResponse.generic()
        return JSONResponse(
            status_code=error_response.status_code,
            content={"detail": error_response.detail.model_dump()},
        )


logger.info("Including routers")
routers.include_routers(app)

app_routes_paths = [
    route.path
    for route in app.routes
    if isinstance(route, (Mount, Route, WebSocketRoute))
]
