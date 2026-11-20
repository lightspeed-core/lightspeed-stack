"""Compaction settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from configuration import configuration
from models.api.requests import QueryRequest


@dataclass
class CompactionSettings:
    """Settings for compaction."""

    provider: Optional[str] = None
    model: Optional[str] = None
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
        model = request.model or configuration.inference.default_model
        provider = request.provider or configuration.inference.default_provider
        return cls(
            enabled=configuration.compaction.enabled,
            model=model,
            provider=provider,
        )
