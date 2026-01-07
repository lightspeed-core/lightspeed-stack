"""Unit tests for ByokRag model."""

from pathlib import Path

import pytest

from pydantic import ValidationError

from models.config import ByokRag

from constants import (
    DEFAULT_RAG_TYPE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSION,
)


def test_byok_rag_configuration_default_values() -> None:
    """Test the ByokRag constructor."""

    byok_rag = ByokRag(
        rag_id="rag_id",
        vector_db_id="vector_db_id",
        db_path="tests/configuration/rag.txt",
    )
    assert byok_rag is not None
    assert byok_rag.rag_id == "rag_id"
    assert byok_rag.rag_type == DEFAULT_RAG_TYPE
    assert byok_rag.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert byok_rag.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION
    assert byok_rag.vector_db_id == "vector_db_id"
    assert byok_rag.db_path == Path("tests/configuration/rag.txt")


def test_byok_rag_configuration_nondefault_values() -> None:
    """Test the ByokRag constructor.

    Verify that ByokRag class accepts and stores non-default configuration values.

    Asserts that rag_id, rag_type, embedding_model, embedding_dimension, and
    vector_db_id match the provided inputs and that db_path is converted to a
    Path.
    """

    byok_rag = ByokRag(
        rag_id="rag_id",
        rag_type="rag_type",
        embedding_model="embedding_model",
        embedding_dimension=1024,
        vector_db_id="vector_db_id",
        db_path="tests/configuration/rag.txt",
    )
    assert byok_rag is not None
    assert byok_rag.rag_id == "rag_id"
    assert byok_rag.rag_type == "rag_type"
    assert byok_rag.embedding_model == "embedding_model"
    assert byok_rag.embedding_dimension == 1024
    assert byok_rag.vector_db_id == "vector_db_id"
    assert byok_rag.db_path == Path("tests/configuration/rag.txt")


def test_byok_rag_configuration_wrong_dimension() -> None:
    """Test the ByokRag constructor."""

    with pytest.raises(ValidationError, match="should be greater than 0"):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="rag_type",
            embedding_model="embedding_model",
            embedding_dimension=-1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )


def test_byok_rag_configuration_empty_rag_id() -> None:
    """Test the ByokRag constructor."""

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = ByokRag(
            rag_id="",
            rag_type="rag_type",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )


def test_byok_rag_configuration_empty_rag_type() -> None:
    """Test the ByokRag constructor.

    Verify that constructing a ByokRag with an empty `rag_type` raises a validation error.

    Raises:
        ValidationError: if `rag_type` is an empty string; error message
        includes "String should have at least 1 character".
    """

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )


def test_byok_rag_configuration_empty_embedding_model() -> None:
    """Test the ByokRag constructor."""

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="rag_type",
            embedding_model="",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )


def test_byok_rag_configuration_empty_vector_db_id() -> None:
    """Test the ByokRag constructor."""

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="rag_type",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="",
            db_path="tests/configuration/rag.txt",
        )
