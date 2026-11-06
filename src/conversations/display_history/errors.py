"""Errors raised when display history cannot be saved or loaded."""


class DisplayHistoryDatabaseError(Exception):
    """A database operation for display history failed."""

    def __init__(self, operation: str) -> None:
        """Record which persistence action failed."""
        self.operation = operation
        super().__init__(f"Display history {operation} failed")
