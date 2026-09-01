"""Common types for the project."""

from re import Pattern
from typing import Any

type SingletonInstances = dict[type, Any]

CompiledPatterns = list[tuple[Pattern[str], str]]


class Singleton(type):
    """Metaclass for Singleton support."""

    _instances: SingletonInstances = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """
        Return the single cached instance of the class, creating and caching it on first call.

        Returns:
            object: The singleton instance for this class.
        """
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
