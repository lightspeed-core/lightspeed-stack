"""Tests for conversation and turn item id helpers."""

import uuid

from conversations.agent_history.ids import new_id


def test_message_item_id_matches_run_id_shape() -> None:
    """Turn item ids use the same prefixed uuid pattern as run ids."""
    item_id = new_id("message")
    assert item_id.startswith("msg_")
    uuid.UUID(item_id.removeprefix("msg_"))

    run_id = new_id("run")
    assert run_id.startswith("resp_")
    uuid.UUID(run_id.removeprefix("resp_"))


def test_sources_item_prefix() -> None:
    """Sources turn items use the src_ prefix."""
    item_id = new_id("sources")
    assert item_id.startswith("src_")
    uuid.UUID(item_id.removeprefix("src_"))
