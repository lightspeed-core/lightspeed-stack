"""Integration tests for the /v1/skills endpoint.

Unlike the unit tests in tests/unit/app/endpoints/test_skills.py (which mock
out the whole `configuration` module), these tests load a real configuration
object via the `test_config` fixture and only attach a `SkillsConfiguration`
pointing at skill directories written to a temporary path. This exercises the
real configuration-loaded checks and the real skill-discovery code path
(`utils.pydantic_ai_helpers.get_skills_metadata`) end-to-end.
"""

from pathlib import Path

import pytest
from fastapi import Request

from app.endpoints.skills import skills_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.responses.successful import SkillsResponse
from models.config import SkillsConfiguration


def _write_skill(skills_root: Path, name: str, description: str) -> None:
    """Write a minimal SKILL.md file for one skill.

    Parameters:
        skills_root: Root directory that contains the skill directory.
        name: Skill name, used as both the directory name and frontmatter value.
        description: Skill description written into the frontmatter.

    Returns:
        None.
    """
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nInstructions.\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_skills_endpoint_returns_configured_skills(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    tmp_path: Path,
) -> None:
    """Test that /v1/skills returns metadata for all configured skills.

    Parameters:
    ----------
        test_config: Real loaded configuration (from tests/configuration/lightspeed-stack.yaml).
        test_request: FastAPI request.
        test_auth: noop authentication tuple.
        tmp_path: pytest tmp path fixture used to host real SKILL.md files on disk.
    """
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, "code-review", "Review code for quality and security")
    _write_skill(
        skills_root, "openshift-troubleshooting", "Troubleshoot OpenShift issues"
    )

    test_config.configuration.skills = SkillsConfiguration(paths=[skills_root])

    response = await skills_endpoint_handler(request=test_request, auth=test_auth)

    assert isinstance(response, SkillsResponse)
    assert len(response.skills) == 2
    names = {skill.name for skill in response.skills}
    assert names == {"code-review", "openshift-troubleshooting"}
    for skill in response.skills:
        assert skill.name
        assert skill.description


@pytest.mark.asyncio
async def test_skills_endpoint_returns_empty_list_when_unconfigured(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that /v1/skills returns an empty list when no skills are configured.

    Parameters:
    ----------
        test_config: Real loaded configuration (from tests/configuration/lightspeed-stack.yaml).
        test_request: FastAPI request.
        test_auth: noop authentication tuple.
    """
    test_config.configuration.skills = None

    response = await skills_endpoint_handler(request=test_request, auth=test_auth)

    assert isinstance(response, SkillsResponse)
    assert response.skills == []
