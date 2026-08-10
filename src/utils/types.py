"""Common types for the project."""

from re import Pattern
from typing import Any, TypeVar, cast

from ogx_api import ImageContentItem, TextContentItem

type SingletonInstances = dict[type, object]

CompiledPatterns = list[tuple[Pattern[str], str]]

T = TypeVar("T")


def content_to_str(content: Any) -> str:
    """Convert content (str, TextContentItem, ImageContentItem, or list) to string.

    Parameters:
    ----------
        content: Value to normalize into a string (may be None,
                 str, content item, list, or any other object).

    Returns:
    -------
        str: The normalized string representation of the content.
    """
    match content:
        case None:
            return ""
        case str():
            return content
        case TextContentItem():
            # help the type checkers to infer return data type
            return str(content.text)
        case ImageContentItem():
            return "<image>"
        case list():
            return " ".join(content_to_str(item) for item in content)
        case _:
            return str(content)


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
