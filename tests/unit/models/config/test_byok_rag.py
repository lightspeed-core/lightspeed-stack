"""Unit tests for RagStore model."""

import pytest
from pydantic import ValidationError

from constants import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RAG_BACKEND,
    DEFAULT_SCORE_MULTIPLIER,
)
from models.config import ByokConfiguration, RagStore


def test_rag_store_configuration_default_values() -> None:
    """Test the RagStore constructor.

    Verify that RagStore initializes correctly when only required fields are provided.

    Asserts that the instance stores the given `rag_id`, `vector_db_id`, and
    `db_path`, and that unspecified fields use the module's default values for
    `backend`, `embedding_model`, `embedding_dimension`, and
    `score_multiplier`.
    """
    rag_store = RagStore(  # pyright: ignore[reportCallIssue]
        rag_id="rag_id",
        vector_db_id="vector_db_id",
        db_path="tests/configuration/rag.txt",
    )
    assert rag_store is not None
    assert rag_store.rag_id == "rag_id"
    assert rag_store.backend == DEFAULT_RAG_BACKEND
    assert rag_store.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert rag_store.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION
    assert rag_store.vector_db_id == "vector_db_id"
    assert rag_store.db_path == "tests/configuration/rag.txt"
    assert rag_store.score_multiplier == DEFAULT_SCORE_MULTIPLIER


def test_rag_store_configuration_nondefault_values() -> None:
    """Test the RagStore constructor.

    Verify that RagStore class accepts and stores non-default configuration values.

    Asserts that rag_id, backend, embedding_model, embedding_dimension, and
    vector_db_id match the provided inputs and that db_path is converted to a
    Path.
    """
    rag_store = RagStore(
        rag_id="rag_id",
        backend="faiss",
        embedding_model="embedding_model",
        embedding_dimension=1024,
        vector_db_id="vector_db_id",
        db_path="tests/configuration/rag.txt",
        score_multiplier=1.0,
    )
    assert rag_store is not None
    assert rag_store.rag_id == "rag_id"
    assert rag_store.backend == "faiss"
    assert rag_store.embedding_model == "embedding_model"
    assert rag_store.embedding_dimension == 1024
    assert rag_store.vector_db_id == "vector_db_id"
    assert rag_store.db_path == "tests/configuration/rag.txt"


def test_rag_store_configuration_wrong_dimension() -> None:
    """Test the RagStore constructor.

    Verify constructing RagStore with embedding_dimension less than or equal to
    zero raises a ValidationError.

    The raised ValidationError's message must contain "should be greater than 0".
    """
    with pytest.raises(ValidationError, match="should be greater than 0"):
        _ = RagStore(
            rag_id="rag_id",
            backend="faiss",
            embedding_model="embedding_model",
            embedding_dimension=-1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_rag_store_configuration_empty_rag_id() -> None:
    """Test the RagStore constructor.

    Validate that constructing a RagStore with an empty `rag_id` raises a validation error.

    Expects a `pydantic.ValidationError` whose message contains "String should
    have at least 1 character".
    """
    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = RagStore(
            rag_id="",
            backend="faiss",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_rag_store_configuration_empty_backend() -> None:
    """Test the RagStore constructor.

    Verify that constructing a RagStore with an empty `backend` raises a validation error.

    Raises:
        ValidationError: if `backend` is an empty string; error message
        includes "String should have at least 1 character".
    """
    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = RagStore(
            rag_id="rag_id",
            backend="",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_rag_store_configuration_unsupported_backend() -> None:
    """Test that unsupported backend values are rejected."""
    with pytest.raises(ValidationError, match="Unsupported RAG backend"):
        _ = RagStore(
            rag_id="rag_id",
            backend="unsupported",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )


def test_rag_store_configuration_empty_embedding_model() -> None:
    """Test the RagStore constructor.

    Verify that constructing a RagStore with an empty `embedding_model` raises a validation error.

    Expects a pydantic.ValidationError whose message contains "String should
    have at least 1 character".
    """
    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = RagStore(
            rag_id="rag_id",
            backend="faiss",
            embedding_model="",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_rag_store_configuration_empty_vector_db_id() -> None:
    """Test the RagStore constructor.

    Ensure constructing a RagStore with an empty `vector_db_id` raises a ValidationError.

    Asserts that Pydantic validation fails with a message containing "String
    should have at least 1 character".
    """
    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        _ = RagStore(
            rag_id="rag_id",
            backend="faiss",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )


def test_rag_store_configuration_custom_score_multiplier() -> None:
    """Test RagStore with custom score_multiplier."""
    rag_store = RagStore(
        rag_id="rag_id",
        backend="faiss",
        vector_db_id="vector_db_id",
        embedding_model="embedding_model",
        embedding_dimension=1024,
        db_path="tests/configuration/rag.txt",
        score_multiplier=2.5,
    )
    assert rag_store.score_multiplier == 2.5


def test_rag_store_configuration_score_multiplier_must_be_positive() -> None:
    """Test that score_multiplier must be greater than 0."""
    with pytest.raises(ValidationError, match="greater than 0"):
        _ = RagStore(
            rag_id="rag_id",
            backend="faiss",
            vector_db_id="vector_db_id",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            db_path="tests/configuration/rag.txt",
            score_multiplier=0.0,
        )


def test_byok_rag_faiss_requires_db_path() -> None:
    """Test that faiss backend requires db_path."""
    with pytest.raises(ValidationError, match="db_path is required"):
        _ = RagStore(
            rag_id="rag_id",
            backend="faiss",
            vector_db_id="vector_db_id",
        )


def test_byok_rag_pgvector_defaults() -> None:
    """Test pgvector auto-populates connection fields with env var defaults."""
    store = RagStore(
        rag_id="pg_store",
        backend="pgvector",
        vector_db_id="vs_pg",
    )
    assert store.backend == "pgvector"
    assert store.host == "${env.POSTGRES_HOST}"
    assert store.port == "${env.POSTGRES_PORT}"
    assert store.db == "${env.POSTGRES_DATABASE}"
    assert store.user == "${env.POSTGRES_USER}"
    password = store.password.get_secret_value()  # pylint: disable=no-member
    assert password == "${env.POSTGRES_PASSWORD}"
    assert store.db_path is None


def test_byok_rag_pgvector_custom_connection_fields() -> None:
    """Test pgvector accepts custom connection field values."""
    store = RagStore(
        rag_id="pg_store",
        backend="pgvector",
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
    store = RagStore(
        rag_id="pg_store",
        backend="pgvector",
        vector_db_id="vs_pg",
        host="custom-host",
    )
    assert store.host == "custom-host"
    assert store.port == "${env.POSTGRES_PORT}"


def test_byok_rag_pgvector_does_not_require_db_path() -> None:
    """Test pgvector does not require db_path."""
    store = RagStore(
        rag_id="pg_store",
        backend="pgvector",
        vector_db_id="vs_pg",
    )
    assert store.db_path is None


def test_byok_configuration_rejects_duplicate_rag_ids() -> None:
    """Test that duplicate rag_id values are rejected."""
    with pytest.raises(ValidationError, match="Duplicate rag_id 'docs'"):
        ByokConfiguration(
            stores=[
                RagStore(
                    rag_id="docs",
                    vector_db_id="vs_1",
                    db_path="/tmp/a.db",
                ),
                RagStore(
                    rag_id="docs",
                    vector_db_id="vs_2",
                    db_path="/tmp/b.db",
                ),
            ],
        )


def test_byok_configuration_allows_unique_rag_ids() -> None:
    """Test that unique rag_id values are accepted."""
    config = ByokConfiguration(
        stores=[
            RagStore(
                rag_id="docs-a",
                vector_db_id="vs_1",
                db_path="/tmp/a.db",
            ),
            RagStore(
                rag_id="docs-b",
                vector_db_id="vs_2",
                db_path="/tmp/b.db",
            ),
        ],
    )
    assert len(config.stores) == 2
