"""Unit tests for CORSConfiguration model."""

import pytest

from models.config import CORSConfiguration


def test_cors_default_configuration() -> None:
    """Test the CORS configuration.

    Verify that a default CORSConfiguration instance has the expected default
    values.

    Asserts that:
    - allow_origins is ["*"]
    - allow_credentials is False
    - allow_methods is ["*"]
    - allow_headers is ["*"]
    """
    cfg = CORSConfiguration()
    assert cfg is not None
    assert cfg.allow_origins == ["*"]
    assert cfg.allow_credentials is False
    assert cfg.allow_methods == ["*"]
    assert cfg.allow_headers == ["*"]


def test_cors_custom_configuration_v1() -> None:
    """Test the CORS configuration."""
    cfg = CORSConfiguration(
        allow_origins=["foo_origin", "bar_origin", "baz_origin"],
        allow_credentials=False,
        allow_methods=["foo_method", "bar_method", "baz_method"],
        allow_headers=["foo_header", "bar_header", "baz_header"],
    )
    assert cfg is not None
    assert cfg.allow_origins == ["foo_origin", "bar_origin", "baz_origin"]
    assert cfg.allow_credentials is False
    assert cfg.allow_methods == ["foo_method", "bar_method", "baz_method"]
    assert cfg.allow_headers == ["foo_header", "bar_header", "baz_header"]


def test_cors_custom_configuration_v2() -> None:
    """Test the CORS configuration."""
    cfg = CORSConfiguration(
        allow_origins=["foo_origin", "bar_origin", "baz_origin"],
        allow_credentials=True,
        allow_methods=["foo_method", "bar_method", "baz_method"],
        allow_headers=["foo_header", "bar_header", "baz_header"],
    )
    assert cfg is not None
    assert cfg.allow_origins == ["foo_origin", "bar_origin", "baz_origin"]
    assert cfg.allow_credentials is True
    assert cfg.allow_methods == ["foo_method", "bar_method", "baz_method"]
    assert cfg.allow_headers == ["foo_header", "bar_header", "baz_header"]


def test_cors_custom_configuration_v3() -> None:
    """Test the CORS configuration.

    Verify that CORSConfiguration accepts a wildcard origin when credentials
    are disabled and preserves provided methods and headers.

    Creates a CORSConfiguration with allow_origins ["*"], allow_credentials
    False, and explicit allow_methods and allow_headers, then asserts the
    instance exists and its attributes match the provided values.
    """
    cfg = CORSConfiguration(
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["foo_method", "bar_method", "baz_method"],
        allow_headers=["foo_header", "bar_header", "baz_header"],
    )
    assert cfg is not None
    assert cfg.allow_origins == ["*"]
    assert cfg.allow_credentials is False
    assert cfg.allow_methods == ["foo_method", "bar_method", "baz_method"]
    assert cfg.allow_headers == ["foo_header", "bar_header", "baz_header"]


def test_cors_improper_configuration() -> None:
    """Test the CORS configuration.

    Verify that constructing CORSConfiguration with a wildcard origin and
    credentials enabled raises a ValueError.

    Asserts the raised ValueError contains the message that `allow_credentials`
    cannot be true when `allow_origins` contains the '*' wildcard and advises
    using explicit origins or disabling credentials.
    """
    expected = (
        "Value error, Invalid CORS configuration: "
        + "allow_credentials can not be set to true when allow origins contains the '\\*' wildcard."
        + "Use explicit origins or disable credentials."
    )

    with pytest.raises(ValueError, match=expected):
        # allow_credentials can not be true when allow_origins contains '*'
        CORSConfiguration(
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["foo_method", "bar_method", "baz_method"],
            allow_headers=["foo_header", "bar_header", "baz_header"],
        )
