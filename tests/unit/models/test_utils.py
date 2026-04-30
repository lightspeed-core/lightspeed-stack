"""Unit tests for models.utils (mirrors src/models/utils.py)."""

from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolFileSearch as InputToolFileSearch,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolMCP as InputToolMCP,
)

from models.utils import add_mcp_authorizations


class TestAddMcpAuthorizations:
    """Tests for add_mcp_authorizations with realistic MCP tool rows.

    Assumes server_label is present on MCP dicts and unique across configured
    servers; see InputToolMCP in llama-stack-api.
    """

    def test_merges_authorization_by_server_label(self) -> None:
        """MCP model_dump omits authorization; the helper restores it by server_label."""
        live = InputToolMCP(
            server_label="alpha",
            server_url="http://alpha",
            require_approval="never",
            authorization="secret-token",
        )
        dumped = [live.model_dump()]
        assert "authorization" not in dumped[0]

        out = add_mcp_authorizations(dumped, [live])
        assert len(out) == 1
        assert out[0]["authorization"] == "secret-token"
        assert out[0]["server_label"] == "alpha"

    def test_two_mcp_servers_distinct_tokens(self) -> None:
        """Each server_label receives its own authorization."""
        a = InputToolMCP(
            server_label="srv-a",
            server_url="http://a",
            require_approval="never",
            authorization="token-a",
        )
        b = InputToolMCP(
            server_label="srv-b",
            server_url="http://b",
            require_approval="never",
            authorization="token-b",
        )
        dumped = [a.model_dump(), b.model_dump()]
        assert "authorization" not in dumped[0]
        assert "authorization" not in dumped[1]

        out = add_mcp_authorizations(dumped, [a, b])
        assert out[0]["authorization"] == "token-a"
        assert out[1]["authorization"] == "token-b"

    def test_file_search_row_unchanged_no_authorization_merge(self) -> None:
        """Non-MCP rows are copied; MCP row still gets auth from live list."""
        mcp = InputToolMCP(
            server_label="m",
            server_url="http://m",
            require_approval="never",
            authorization="mcp-secret",
        )
        fs = InputToolFileSearch(type="file_search", vector_store_ids=["vs-1"])
        dumped = [fs.model_dump(), mcp.model_dump()]
        assert "authorization" not in dumped[1]

        out = add_mcp_authorizations(dumped, [fs, mcp])
        assert out[0]["type"] == "file_search"
        assert "authorization" not in out[0]
        assert out[1]["authorization"] == "mcp-secret"

    def test_subset_dumped_rows_still_match_live_by_label(self) -> None:
        """When only some MCP tools appear in dumped_tools, labels still align."""
        first = InputToolMCP(
            server_label="one",
            server_url="http://one",
            require_approval="never",
            authorization="tok-one",
        )
        second = InputToolMCP(
            server_label="two",
            server_url="http://two",
            require_approval="never",
            authorization="tok-two",
        )
        dumped = [second.model_dump()]
        assert "authorization" not in dumped[0]

        out = add_mcp_authorizations(dumped, [first, second])
        assert len(out) == 1
        assert out[0]["authorization"] == "tok-two"

    def test_does_not_mutate_input_list_or_dicts(self) -> None:
        """Output is new containers; inputs stay as provided."""
        live = InputToolMCP(
            server_label="s",
            server_url="http://s",
            require_approval="never",
            authorization="t",
        )
        dumped = [live.model_dump()]
        row = dumped[0]
        assert "authorization" not in row

        out = add_mcp_authorizations(dumped, [live])
        assert out is not dumped
        assert out[0] is not row
        assert "authorization" not in row
