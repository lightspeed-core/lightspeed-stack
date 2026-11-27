"""Unit tests for utils.referenced_documents."""

from utils.referenced_documents import graft_url_fragment


class TestGraftUrlFragment:
    """Tests for graft_url_fragment."""

    def test_grafts_fragment_onto_portal_path(self) -> None:
        """The #fragment from source_path is appended to the portal path."""
        assert (
            graft_url_fragment(
                "/documentation/en-us/p/1/topic",
                "/en/documentation/p/1/topic#GUID-abc",
            )
            == "/documentation/en-us/p/1/topic#GUID-abc"
        )

    def test_noop_when_source_path_has_no_fragment(self) -> None:
        """No change when source_path carries no anchor."""
        assert (
            graft_url_fragment("/documentation/en-us/p/1/topic", "/en/documentation/x")
            == "/documentation/en-us/p/1/topic"
        )

    def test_noop_when_reference_already_has_fragment(self) -> None:
        """An existing fragment on the reference is preserved (not doubled)."""
        assert (
            graft_url_fragment("/p/1/topic#existing", "/s#other")
            == "/p/1/topic#existing"
        )

    def test_noop_when_reference_is_none(self) -> None:
        """None reference stays None."""
        assert graft_url_fragment(None, "/s#frag") is None

    def test_noop_when_source_path_is_none(self) -> None:
        """None source_path leaves the reference unchanged."""
        assert graft_url_fragment("/p/1/topic", None) == "/p/1/topic"

    def test_noop_when_fragment_is_empty(self) -> None:
        """A trailing '#' with no fragment is ignored."""
        assert graft_url_fragment("/p/1/topic", "/s#") == "/p/1/topic"
