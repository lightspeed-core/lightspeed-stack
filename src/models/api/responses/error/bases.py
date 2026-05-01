"""Base Pydantic types for OpenAPI-aligned structured API error responses."""

from typing import Any, Optional

from pydantic import BaseModel, Field
from pydantic_core import SchemaError


class DetailModel(BaseModel):
    """Nested detail model for error responses."""

    response: str = Field(..., description="Short summary of the error")
    cause: str = Field(..., description="Detailed explanation of what caused the error")


class AbstractErrorResponse(BaseModel):
    """Base class for error responses.

    Attributes:
        status_code: HTTP status code for the error response.
        detail: The detail model containing error summary and cause.
    """

    status_code: int = Field(
        ..., description="HTTP status code for the errors response"
    )
    detail: DetailModel = Field(
        ..., description="The detail model containing error summary and cause"
    )

    def __init__(self, *, response: str, cause: str, status_code: int) -> None:
        """Create an error response model with an HTTP status code and detailed message.

        Args:
            response: A short, user-facing summary of the error.
            cause: A more detailed explanation of the error cause.
            status_code: The HTTP status code to associate with this error response.
        """
        super().__init__(
            status_code=status_code, detail=DetailModel(response=response, cause=cause)
        )

    @classmethod
    def get_description(cls) -> str:
        """Retrieve the class description.

        Returns:
            The class description attribute if present; otherwise the class
            docstring; if neither is present, an empty string.
        """
        return getattr(cls, "description", cls.__doc__ or "")

    @classmethod
    def openapi_response(cls, examples: Optional[list[str]] = None) -> dict[str, Any]:
        """Build an OpenAPI/FastAPI response dictionary that exposes the model's labeled examples.

        Extracts examples from the model's JSON schema and includes them as
        named application/json examples in the returned response mapping. If
        the optional examples list is provided, only examples whose labels
        appear in that list are included. Each included example is exposed
        under its label with a value containing a detail payload.

        Args:
            examples: If provided, restricts which labeled examples to include by label.

        Returns:
            A response mapping with keys description (the response description),
            model (the model class), and content (a mapping for application/json
            to the examples object).

        Raises:
            SchemaError: If any example in the model schema lacks a label or detail field.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples", [])

        named_examples: dict[str, Any] = {}
        for ex in model_examples:
            label = ex.get("label", None)
            if label is None:
                raise SchemaError(f"Example {ex} in {cls.__name__} has no label")
            if examples is None or label in examples:
                detail = ex.get("detail", None)
                if detail is None:
                    raise SchemaError(f"Example {ex} in {cls.__name__} has no detail")
                named_examples[label] = {"value": {"detail": detail}}

        content: dict[str, Any] = {"application/json": {"examples": named_examples}}

        return {
            "description": cls.get_description(),
            "model": cls,
            "content": content,
        }
