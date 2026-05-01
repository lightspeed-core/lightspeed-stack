"""Structured HTTP error response models for OpenAPI documentation."""

from models.api.responses.error.bad_request import BadRequestResponse
from models.api.responses.error.bases import AbstractErrorResponse, DetailModel
from models.api.responses.error.conflict import ConflictResponse
from models.api.responses.error.content_too_large import (
    FileTooLargeResponse,
    PromptTooLongResponse,
)
from models.api.responses.error.forbidden import ForbiddenResponse
from models.api.responses.error.internal import InternalServerErrorResponse
from models.api.responses.error.not_found import NotFoundResponse
from models.api.responses.error.service_unavailable import ServiceUnavailableResponse
from models.api.responses.error.too_many_requests import QuotaExceededResponse
from models.api.responses.error.unauthorized import UnauthorizedResponse
from models.api.responses.error.unprocessable_entity import UnprocessableEntityResponse

__all__ = [
    "AbstractErrorResponse",
    "BadRequestResponse",
    "ConflictResponse",
    "DetailModel",
    "ForbiddenResponse",
    "InternalServerErrorResponse",
    "NotFoundResponse",
    "PromptTooLongResponse",
    "FileTooLargeResponse",
    "QuotaExceededResponse",
    "ServiceUnavailableResponse",
    "UnauthorizedResponse",
    "UnprocessableEntityResponse",
]
