"""Shield settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass

from configuration import configuration
from models.api.requests import QueryRequest


def _enabled_for_request(requested: list[str] | None, item_id: str) -> bool:
    """Return whether one configured id stays enabled for this request.

    ``None`` leaves every configured id enabled. An empty list disables every
    id. Otherwise an id stays enabled when it appears in the request.

    Parameters:
        requested: Ids from the query, or ``None`` when the field was omitted.
        item_id: Configured id being considered.

    Returns:
        ``True`` when the id should stay enabled.

    """
    if requested is None:
        return True
    return item_id in requested


@dataclass
class ShieldSettings:
    """Settings for a shield."""

    id: str
    enabled: bool = True

    @classmethod
    def from_query_request(cls, request: QueryRequest) -> list[ShieldSettings]:
        """Build shield settings for every configured shield.

        Parameters:
            request: Incoming query. ``shield_ids`` of ``None`` leaves every
                shield enabled. An empty list disables every shield. Otherwise
                only the named shields stay enabled.

        Returns:
            One shield setting per configured shield, with ``enabled`` set
            from the request.

        """
        return [
            cls(
                id=shield.name,
                enabled=_enabled_for_request(request.shield_ids, shield.name),
            )
            for shield in configuration.shields
        ]
