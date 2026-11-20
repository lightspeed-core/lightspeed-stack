"""Unit tests for skill capability construction."""

from pytest_mock import MockerFixture

from agent.capabilities.skills.factory import SkillFactory
from agent.types.settings import SkillSettings


def test_no_enabled_skills_build_nothing(mocker: MockerFixture) -> None:
    """An empty list or only disabled skills produce no capability."""
    skills = mocker.patch("agent.capabilities.skills.factory.SkillsCapability")

    assert SkillFactory.build_capabilities([]) is None
    assert (
        SkillFactory.build_capabilities(
            [
                SkillSettings(path="/skills/off", enabled=False),
                SkillSettings(path="/skills/none", enabled=[]),
            ]
        )
        is None
    )

    skills.assert_not_called()


def test_enabled_paths_are_passed_to_the_capability(mocker: MockerFixture) -> None:
    """Enabled skill paths become one capability, including a non-empty tool list."""
    skills = mocker.patch("agent.capabilities.skills.factory.SkillsCapability")

    capability = SkillFactory.build_capabilities(
        [
            SkillSettings(path="/skills/off", enabled=False),
            SkillSettings(path="/skills/one"),
            SkillSettings(path="/skills/filtered", enabled=["run_skill_script"]),
        ]
    )

    assert capability is skills.return_value
    skills.assert_called_once_with(
        directories=["/skills/one", "/skills/filtered"],
        validate=False,
        exclude_tools=["run_skill_script"],
    )
