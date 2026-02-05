"""Definition of FastAPI based web service."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from llama_stack_client import APIConnectionError
from starlette.routing import Mount, Route, WebSocketRoute
from llama_stack_client import APIConnectionError

from authorization.azure_token_manager import AzureEntraIDManager
import metrics
import version
from app import routers
from app.database import create_tables, initialize_database
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from a2a_storage import A2AStorageFactory
from models.responses import InternalServerErrorResponse, ServiceUnavailableResponse

# from utils.common import register_mcp_servers_async  # Not needed for Responses API
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

    # Log MCP server configuration
    mcp_servers = configuration.configuration.mcp_servers
    if mcp_servers:
        logger.info("Loaded %d MCP server(s) from configuration:", len(mcp_servers))
        for server in mcp_servers:
            has_auth = bool(server.authorization_headers)
            logger.info(
                "  - %s at %s (auth: %s)",
                server.name,
                server.url,
                "yes" if has_auth else "no",
            )
            # Debug: Show auth header names if configured
            if has_auth:
                logger.debug(
                    "    Auth headers: %s",
                    ", ".join(server.authorization_headers.keys()),
                )
    else:
        logger.info("No MCP servers configured")

    # NOTE: MCP server registration not needed for Responses API
    # The Responses API takes inline tool definitions instead of pre-registered toolgroups
    # logger.info("Registering MCP servers")
    # await register_mcp_servers_async(logger, configuration.configuration)
    # get_logger("app.endpoints.handlers")
    logger.info("App startup complete")

    initialize_database()
    create_tables()

    yield

    # Cleanup resources on shutdown
    # Wait for pending background tasks to complete before shutting down
    # Import here to avoid circular dependency issues at module load time
    from app.endpoints.query import (  # pylint: disable=import-outside-toplevel
        background_tasks_set as query_bg_tasks,
    )
    from app.endpoints.streaming_query_v2 import (  # pylint: disable=import-outside-toplevel
        background_tasks_set as streaming_bg_tasks,
    )

    if query_bg_tasks or streaming_bg_tasks:
        logger.info(
            "Waiting for background tasks to complete (query: %d, streaming: %d)",
            len(query_bg_tasks),
            len(streaming_bg_tasks),
        )
        all_tasks = list(query_bg_tasks) + list(streaming_bg_tasks)
        await asyncio.gather(*all_tasks, return_exceptions=True)
        logger.info("All background tasks completed")

    await A2AStorageFactory.cleanup()
    logger.info("App shutdown complete")


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


# ============================================================================
# Pure ASGI Middleware Implementation
# ============================================================================
#
# WHY THIS CHANGE WAS NECESSARY:
#
# Problem: FastAPI's @app.middleware("http") decorator uses Starlette's
# BaseHTTPMiddleware, which has critical bugs that cause production issues:
#
# 1. RuntimeError: "No response returned" with streaming responses
# 2. Exceptions don't propagate correctly through middleware chain
# 3. Background tasks can fail or behave unpredictably
# 4. Memory leaks with large responses
# 5. Context variables leak between requests under high concurrency
#
# See: https://github.com/encode/starlette/issues/1678
#
# SOLUTION: Pure ASGI Middleware
#
# Instead of using the @app.middleware("http") decorator, we implement
# middleware as pure ASGI callable classes with __call__(scope, receive, send).
# This gives us direct control over the ASGI protocol without buggy abstractions.
#
# ASGI (Asynchronous Server Gateway Interface) is the low-level protocol that
# FastAPI/Starlette use to communicate with ASGI servers (like Uvicorn). By
# implementing the ASGI interface directly, we bypass BaseHTTPMiddleware entirely.
#
# Benefits:
# ✅ No "No response returned" errors with streaming endpoints
# ✅ Proper exception handling at the ASGI level
# ✅ Better performance (fewer abstraction layers)
# ✅ Recommended approach by Starlette maintainers
# ✅ Works reliably with all response types (streaming, SSE, websockets)
#
# Implementation Details:
# - MetricsMiddleware: Collects Prometheus metrics (duration, status codes)
# - ExceptionMiddleware: Global exception handler for uncaught errors
# - Both implement __call__(scope, receive, send) for direct ASGI control
# - Applied at the end after routers are registered (see lines 356-358)
#
# ============================================================================


# Pure ASGI Middleware Classes
class MetricsMiddleware:  # pylint: disable=too-few-public-methods
    """Pure ASGI middleware for REST API metrics collection.

    Collects Prometheus metrics for all monitored API endpoints:
    - response_duration_seconds: Histogram of request processing time
    - rest_api_calls_total: Counter of requests by endpoint and status code

    This middleware wraps the ASGI application and intercepts HTTP requests
    to measure their performance characteristics.
    """

    def __init__(  # pylint: disable=redefined-outer-name
        self, app: Any, app_routes_paths: list[str]
    ) -> None:
        """Initialize metrics middleware.

        Parameters:
            app: The ASGI application instance to wrap
            app_routes_paths: List of route paths to monitor (others ignored)
        """
        self.app = app
        self.app_routes_paths = app_routes_paths

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Handle ASGI request/response cycle with metrics collection.

        This is the ASGI interface. The method receives:
        - scope: Request metadata (type, path, headers, method, etc.)
        - receive: Async callable to get messages from client
        - send: Async callable to send messages to client

        We wrap the send callable to intercept the response status code.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Match request path against route templates (handles parameterized routes)
        # Use template path for metrics to avoid cardinality explosion
        route_path = None
        for route_template in self.app_routes_paths:
            # Simple parameterized route matching: check if path segments match template
            # This handles routes like /conversations/{conversation_id}
            path_parts = path.strip("/").split("/")
            template_parts = route_template.strip("/").split("/")

            if len(path_parts) == len(template_parts):
                match = all(
                    tp.startswith("{")
                    and tp.endswith("}")  # Template parameter
                    or tp == pp  # Exact match
                    for tp, pp in zip(template_parts, path_parts)
                )
                if match:
                    route_path = route_template
                    break

        # Ignore paths not matching any route
        if route_path is None:
            await self.app(scope, receive, send)
            return

        logger.debug(
            "Processing API request for path: %s (route: %s)", path, route_path
        )

        # Track response status code by wrapping send callable
        # ASGI sends responses in two messages:
        # 1. http.response.start (contains status code and headers)
        # 2. http.response.body (contains response content)
        # We intercept message #1 to capture the status code
        status_code = None

        async def send_wrapper(message: dict[str, Any]) -> None:
            """Capture response status code from ASGI messages."""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        # Measure duration and execute (use route template for metric label)
        with metrics.response_duration_seconds.labels(route_path).time():
            await self.app(scope, receive, send_wrapper)

        # Update metrics (ignore /metrics endpoint, use route template for label)
        if status_code and not route_path.endswith("/metrics"):
            metrics.rest_api_calls_total.labels(route_path, status_code).inc()


class ExceptionMiddleware:  # pylint: disable=too-few-public-methods
    """Pure ASGI middleware for global exception handling.

    Catches all unhandled exceptions from endpoints and converts them to
    proper HTTP 500 error responses with standardized JSON format.

    Exception handling strategy:
    - All exceptions: Caught, logged with traceback, converted to 500
    - HTTPException is already handled by FastAPI before reaching this middleware

    This ensures clients always receive a valid JSON response even when
    unexpected errors occur deep in the application code.
    """

    def __init__(self, app: Any) -> None:  # pylint: disable=redefined-outer-name
        """Initialize exception middleware.

        Parameters:
            app: The ASGI application instance to wrap
        """
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Handle ASGI request/response cycle with exception handling.

        Wraps the entire application in a try-except block at the ASGI level.
        Any exception that escapes from endpoints, other middleware, or the
        framework itself will be caught here and converted to a proper error response.

        IMPORTANT: Tracks whether the response has started to avoid ASGI violations.
        If an exception occurs after streaming has begun (http.response.start sent),
        we cannot send a new error response - we can only log the error.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Track whether response has started to prevent ASGI violations
        response_started = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            """Wrap send to track when response starts."""
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except APIConnectionError as exc:
            # Llama Stack connection failure - return 503 so clients know to retry
            logger.error("Llama Stack connection error in middleware: %s", exc)

            if response_started:
                logger.error(
                    "Cannot send 503 response - response already started (likely streaming)"
                )
                return

            # Return 503 Service Unavailable for Llama Stack connection issues
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(exc)
            )

            await send(
                {
                    "type": "http.response.start",
                    "status": error_response.status_code,
                    "headers": [[b"content-type", b"application/json"]],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": error_response.model_dump_json().encode("utf-8"),
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Log unexpected exception with full traceback for debugging
            logger.exception("Uncaught exception in endpoint: %s", exc)

            # If response already started (e.g., streaming), we can't send error response
            # The ASGI spec requires exactly ONE http.response.start per request
            if response_started:
                logger.error(
                    "Cannot send error response - response already started (likely streaming)"
                )
                return

            # Response hasn't started yet - safe to send error response
            error_response = InternalServerErrorResponse.generic()

            # Manually construct ASGI HTTP error response
            # Must send two ASGI messages: start (status/headers) and body (content)
            await send(
                {
                    "type": "http.response.start",
                    "status": error_response.status_code,
                    "headers": [[b"content-type", b"application/json"]],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": JSONResponse(
                        content={"detail": error_response.detail.model_dump()}
                    ).body,
                }
            )


logger.info("Including routers")
routers.include_routers(app)

app_routes_paths = [
    route.path
    for route in app.routes
    if isinstance(route, (Mount, Route, WebSocketRoute))
]

# ============================================================================
# Apply Pure ASGI Middleware Layers
# ============================================================================
#
# IMPORTANT: Middleware is applied in REVERSE order!
# The last middleware added becomes the outermost layer in execution.
#
# Execution order for incoming requests:
#   1. ExceptionMiddleware (outermost - catches ALL exceptions)
#   2. MetricsMiddleware (measures request duration and status)
#   3. CORSMiddleware (applied earlier via add_middleware)
#   4. Authorization middleware (from routers)
#   5. Endpoint handlers (innermost)
#
# Why this order matters:
# - ExceptionMiddleware MUST be outermost to catch exceptions from all layers
# - MetricsMiddleware measures total request time including CORS processing
# - CORS must process OPTIONS requests before hitting endpoints
#
# Technical note:
# We use add_middleware() to register pure ASGI middleware classes with FastAPI.
# This is critical because it ensures they're inserted at the correct position in
# the middleware stack, BEFORE Starlette's internal ServerErrorMiddleware.
#
# If we wrapped the app directly (e.g., `app = ExceptionMiddleware(app)`), our
# middleware would be OUTSIDE of ServerErrorMiddleware, causing a "double response"
# bug where Starlette's error handler sends a response first, and then our
# middleware tries to send another response, resulting in:
#   "AssertionError: Received multiple 'http.response.start' messages"
#
# Using add_middleware() solves this by inserting our middleware INSIDE the
# middleware stack, where it can catch exceptions before ServerErrorMiddleware.
#
# ============================================================================

# Apply ASGI middleware layers using add_middleware()
logger.info("Applying ASGI middleware layers")
app.add_middleware(MetricsMiddleware, app_routes_paths=app_routes_paths)
app.add_middleware(ExceptionMiddleware)
