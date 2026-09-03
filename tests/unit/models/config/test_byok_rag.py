"""Unit tests for ByokRag model."""

import pytest
from pydantic import ValidationError

from constants import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RAG_TYPE,
    DEFAULT_SCORE_MULTIPLIER,
)
from models.config import ByokRag


def test_byok_rag_configuration_default_values() -> None:
    """Test the ByokRag constructor.

    Verify that ByokRag initializes correctly when only required fields are provided.

    Asserts that the instance stores the given `rag_id`, `vector_db_id`, and
    `db_path`, and that unspecified fields use the module's default values for
    `rag_type`, `embedding_model`, `embedding_dimension`, and
    `score_multiplier`.
    """
    byok_rag = ByokRag(  # pyright: ignore[reportCallIssue]
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
    assert byok_rag.db_path == "tests/configuration/rag.txt"
    assert byok_rag.score_multiplier == DEFAULT_SCORE_MULTIPLIER


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
        score_multiplier=1.0,
    )
    assert byok_rag is not None
    assert byok_rag.rag_id == "rag_id"
    assert byok_rag.rag_type == "rag_type"
    assert byok_rag.embedding_model == "embedding_model"
    assert byok_rag.embedding_dimension == 1024
    assert byok_rag.vector_db_id == "vector_db_id"
    assert byok_rag.db_path == "tests/configuration/rag.txt"


def test_byok_rag_configuration_wrong_dimension() -> None:
    """Test the ByokRag constructor.

    Verify constructing ByokRag with embedding_dimension less than or equal to
    zero raises a ValidationError.

    The raised ValidationError's message must contain "should be greater than 0".
    """
    with pytest.raises(ValidationError, match="should be greater than 0"):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="rag_type",
            embedding_model="embedding_model",
            embedding_dimension=-1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_byok_rag_configuration_empty_rag_id() -> None:
    """Test the ByokRag constructor.

    Validate that constructing a ByokRag with an empty `rag_id` raises a validation error.

    Expects a `pydantic.ValidationError` whose message contains "String should
    have at least 1 character".
    """
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
            score_multiplier=1.0,
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
            score_multiplier=1.0,
        )


def test_byok_rag_configuration_empty_embedding_model() -> None:
    """Test the ByokRag constructor.

    Verify that constructing a ByokRag with an empty `embedding_model` raises a validation error.

    Expects a pydantic.ValidationError whose message contains "String should
    have at least 1 character".
    """
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
            score_multiplier=1.0,
        )


def test_byok_rag_configuration_empty_vector_db_id() -> None:
    """Test the ByokRag constructor.

    Ensure constructing a ByokRag with an empty `vector_db_id` raises a ValidationError.

    Asserts that Pydantic validation fails with a message containing "String
    should have at least 1 character".
    """
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
            score_multiplier=1.0,
        )


def test_byok_rag_configuration_custom_score_multiplier() -> None:
    """Test ByokRag with custom score_multiplier."""
    byok_rag = ByokRag(
        rag_id="rag_id",
        rag_type="rag_type",
        vector_db_id="vector_db_id",
        embedding_model="embedding_model",
        embedding_dimension=1024,
        db_path="tests/configuration/rag.txt",
        score_multiplier=2.5,
    )
    assert byok_rag.score_multiplier == 2.5


def test_byok_rag_configuration_score_multiplier_must_be_positive() -> None:
    """Test that score_multiplier must be greater than 0."""
    with pytest.raises(ValidationError, match="greater than 0"):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="rag_type",
            vector_db_id="vector_db_id",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            db_path="tests/configuration/rag.txt",
            score_multiplier=0.0,
        )


def test_byok_rag_faiss_requires_db_path() -> None:
    """Test that inline::faiss requires db_path."""
    with pytest.raises(ValidationError, match="db_path is required"):
        _ = ByokRag(
            rag_id="rag_id",
            rag_type="inline::faiss",
            vector_db_id="vector_db_id",
        )


def test_byok_rag_pgvector_defaults() -> None:
    """Test pgvector auto-populates connection fields with env var defaults."""
    store = ByokRag(
        rag_id="pg_store",
        rag_type="remote::pgvector",
        vector_db_id="vs_pg",
    )
    assert store.rag_type == "remote::pgvector"
    assert store.host == "${env.POSTGRES_HOST}"
    assert store.port == "${env.POSTGRES_PORT}"
    assert store.db == "${env.POSTGRES_DATABASE}"
    assert store.user == "${env.POSTGRES_USER}"
    password = store.password.get_secret_value()  # pylint: disable=no-member
    assert password == "${env.POSTGRES_PASSWORD}"
    assert store.db_path is None


def test_byok_rag_pgvector_custom_connection_fields() -> None:
    """Test pgvector accepts custom connection field values."""
    store = ByokRag(
        rag_id="pg_store",
        rag_type="remote::pgvector",
        vector_db_id="vs_pg",
        host="db.example.com",
        port="5433",
        db="my_knowledge",
        user="admin",
        password="secret",
    )
    assert store.host == "db.example.com"
    assert store.port == "5433"
    assert store.db == "my_knowledge"
    assert store.user == "admin"
    assert store.password.get_secret_value() == "secret"  # pylint: disable=no-member


def test_byok_rag_pgvector_partial_overrides() -> None:
    """Test pgvector fills only missing connection fields with defaults."""
    store = ByokRag(
        rag_id="pg_store",
        rag_type="remote::pgvector",
        vector_db_id="vs_pg",
        host="custom-host",
    )
    assert store.host == "custom-host"
    assert store.port == "${env.POSTGRES_PORT}"


def test_byok_rag_pgvector_does_not_require_db_path() -> None:
    """Test pgvector does not require db_path."""
    store = ByokRag(
        rag_id="pg_store",
        rag_type="remote::pgvector",
        vector_db_id="vs_pg",
    )
    assert store.db_path is None
