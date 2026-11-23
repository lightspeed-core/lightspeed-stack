"""Generic FastAPI handler that turns mapped domain exceptions into HTTP errors."""

from collections.abc import Callable, Mapping

from fastapi import Request
from fastapi.responses import JSONResponse

from log import get_logger
from models.api.responses.error import InternalServerErrorResponse
from models.api.responses.error.bases import AbstractErrorResponse

logger = get_logger(__name__)


def _http_exception_body(error: AbstractErrorResponse) -> JSONResponse:
    """Return status and detail in the same shape as a raised HTTPException.

    Args:
        error: OpenAPI-aligned error model with status_code and detail.

    Returns:
        JSON response whose body wraps detail under the detail key.

    """
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail.model_dump()},
    )


def module_exception_handler(
    mappings: Mapping[type, Callable[..., AbstractErrorResponse]],
) -> Callable[[Request, Exception], JSONResponse]:
    """Create a FastAPI exception handler for one module mapping table.

    Args:
        mappings: Exact exception type to HTTP response builder for one domain.

    Returns:
        Handler that looks up the concrete exception type and builds the response.

    """

    def handler(request: Request, exc: Exception) -> JSONResponse:
        builder = mappings.get(type(exc))
        if builder is None:
            logger.error(
                "Unmapped %s with no HTTP translation",
                type(exc).__name__,
                exc_info=exc,
            )
            return _http_exception_body(InternalServerErrorResponse.generic())

        return _http_exception_body(builder(request, exc))

    return handler
