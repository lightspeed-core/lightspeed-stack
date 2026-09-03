"""Common types for the project."""

from re import Pattern
from typing import TypeVar, cast

type SingletonInstances = dict[type, object]

CompiledPatterns = list[tuple[Pattern[str], str]]

T = TypeVar("T")


class Singleton(type):
    """Metaclass for Singleton support."""

    _instances: SingletonInstances = {}

    def __call__(cls: type[T], *args: object, **kwargs: object) -> T:
        """
        Return the cached singleton instance, creating it if necessary.

        Returns:
            The singleton instance for this class.
        """
        if cls not in Singleton._instances:
            Singleton._instances[cls] = type.__call__(cls, *args, **kwargs)

        return cast(T, Singleton._instances[cls])
