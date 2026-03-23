"""Decorator that makes sure the object is 'connected' according to it's connected predicate."""

from collections.abc import Callable
from typing import Any


def connection(f: Callable) -> Callable:
    """
    Ensure a connectable object is connected before invoking the wrapped function.

    The returned wrapper calls `connectable.connected()` and, if that returns
    `False`, calls `connectable.connect()` prior to delegating to the original
    function.

    Parameters:
        f (Callable): The function to wrap. The wrapped function is
        expected to accept a `connectable` first argument.

    Returns:
        Callable: A wrapper function with signature `(connectable,
        *args, **kwargs)` that ensures `connectable` is connected
        before calling `f`.

    Example:
    ```python
    @connection
    def list_history(self) -> list[str]:
       pass
    ```
    """

    def wrapper(connectable: Any, *args: Any, **kwargs: Any) -> Callable:
        """
        Ensure the provided connectable is connected, then call the wrapped with the same arguments.

        Parameters:
            connectable (Any): Object that implements `connected()` -> bool and
            `connect()` -> None; will be connected if not already.
                *args (Any): Positional arguments forwarded to the wrapped callable.
                **kwargs (Any): Keyword arguments forwarded to the wrapped callable.

        Returns:
                Any: The value returned by the wrapped callable.
        """
        if not connectable.connected():
            connectable.connect()
        return f(connectable, *args, **kwargs)

    return wrapper
