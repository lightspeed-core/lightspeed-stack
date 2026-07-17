"""Unit tests for the connection decorator."""

import pytest

from lightspeed_stack.utils.connection_decorator import connection


class SomeActionException(Exception):
    """Exception type used by unit test."""


class Connectable:
    """Class used to test connection decorator."""

    def __init__(self, raise_exception_from_foo: bool):
        """Initialize class used to test connection decorator."""
        self._raise_exception_from_foo = raise_exception_from_foo
        self._connected = False

    def connected(self) -> bool:
        """Predicate if connection is alive."""
        return self._connected

    def connect(self) -> None:
        """Connect."""
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect."""
        self._connected = False

    @connection
    def some_action(self) -> None:
        """Perform any action, but with active connection."""
        if self._raise_exception_from_foo:
            raise SomeActionException("some_action error!")


def test_connection_decorator() -> None:
    """Test the connection decorator."""
    c = Connectable(raise_exception_from_foo=False)
    c.disconnect()
    assert c.connected() is False

    # this method should autoconnect
    c.some_action()
    assert c.connected() is True


def test_connection_decorator_on_connection_exception() -> None:
    """Test the connection decorator."""
    c = Connectable(raise_exception_from_foo=True)
    c.disconnect()
    assert c.connected() is False

    with pytest.raises(SomeActionException, match="some_action error!"):
        # this method should autoconnect
        c.some_action()
