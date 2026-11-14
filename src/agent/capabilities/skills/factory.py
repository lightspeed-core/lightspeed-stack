"""Factory for building skill capabilities from skill settings."""

from typing import Optional

from pydantic_ai_skills import SkillsCapability

from agent.types.settings import SkillSettings


class SkillFactory:
    """Factory for building skill capabilities."""

    @staticmethod
    def build_capabilities(settings: list[SkillSettings]) -> Optional[SkillsCapability]:
        """Build a skill capability from all skill settings.

        Parameters:
            settings: Skill settings to turn into a capability.

        Returns:
            One skill capability covering every enabled skill path, or
            ``None`` when no skills are enabled.

        """
        enabled_settings = [setting for setting in settings if setting.enabled]

        if not enabled_settings:
            return None

        return SkillsCapability(
            directories=[setting.path for setting in enabled_settings],
            validate=False,
            exclude_tools=["run_skill_script"],
        )
