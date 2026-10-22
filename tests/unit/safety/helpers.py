"""Shared builders for safety unit tests."""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage


def run_context(**overrides: Any) -> RunContext[Any]:
    """Build a run context, overriding any of the default fields."""
    kwargs: dict[str, Any] = {
        "deps": None,
        "model": TestModel(),
        "usage": RunUsage(),
    }
    kwargs.update(overrides)
    return RunContext(**kwargs)


def request_context(messages: list[ModelMessage]) -> ModelRequestContext:
    """Wrap a message list in a model request context without copying it."""
    return ModelRequestContext(
        model=TestModel(),
        messages=messages,
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )
