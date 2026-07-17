"""Unit tests for tool_formatter utilities."""

from typing import Any

from lightspeed_stack.utils.tool_formatter import translate_vector_store_ids_to_user_facing


class TestTranslateVectorStoreIdsToUserFacing:
    """Tests for translate_vector_store_ids_to_user_facing."""

    def test_empty_mapping_returns_new_list_same_tool_objects(self) -> None:
        """When mapping is empty, return a new list with the same tool dicts."""
        tools: list[dict[str, Any]] = [
            {"type": "file_search", "vector_store_ids": ["vs-1"]},
        ]
        result = translate_vector_store_ids_to_user_facing(tools, {})
        assert result is not tools
        assert result == tools
        assert result[0] is tools[0]

    def test_file_search_vector_store_ids_mapped(self) -> None:
        """file_search tools get vector_store_ids rewritten via mapping."""
        tools: list[dict[str, Any]] = [
            {
                "type": "file_search",
                "vector_store_ids": ["llama-vs", "other-vs"],
            },
        ]
        mapping = {"llama-vs": "user-rag-a", "other-vs": "user-rag-b"}
        result = translate_vector_store_ids_to_user_facing(tools, mapping)
        assert result[0]["vector_store_ids"] == ["user-rag-a", "user-rag-b"]
        assert result[0]["type"] == "file_search"

    def test_unmapped_id_passthrough(self) -> None:
        """IDs absent from mapping are left unchanged."""
        tools: list[dict[str, Any]] = [
            {"type": "file_search", "vector_store_ids": ["known", "unknown-id"]},
        ]
        result = translate_vector_store_ids_to_user_facing(
            tools, {"known": "user-facing"}
        )
        assert result[0]["vector_store_ids"] == ["user-facing", "unknown-id"]

    def test_non_file_search_tool_unchanged_identity(self) -> None:
        """Non-file_search entries are appended as the same dict instance."""
        mcp_tool: dict[str, Any] = {"type": "mcp", "server_url": "http://x"}
        tools: list[dict[str, Any]] = [mcp_tool]
        result = translate_vector_store_ids_to_user_facing(tools, {"any": "mapping"})
        assert len(result) == 1
        assert result[0] is mcp_tool

    def test_file_search_new_dict_instance(self) -> None:
        """file_search entries are copied so original tool dict is not mutated."""
        original: dict[str, Any] = {
            "type": "file_search",
            "vector_store_ids": ["vs-1"],
        }
        tools: list[dict[str, Any]] = [original]
        result = translate_vector_store_ids_to_user_facing(tools, {"vs-1": "u-1"})
        assert result[0] is not original
        assert original["vector_store_ids"] == ["vs-1"]

    def test_mixed_tools_order_preserved(self) -> None:
        """Order and handling per type are stable across a mixed tool list."""
        tools: list[dict[str, Any]] = [
            {"type": "file_search", "vector_store_ids": ["a"]},
            {"type": "function", "name": "fn"},
            {"type": "file_search", "vector_store_ids": ["b", "c"]},
        ]
        result = translate_vector_store_ids_to_user_facing(
            tools, {"a": "A", "b": "B", "c": "C"}
        )
        assert [t["type"] for t in result] == ["file_search", "function", "file_search"]
        assert result[0]["vector_store_ids"] == ["A"]
        assert result[1] is tools[1]
        assert result[2]["vector_store_ids"] == ["B", "C"]
