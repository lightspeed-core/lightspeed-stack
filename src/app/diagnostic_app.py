"""Minimal diagnostic FastAPI app for when configuration fails."""

from fastapi import FastAPI
from app.endpoints import health
import version


def create_diagnostic_app() -> FastAPI:
    """
    Create a minimal diagnostic FastAPI app with only health endpoints.
    
    This app is used when configuration loading fails, providing basic
    health reporting capabilities for troubleshooting.
    
    Returns:
        FastAPI: Minimal app with only health endpoints
    """
    app = FastAPI(
        title="Lightspeed Stack - Diagnostic Mode",
        summary="Minimal diagnostic server for troubleshooting",
        description="Limited service running in diagnostic mode due to configuration issues",
        version=version.__version__,
        contact={
            "name": "Red Hat",
            "url": "https://www.redhat.com/",
        },
        license_info={
            "name": "Apache 2.0", 
            "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
        },
    )
    
    # Only include health endpoints - no authentication required
    app.include_router(health.router)
    
    return app


# Export the diagnostic app instance
diagnostic_app = create_diagnostic_app()
