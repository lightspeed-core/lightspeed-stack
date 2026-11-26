"""Unit tests for shield settings built from a query or Responses request."""

from types import SimpleNamespace

from pytest_mock import MockerFixture

from agent.types.settings.shield import ShieldSettings
from models.api.requests import QueryRequest, ResponsesRequest


def _install(mocker: MockerFixture, names: list[str]) -> None:
    """Point shield settings at shields with the given names."""
    mocker.patch(
        "agent.types.settings.shield.configuration",
        SimpleNamespace(shields=[SimpleNamespace(name=name) for name in names]),
    )


def _query(shield_ids: list[str] | None) -> QueryRequest:
    """Build a query that selects the given shields."""
    return QueryRequest(query="What is Kubernetes?", shield_ids=shield_ids)


def _responses(shield_ids: list[str] | None) -> ResponsesRequest:
    """Build a Responses request that selects the given shields."""
    return ResponsesRequest(input="What is Kubernetes?", shield_ids=shield_ids)


def test_omitted_ids_leave_every_shield_enabled(mocker: MockerFixture) -> None:
    """A missing shield id list leaves every configured shield enabled."""
    _install(mocker, ["topic", "pii"])

    settings = ShieldSettings.from_query_request(_query(None))
    responses_settings = ShieldSettings.from_responses_request(_responses(None))

    assert settings == [
        ShieldSettings(id="topic", enabled=True),
        ShieldSettings(id="pii", enabled=True),
    ]
    assert responses_settings == settings


def test_query_ids_enable_only_the_named_shields(mocker: MockerFixture) -> None:
    """A provided id list disables every configured shield that is absent."""
    _install(mocker, ["topic", "pii"])

    settings = ShieldSettings.from_query_request(_query(["pii", "unknown"]))
    responses_settings = ShieldSettings.from_responses_request(
        _responses(["pii", "unknown"])
    )

    assert settings == [
        ShieldSettings(id="topic", enabled=False),
        ShieldSettings(id="pii", enabled=True),
    ]
    assert responses_settings == settings


def test_empty_id_list_disables_every_shield(mocker: MockerFixture) -> None:
    """An empty shield id list disables every configured shield."""
    _install(mocker, ["topic", "pii"])

    settings = ShieldSettings.from_query_request(_query([]))
    responses_settings = ShieldSettings.from_responses_request(_responses([]))

    assert [setting.enabled for setting in settings] == [False, False]
    assert [setting.enabled for setting in responses_settings] == [False, False]


def test_no_configured_shields_produce_no_settings(mocker: MockerFixture) -> None:
    """An empty shield list yields no shield settings."""
    _install(mocker, [])

    assert ShieldSettings.from_query_request(_query(None)) == []
    assert ShieldSettings.from_responses_request(_responses(None)) == []
