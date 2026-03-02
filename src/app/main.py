"""Definition of FastAPI based web service."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from llama_stack_client import APIConnectionError
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import metrics
import version
from a2a_storage import A2AStorageFactory
from app import routers
from app.database import create_tables, initialize_database
from authorization.azure_token_manager import AzureEntraIDManager
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

    azure_config = configuration.configuration.azure_entra_id
    if azure_config is not None:
        AzureEntraIDManager().set_config(azure_config)
        if not AzureEntraIDManager().refresh_token():
            logger.warning(
                "Failed to refresh Azure token at startup. "
                "Token refresh will be retried on next Azure request."
            )

    llama_stack_config = configuration.configuration.llama_stack
    await AsyncLlamaStackClientHolder().load(llama_stack_config)
    client = AsyncLlamaStackClientHolder().get_client()
    # check if the Llama Stack version is supported by the service
    try:
        await check_llama_stack_version(client)
    except APIConnectionError as e:
        llama_stack_url = llama_stack_config.url
        logger.error(
            "Failed to connect to Llama Stack at '%s'. "
            "Please verify that the 'llama_stack.url' configuration is correct "
            "and that the Llama Stack service is running and accessible. "
            "Original error: %s",
            llama_stack_url,
            e,
        )
        raise

    logger.info("Registering MCP servers")
    await register_mcp_servers_async(logger, configuration.configuration)
    logger.info("App startup complete")

    initialize_database()
    create_tables()

    yield

    # Cleanup resources on shutdown
    await A2AStorageFactory.cleanup()
    logger.info("App shutdown complete")


app = FastAPI(
    root_path=configuration.service_configuration.root_path,
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


class RestApiMetricsMiddleware:  # pylint: disable=too-few-public-methods
    """Pure ASGI middleware for REST API metrics.

    Record REST API request metrics for application routes and forward the
    request to the next ASGI handler.

    Only requests whose path is listed in the application's routes are
    measured.  For measured requests, this middleware records request duration
    and increments a per-path / per-status counter; it does not increment
    counters for the ``/metrics`` endpoint.

    This is implemented as a pure ASGI middleware (instead of using Starlette's
    ``BaseHTTPMiddleware``) to avoid the ``RuntimeError: No response returned``
    bug that occurs when ``call_next`` is used with long-running handlers such
    as LLM inference.  See https://issues.redhat.com/browse/RSPEED-2413.
    """

    def __init__(self, app: ASGIApp) -> None:  # pylint: disable=redefined-outer-name
        """Initialize the middleware."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an ASGI request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        logger.debug("Received request for path: %s", path)

        # Ignore paths that are not part of the app routes.
        if path not in app_routes_paths:
            await self.app(scope, receive, send)
            return

        logger.debug("Processing API request for path: %s", path)

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        # Measure duration and forward the request.  Use try/finally so the
        # call counter is always incremented, even when the inner app raises.
        try:
            with metrics.response_duration_seconds.labels(path).time():
                await self.app(scope, receive, send_wrapper)
        finally:
            # Ignore /metrics endpoint that will be called periodically.
            if not path.endswith("/metrics"):
                metrics.rest_api_calls_total.labels(path, status_code).inc()


class GlobalExceptionMiddleware:  # pylint: disable=too-few-public-methods
    """Pure ASGI middleware to handle uncaught exceptions from all endpoints.

    This is implemented as a pure ASGI middleware (instead of using Starlette's
    ``BaseHTTPMiddleware``) to avoid the ``RuntimeError: No response returned``
    bug that occurs when ``call_next`` is used with long-running handlers such
    as LLM inference.  See https://issues.redhat.com/browse/RSPEED-2413.
    """

    def __init__(self, app: ASGIApp) -> None:  # pylint: disable=redefined-outer-name
        """Initialize the middleware."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an ASGI request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except HTTPException:
            raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Uncaught exception in endpoint: %s", exc)
            if response_started:
                raise
            error_response = InternalServerErrorResponse.generic()
            response = JSONResponse(
                status_code=error_response.status_code,
                content={"detail": error_response.detail.model_dump()},
            )
            await response(scope, receive, send)


logger.info("Including routers")
routers.include_routers(app)

app_routes_paths = [
    route.path
    for route in app.routes
    if isinstance(route, (Mount, Route, WebSocketRoute))
]

# Register pure ASGI middlewares.  Middleware execution order is the reverse of
# registration order: GlobalExceptionMiddleware (registered first) is innermost,
# RestApiMetricsMiddleware (registered last) is outermost.  This ensures metrics
# always observe a status code — including 500s synthesised by the exception
# middleware — rather than seeing a raw exception with no response.
app.add_middleware(GlobalExceptionMiddleware)
app.add_middleware(RestApiMetricsMiddleware)
