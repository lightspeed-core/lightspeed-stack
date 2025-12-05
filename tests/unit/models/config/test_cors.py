"""Unit tests for CORSConfiguration model."""

import pytest

from models.config import CORSConfiguration


def test_cors_default_configuration() -> None:
    """Test the CORS configuration."""
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
    """Test the CORS configuration."""
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
    """Test the CORS configuration."""
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
