"""Base classes for successful API response models."""

from typing import Any, ClassVar

from pydantic import BaseModel, Field, computed_field
from pydantic_core import SchemaError

from log import get_logger
from models.api.responses.constants import SUCCESSFUL_RESPONSE_DESCRIPTION

logger = get_logger(__name__)


class AbstractSuccessfulResponse(BaseModel):
    """Base class for all successful response models."""

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Generate FastAPI response dict with a single example from model_config."""
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")
        example_value = model_examples[0]
        content = {"application/json": {"example": example_value}}

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": content,
        }


class AbstractDeleteResponse(BaseModel):
    """Base model for successful delete responses."""

    deleted: bool = Field(
        ...,
        description="Whether the deletion was successful.",
        examples=[True, False],
    )
    resource_name: ClassVar[str]

    @computed_field
    def response(self) -> str:
        """Human-readable outcome of the delete operation."""
        return (
            f"{self.resource_name} deleted successfully"
            if self.deleted
            else f"{self.resource_name} not found"
        )

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Build FastAPI/OpenAPI metadata with named application/json examples.

        Returns:
            A response dict with description, model, and content keys.

        Raises:
            SchemaError: If the model JSON schema has no examples list.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")

        examples: dict[str, dict[str, Any]] = {}
        for index, example in enumerate(model_examples):
            if "label" not in example:
                raise SchemaError(
                    f"Example at index {index} in {cls.__name__} has no label"
                )
            if "value" not in example:
                raise SchemaError(
                    f"Example at index {index} in {cls.__name__} has no value"
                )
            examples[example["label"]] = {"value": example["value"]}

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": {"application/json": {"examples": examples}},
        }
