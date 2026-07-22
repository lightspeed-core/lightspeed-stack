"""Unit tests for SkillsConfiguration model."""

# pylint: disable=no-member
# Pydantic Field(default_factory=...) pattern confuses pylint's static analysis

from pathlib import Path

import pytest
from pydantic import ValidationError

from lightspeed_stack.models.config import SkillsConfiguration


class TestSkillsConfiguration:
    """Tests for SkillsConfiguration model."""

    def test_empty_paths_list(self) -> None:
        """Test that an explicit empty paths list is allowed."""
        config = SkillsConfiguration(paths=[])
        assert config.paths == []

    def test_no_unknown_fields_allowed(self) -> None:
        """Test that SkillsConfiguration rejects unknown fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SkillsConfiguration(unknown_field="value")  # type: ignore[call-arg]

    def test_skill_paths(self) -> None:
        """Test configuration with multiple skill paths."""
        config = SkillsConfiguration(
            paths=[
                "/var/skills/openshift-troubleshooting",
                "/var/skills/code-review",
                "/opt/custom-skills",
            ]
        )
        assert len(config.paths) == 3
        assert Path("/var/skills/openshift-troubleshooting") in config.paths
        assert Path("/var/skills/code-review") in config.paths
        assert Path("/opt/custom-skills") in config.paths

    def test_mixed_absolute_and_relative_paths(self) -> None:
        """Test that both absolute and relative paths can be mixed."""
        config = SkillsConfiguration(
            paths=["/var/skills", "./local-skills", "/opt/skills"]
        )
        assert len(config.paths) == 3
        assert Path("/var/skills") in config.paths
        assert Path("./local-skills") in config.paths
        assert Path("/opt/skills") in config.paths
