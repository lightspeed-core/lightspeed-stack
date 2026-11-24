"""Unit tests for skill settings built from configuration."""

from pathlib import Path
from types import SimpleNamespace

from pytest_mock import MockerFixture

from agent.types.settings.skill import SkillSettings
from models.api.requests import QueryRequest
from models.config import SkillsConfiguration


def _query() -> QueryRequest:
    """Build a query. Skill selection does not read it."""
    return QueryRequest(query="What is Kubernetes?")


def test_configured_paths_are_enabled(mocker: MockerFixture) -> None:
    """Each configured skill path becomes an enabled skill setting."""
    mocker.patch(
        "agent.types.settings.skill.configuration",
        SimpleNamespace(
            skills=SkillsConfiguration(paths=[Path("skills/one"), Path("skills/two")])
        ),
    )

    settings = SkillSettings.from_query_request(_query())

    assert settings == [
        SkillSettings(path="skills/one", enabled=True),
        SkillSettings(path="skills/two", enabled=True),
    ]


def test_missing_skills_configuration_yields_no_settings(
    mocker: MockerFixture,
) -> None:
    """Skills that are not configured produce an empty list."""
    mocker.patch(
        "agent.types.settings.skill.configuration",
        SimpleNamespace(skills=None),
    )

    assert SkillSettings.from_query_request(_query()) == []
