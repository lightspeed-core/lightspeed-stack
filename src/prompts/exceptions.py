"""Domain exceptions for the prompts module."""


class PromptError(Exception):
    """Base class for prompt domain errors."""


class PromptValidationError(PromptError):
    """Invalid prompt field values."""
