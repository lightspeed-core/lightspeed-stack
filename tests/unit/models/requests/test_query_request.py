"""Unit tests for QueryRequest model."""

import pytest
from pydantic import ValidationError

from models.api.requests import QueryRequest
from models.common.query import Attachment, OkpFilter, SolrVectorSearchRequest


class TestQueryRequest:
    """Test cases for the QueryRequest model."""

    def test_constructor(self) -> None:
        """Test the QueryRequest constructor.

        Verify QueryRequest initializes with the provided query and leaves optional fields unset.

        Asserts that:
        - `query` equals the provided string.
        - `conversation_id`, `provider`, `model`, `system_prompt`, and `attachments` are `None`.
        """
        qr = QueryRequest(
            query="Tell me about Kubernetes"
        )  # pyright: ignore[reportCallIssue]

        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id is None
        assert qr.provider is None
        assert qr.model is None
        assert qr.system_prompt is None
        assert qr.attachments is None

    def test_constructor_wrong_conversation_id(self) -> None:
        """Test the QueryRequest constructor with wrong conversation_id."""
        with pytest.raises(ValueError, match="Improper conversation ID 'xyzzy'"):
            _ = QueryRequest(
                query="Tell me about Kubernetes", conversation_id="xyzzy"
            )  # pyright: ignore[reportCallIssue]

    def test_with_attachments(self) -> None:
        """Test the QueryRequest with attachments.

        Verify that a QueryRequest constructed with attachments stores them intact.

        Constructs two Attachment instances, creates a QueryRequest with those attachments,
        and asserts that the request's attachments list is present, has length 2, and that
        each attachment's `attachment_type`, `content_type`, and `content` match the
        original objects.
        """
        attachments = [
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="this is attachment",
            ),
            Attachment(
                attachment_type="configuration",
                content_type="application/yaml",
                content="kind: Pod\n metadata:\n name:    private-reg",
            ),
        ]
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            attachments=attachments,
        )  # pyright: ignore[reportCallIssue]
        assert qr.attachments is not None
        assert len(qr.attachments) == 2

        # the following warning is false positive
        # pylint: disable=unsubscriptable-object
        assert qr.attachments[0].attachment_type == "log"
        assert qr.attachments[0].content_type == "text/plain"
        assert qr.attachments[0].content == "this is attachment"
        assert qr.attachments[1].attachment_type == "configuration"
        assert qr.attachments[1].content_type == "application/yaml"
        assert (
            qr.attachments[1].content == "kind: Pod\n metadata:\n name:    private-reg"
        )

    def test_with_optional_fields(self) -> None:
        """Test the QueryRequest with optional fields."""
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            provider="OpenAI",
            model="gpt-3.5-turbo",
            system_prompt="You are a helpful assistant",
        )  # pyright: ignore[reportCallIssue]
        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.system_prompt == "You are a helpful assistant"
        assert qr.attachments is None

    def test_validate_media_type(self) -> None:
        """Test accepted media_type values on QueryRequest.

        Constructs a QueryRequest with provider, model, and a supported
        ``media_type`` and asserts fields are stored correctly.
        """
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            provider="OpenAI",
            model="gpt-3.5-turbo",
            media_type="text/plain",
        )  # pyright: ignore[reportCallIssue]
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.media_type == "text/plain"

    def test_generate_topic_summary_explicit_false(self) -> None:
        """Test that generate_topic_summary can be explicitly set to False.

        Verify that generate_topic_summary accepts an explicit value.

        Constructs a QueryRequest with generate_topic_summary set to False and
        asserts the instance's attribute reflects that setting.
        """
        qr = QueryRequest(
            query="Tell me about Kubernetes", generate_topic_summary=False
        )  # pyright: ignore[reportCallIssue]
        assert qr.generate_topic_summary is False

    def test_generate_topic_summary_explicit_true(self) -> None:
        """Test that generate_topic_summary can be explicitly set to True."""
        qr = QueryRequest(
            query="Tell me about Kubernetes", generate_topic_summary=True
        )  # pyright: ignore[reportCallIssue]
        assert qr.generate_topic_summary is True

    def test_solr_legacy_plain_dict(self) -> None:
        """Legacy clients may send filter keys as a plain object on ``solr``."""
        qr = QueryRequest(
            query="q",
            solr={"fq": ["a:b"]},
        )  # pyright: ignore[reportCallIssue]
        solr_request = SolrVectorSearchRequest.model_validate(qr.solr)
        assert solr_request.mode is None
        assert solr_request.filters == {"fq": ["a:b"]}

    def test_solr_structured_mode_and_filters(self) -> None:
        """New clients send ``mode`` and ``filters`` under ``solr``."""
        qr = QueryRequest(
            query="q",
            solr={"mode": "hybrid", "filters": {"fq": ["x:y"]}},
        )  # pyright: ignore[reportCallIssue]
        solr_request = SolrVectorSearchRequest.model_validate(qr.solr)
        assert solr_request.mode == "hybrid"
        assert solr_request.filters == {"fq": ["x:y"]}

    def test_okp_filter_parsed(self) -> None:
        """The transport-neutral ``okp`` filter is parsed into typed objects."""
        qr = QueryRequest(
            query="q",
            okp={
                "products": [
                    {
                        "product": "openshift_container_platform",
                        "versions": ["4.16", "4.17"],
                    }
                ]
            },
        )  # pyright: ignore[reportCallIssue]
        assert qr.okp is not None
        assert qr.okp.products[0].product == "openshift_container_platform"
        assert qr.okp.products[0].versions == ["4.16", "4.17"]

    def test_okp_defaults_to_none(self) -> None:
        """The ``okp`` field is optional and defaults to None."""
        qr = QueryRequest(query="q")
        assert qr.okp is None


class TestOkpFilter:
    """Tests for the OkpFilter / OkpProductFilter request models."""

    def test_product_is_required(self) -> None:
        """A product selection without a product identifier is rejected."""
        with pytest.raises(ValidationError):
            OkpFilter.model_validate({"products": [{"versions": ["4.16"]}]})

    def test_versions_optional(self) -> None:
        """Versions may be omitted, matching the product regardless of version."""
        okp = OkpFilter.model_validate(
            {"products": [{"product": "openshift_container_platform"}]}
        )
        assert okp.products[0].versions is None

    def test_products_defaults_to_empty_list(self) -> None:
        """An OkpFilter with no products is an empty (no-op) filter."""
        assert OkpFilter().products == []

    def test_unknown_fields_rejected(self) -> None:
        """Unknown fields are rejected on both nested models."""
        with pytest.raises(ValidationError):
            OkpFilter.model_validate({"products": [{"product": "p", "bogus": 1}]})
