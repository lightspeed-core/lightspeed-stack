"""Structured HTTP error response models for OpenAPI documentation."""

from lightspeed_stack.models.api.responses.error.bad_request import BadRequestResponse
from lightspeed_stack.models.api.responses.error.bases import (
    AbstractErrorResponse,
    DetailModel,
)
from lightspeed_stack.models.api.responses.error.conflict import ConflictResponse
from lightspeed_stack.models.api.responses.error.content_too_large import (
    FileTooLargeResponse,
    PromptTooLongResponse,
)
from lightspeed_stack.models.api.responses.error.forbidden import ForbiddenResponse
from lightspeed_stack.models.api.responses.error.internal import (
    InternalServerErrorResponse,
)
from lightspeed_stack.models.api.responses.error.not_found import NotFoundResponse
from lightspeed_stack.models.api.responses.error.service_unavailable import (
    ServiceUnavailableResponse,
)
from lightspeed_stack.models.api.responses.error.too_many_requests import (
    QuotaExceededResponse,
)
from lightspeed_stack.models.api.responses.error.unauthorized import (
    UnauthorizedResponse,
)
from lightspeed_stack.models.api.responses.error.unprocessable_entity import (
    UnprocessableEntityResponse,
)

__all__ = [
    "AbstractErrorResponse",
    "BadRequestResponse",
    "ConflictResponse",
    "DetailModel",
    "FileTooLargeResponse",
    "ForbiddenResponse",
    "InternalServerErrorResponse",
    "NotFoundResponse",
    "PromptTooLongResponse",
    "QuotaExceededResponse",
    "ServiceUnavailableResponse",
    "UnauthorizedResponse",
    "UnprocessableEntityResponse",
]
