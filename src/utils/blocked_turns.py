"""The mark of a turn a shield blocked (LCORE-3788).

A turn a shield blocked is stored in the conversation, so that the history a
client reads is complete. It must not reach the model again. Conversation
compaction rebuilds the model's context from the stored items, so a blocked
text that is replayed or summarized there was not blocked, only delayed by one
turn.

A conversation item has no field for metadata, so the mark is the item id: the
messages of a blocked turn are stored under an id that starts with
``BLOCKED_ITEM_ID_PREFIX``. OGX keeps an id the caller supplies. The ids it
generates itself are ``msg_`` followed by hexadecimal digits or a UUID, so they
never start with the prefix.

Only turns stored with the mark are recognized. A blocked turn stored before
the mark existed looks like any other turn.

A shield that runs inside the agent rejects a run by returning a refusal in
place of the model's answer. To the endpoint that looks like any other answer,
so the shield flags the response it returns: ``SHIELD_BLOCKED_METADATA_KEY`` in
its metadata, which :func:`shield_refusal_of` reads back.
"""

import secrets
from collections.abc import Sequence
from typing import Any, Final, Optional

BLOCKED_ITEM_ID_PREFIX: Final[str] = "msg_blocked_"
"""Start of the id of every message that belongs to a blocked turn."""

SHIELD_BLOCKED_METADATA_KEY: Final[str] = "lightspeed_shield_blocked"
"""Metadata key of the response a shield returns when it rejects an agent run."""


def new_blocked_item_id() -> str:
    """Return a new id for a message of a blocked turn.

    Item ids are unique across all conversations in OGX, and storing an item
    under an id that exists overwrites that item. So the id is random, with as
    many random bytes as OGX uses for the ids it generates.

    Returns:
        ``BLOCKED_ITEM_ID_PREFIX`` followed by 48 hexadecimal digits.

    """
    return f"{BLOCKED_ITEM_ID_PREFIX}{secrets.token_hex(24)}"


def is_blocked_item(item: Any) -> bool:
    """Tell whether a stored conversation item belongs to a blocked turn.

    Parameters:
        item: A conversation item, as OGX lists it.

    Returns:
        True when the item has an id that starts with
        ``BLOCKED_ITEM_ID_PREFIX``.

    """
    item_id = getattr(item, "id", None)
    return isinstance(item_id, str) and item_id.startswith(BLOCKED_ITEM_ID_PREFIX)


def exclude_blocked_items(items: Sequence[Any]) -> list[Any]:
    """Return the conversation items that do not belong to a blocked turn.

    This is for code that builds what the model reads. A client that reads the
    conversation gets the blocked turns as well.

    A summary marker records how many stored items it covers, blocked ones
    included. Apply this filter after the items were cut at that count, never
    before.

    Parameters:
        items: Conversation items, as stored.

    Returns:
        The items that are not blocked: the same objects, in their original
        order.

    """
    return [item for item in items if not is_blocked_item(item)]


def mark_blocked(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the items of a turn as blocked, before they are stored.

    Every message gets a new blocked id, in place of the id it may have had:
    the input of a request can carry ids the client chose. Items of other
    types are left as they are; the model's context is built from messages
    only.

    Parameters:
        items: The items of the turn, as dictionaries ready to be stored.

    Returns:
        New dictionaries, in the same order; the ones passed in are not
        modified.

    """
    return [
        (
            {**item, "id": new_blocked_item_id()}
            if item.get("type") == "message"
            else dict(item)
        )
        for item in items
    ]


def shield_refusal_of(run_result: Any) -> Optional[str]:
    """Return the refusal of an agent run, when a shield rejected the run.

    The flag is read from the metadata of the last response of the run.
    pydantic-ai keeps that metadata for the application and does not send it
    to a model.

    Parameters:
        run_result: The result of the agent run.

    Returns:
        The refusal text when the last response carries
        ``SHIELD_BLOCKED_METADATA_KEY``, else ``None``.

    """
    response: Any = getattr(run_result, "response", None)
    metadata = getattr(response, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    if metadata.get(SHIELD_BLOCKED_METADATA_KEY) is not True:
        return None
    return response.text or ""
