"""Decorator that makes sure the object is 'connected' according to it's connected predicate."""

from collections.abc import Callable
from typing import (
    Concatenate,
    ParamSpec,
    Protocol,
    TypeVar,
    runtime_checkable,
)

P = ParamSpec("P")
R = TypeVar("R")
S = TypeVar("S", bound="Connectable")  # the method's self type


@runtime_checkable
class Connectable(Protocol):
    """Any class that implements methods connected and connect."""

    def connected(self) -> bool:
        """Check if DB is connected."""
        return False

    def connect(self) -> None:
        """Connect or reconnect the database."""


def connection(
    f: Callable[Concatenate[S, P], R],
) -> Callable[..., R]:
    """
    Ensure a connectable object is connected before invoking the wrapped method.

    The returned wrapper calls `connectable.connected()` and, if that returns
    `False`, calls `connectable.connect()` prior to delegating to the original
    method.

    Parameters:
    ----------
        f (Callable): The method to wrap. The wrapped method is
        expected to accept a `connectable` first argument.

    Returns:
    -------
        Callable: A wrapper method with signature `(connectable,
        *args, **kwargs)` that ensures `connectable` is connected
        before calling `f`.

    Example:
    ```python
    @connection
    def list_history(self) -> list[str]:
       pass
    ```
    """

    def wrapper(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Ensure the provided connectable is connected, then call the wrapped with the same arguments.

        Parameters:
        ----------
            connectable (Any): Object that implements `connected()` -> bool and
            `connect()` -> None; will be connected if not already.
                *args (Any): Positional arguments forwarded to the wrapped callable.
                **kwargs (Any): Keyword arguments forwarded to the wrapped callable.

        Returns:
        -------
                Any: The value returned by the wrapped callable.
        """
        if not self.connected():
            self.connect()
        return f(self, *args, **kwargs)

    return wrapper
