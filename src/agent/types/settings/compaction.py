"""Compaction settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass

from configuration import configuration
from models.api.requests import QueryRequest


@dataclass
class CompactionSettings:
    """Settings for compaction."""

    enabled: bool = True

    @classmethod
    def from_query_request(
        cls, request: QueryRequest  # pylint: disable=unused-argument
    ) -> CompactionSettings:
        """Build compaction settings from the loaded compaction configuration.

        The query does not select compaction. ``request`` is accepted so every
        setting is built the same way.

        Parameters:
            request: Incoming query. Compaction selection does not read it.

        Returns:
            Compaction settings whose ``enabled`` flag matches configuration.

        """
        return cls(enabled=configuration.compaction.enabled)
