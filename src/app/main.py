"""Definition of FastAPI based web service."""

from typing import Callable, Awaitable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route, WebSocketRoute

from app import routers
from configuration import configuration
from log import get_logger
import metrics
from utils.common import register_mcp_servers_async
import version

logger = get_logger(__name__)

logger.info("Initializing app")

service_name = configuration.configuration.name


app = FastAPI(
    title=f"{service_name} service - OpenAPI",
    description=f"{service_name} service API specification.",
    version=version.__version__,
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


logger.info("Including routers")
routers.include_routers(app)

app_routes_paths = [
    route.path
    for route in app.routes
    if isinstance(route, (Mount, Route, WebSocketRoute))
]


@app.on_event("startup")
async def startup_event() -> None:
    """Perform logger setup on service startup."""
    logger.info("Registering MCP servers")
    await register_mcp_servers_async(logger, configuration.configuration)
    get_logger("app.endpoints.handlers")
    logger.info("App startup complete")
