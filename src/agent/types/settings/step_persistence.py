"""Step persistence settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass

from models.api.requests import QueryRequest


@dataclass
class StepPersistenceSettings:
    """Settings for step persistence."""

    enabled: bool = True

    @classmethod
    def from_query_request(
        cls, request: QueryRequest  # pylint: disable=unused-argument
    ) -> StepPersistenceSettings:
        """Build step persistence settings for a query.

        The query does not select step persistence. ``request`` is accepted so
        every setting is built the same way. Persistence stays enabled; the
        history service returns no capability when the store is a no-op.

        Parameters:
            request: Incoming query. Step persistence selection does not read it.

        Returns:
            Step persistence settings with ``enabled`` set to True.

        """
        return cls()
