"""Domain exceptions for the prompts module."""


class PromptError(Exception):
    """Base class for prompt domain errors."""


class PromptValidationError(PromptError):
    """Invalid prompt field values."""


class PromptNotFoundError(PromptError):
    """No prompt exists for the given identifier."""


class PromptRenderError(PromptError):
    """Prompt rendering error."""
