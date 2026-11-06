"""Fixtures shared by the unit and integration test suites."""

import pytest


@pytest.fixture(
    name="reference_prefix", params=["", "env."], ids=["short", "canonical"]
)
def reference_prefix_fixture(request: pytest.FixtureRequest) -> str:
    """Exercise both environment-reference spellings."""
    return str(request.param)
