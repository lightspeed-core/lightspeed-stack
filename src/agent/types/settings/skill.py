"""Skill settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass

from configuration import configuration
from models.api.requests import QueryRequest


@dataclass
class SkillSettings:
    """Settings for a skill."""

    path: str
    enabled: bool | list[str] = True

    @classmethod
    def from_query_request(
        cls, request: QueryRequest  # pylint: disable=unused-argument
    ) -> list[SkillSettings]:
        """Build skill settings from the loaded skills configuration.

        The query does not select skills. ``request`` is accepted so every
        setting is built the same way.

        Parameters:
            request: Incoming query. Skill selection does not read it.

        Returns:
            One enabled skill setting per configured path, or an empty list
            when skills are not configured.

        """
        skills = configuration.skills
        if skills is None:
            return []
        return [cls(path=str(path)) for path in skills.paths]
