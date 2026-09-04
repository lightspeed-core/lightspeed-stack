"""Serialization helpers for ``ogx_client`` models."""

from typing import Any

from ogx_client.api_client import ApiClient

_OGX_SERIALIZER = ApiClient()


def dump_ogx_model(obj: Any) -> Any:
    """Dump an ogx_client model to a JSON-safe structure.

    Args:
        obj: An ogx_client model instance.

    Returns:
        A JSON-serializable dict, list, or primitive produced from obj.
    """
    return _OGX_SERIALIZER.sanitize_for_serialization(obj)  # type: ignore[no-untyped-call]
