"""Definition of FastAPI based web service."""

from fastapi import FastAPI
from app import routers

import version
from log import get_logger
from configuration import configuration
from utils.common import register_mcp_servers_async
from services.data_collector import data_collector_service

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

logger.info("Including routers")
routers.include_routers(app)


@app.on_event("startup")
async def startup_event() -> None:
    """Perform logger setup on service startup."""
    logger.info("Registering MCP servers")
    await register_mcp_servers_async(logger, configuration.configuration)
    get_logger("app.endpoints.handlers")
    await data_collector_service.start()
    logger.info("App startup complete")

@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Perform cleanup on service shutdown."""
    logger.info("Shutting down services")
    await data_collector_service.stop()
    logger.info("App shutdown complete")