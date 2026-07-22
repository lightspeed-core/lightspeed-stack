"""Common types for the project."""

from re import Pattern
from typing import Any

from ogx_api import ImageContentItem, TextContentItem

type SingletonInstances = dict[type, Any]

CompiledPatterns = list[tuple[Pattern[str], str]]


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

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """
        Return the single cached instance of the class, creating and caching it on first call.

        Returns:
            object: The singleton instance for this class.
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
