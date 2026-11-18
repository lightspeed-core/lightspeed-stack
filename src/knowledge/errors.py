"""Exceptions raised by the knowledge source registry."""


class DuplicateKnowledgeSourceError(Exception):
    """Raised when a knowledge source name is already registered."""

    def __init__(self, name: str) -> None:
        """Initialize with the name that was already registered.

        Args:
            name: Knowledge source name that collided.

        """
        super().__init__(f"Knowledge source {name!r} is already registered")
        self.name = name


class KnowledgeSourceNotFoundError(Exception):
    """Raised when no knowledge source is registered for the requested name."""

    def __init__(self, name: str) -> None:
        """Initialize with the unknown source name.

        Args:
            name: Knowledge source name from configuration.

        """
        super().__init__(f"Knowledge source {name!r} is not registered")
        self.name = name
