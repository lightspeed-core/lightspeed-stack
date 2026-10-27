"""Unit tests for soft-fallback resolution helpers."""

from typing import Any

from providers.inference.resolve import configured_defaults, conversation_last_used


def test_conversation_last_used_returns_none_without_conversation_id() -> None:
    """conversation_last_used skips lookup when conversation_id is omitted."""
    assert conversation_last_used(None) is None


def test_conversation_last_used_returns_ids(mocker: Any) -> None:
    """conversation_last_used returns last-used provider/model from the conversation."""
    conversation = mocker.Mock()
    conversation.last_used_provider = "openai"
    conversation.last_used_model = "chat"
    mocker.patch(
        "providers.inference.resolve.retrieve_conversation",
        return_value=conversation,
    )

    assert conversation_last_used("conv-1") == ("openai", "chat")


def test_conversation_last_used_soft_skips_missing_conversation(mocker: Any) -> None:
    """Missing conversations soft-skip and return None."""
    mocker.patch(
        "providers.inference.resolve.retrieve_conversation",
        return_value=None,
    )

    assert conversation_last_used("missing") is None


def test_configured_defaults_returns_ids(mocker: Any) -> None:
    """configured_defaults returns both configured default ids."""
    mocker.patch(
        "providers.inference.resolve.configuration",
        mocker.Mock(
            inference=mocker.Mock(default_model="chat", default_provider="openai")
        ),
    )

    assert configured_defaults() == ("openai", "chat")


def test_configured_defaults_soft_skips_unset(mocker: Any) -> None:
    """Unset defaults soft-skip and return None."""
    mocker.patch(
        "providers.inference.resolve.configuration",
        mocker.Mock(inference=mocker.Mock(default_model=None, default_provider=None)),
    )

    assert configured_defaults() is None
