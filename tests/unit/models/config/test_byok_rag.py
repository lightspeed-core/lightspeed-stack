"""Unit tests for ByokRag model."""

import warnings

import pytest
from pydantic import ValidationError

from constants import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RAG_TYPE,
    DEFAULT_SCORE_MULTIPLIER,
)
from models.config import ByokRag, _strip_rag_type_prefix, _synthesize_rag_type


class TestByokRagBackendField:
    """Tests for the new 'backend' field and rag_type deprecation."""

    def test_backend_only_faiss(self) -> None:
        """Test that providing only 'backend' synthesizes rag_type."""
        store = ByokRag(
            rag_id="test",
            backend="faiss",
            vector_db_id="vs_123",
            db_path="/tmp/test.faiss",
        )
        assert store.backend == "faiss"
        assert store.rag_type == "inline::faiss"

    def test_backend_only_pgvector(self) -> None:
        """Test that providing only 'backend=pgvector' synthesizes rag_type."""
        store = ByokRag(
            rag_id="test",
            backend="pgvector",
            vector_db_id="vs_123",
        )
        assert store.backend == "pgvector"
        assert store.rag_type == "remote::pgvector"

    def test_backend_unknown_type(self) -> None:
        """Test that an unknown backend gets 'inline::' prefix by default."""
        store = ByokRag(
            rag_id="test",
            backend="chromadb",
            vector_db_id="vs_123",
        )
        assert store.backend == "chromadb"
        assert store.rag_type == "inline::chromadb"

    def test_rag_type_only_emits_deprecation(self) -> None:
        """Test that providing only 'rag_type' emits a deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            store = ByokRag(
                rag_id="test",
                rag_type="inline::faiss",
                vector_db_id="vs_123",
                db_path="/tmp/test.faiss",
            )
            assert store.backend == "faiss"
            assert store.rag_type == "inline::faiss"
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            assert "deprecated" in str(deprecation_warnings[0].message).lower()

    def test_rag_type_only_pgvector(self) -> None:
        """Test that providing only 'rag_type=remote::pgvector' derives backend."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            store = ByokRag(
                rag_id="test",
                rag_type="remote::pgvector",
                vector_db_id="vs_123",
            )
            assert store.backend == "pgvector"
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1

    def test_both_backend_and_rag_type_consistent(self) -> None:
        """Test that providing both consistent backend and rag_type works."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            store = ByokRag(
                rag_id="test",
                backend="faiss",
                rag_type="inline::faiss",
                vector_db_id="vs_123",
                db_path="/tmp/test.faiss",
            )
            assert store.backend == "faiss"
            assert store.rag_type == "inline::faiss"
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1

    def test_both_backend_and_rag_type_inconsistent(self) -> None:
        """Test that providing inconsistent backend and rag_type raises error."""
        with pytest.raises(ValidationError, match="inconsistent"):
            ByokRag(
                rag_id="test",
                backend="pgvector",
                rag_type="inline::faiss",
                vector_db_id="vs_123",
                db_path="/tmp/test.faiss",
            )

    def test_neither_backend_nor_rag_type_uses_default(self) -> None:
        """Test that providing neither backend nor rag_type uses default faiss."""
        store = ByokRag(
            rag_id="test",
            vector_db_id="vs_123",
            db_path="/tmp/test.faiss",
        )
        assert store.backend == "faiss"
        assert store.rag_type == DEFAULT_RAG_TYPE


class TestByokRagDefaults:
    """Tests for ByokRag default values and basic construction."""

    def test_byok_rag_configuration_default_values(self) -> None:
        """Test ByokRag initializes correctly with only required fields."""
        byok_rag = ByokRag(
            rag_id="rag_id",
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
        )
        assert byok_rag is not None
        assert byok_rag.rag_id == "rag_id"
        assert byok_rag.rag_type == DEFAULT_RAG_TYPE
        assert byok_rag.backend == "faiss"
        assert byok_rag.embedding_model == DEFAULT_EMBEDDING_MODEL
        assert byok_rag.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION
        assert byok_rag.vector_db_id == "vector_db_id"
        assert byok_rag.db_path == "tests/configuration/rag.txt"
        assert byok_rag.score_multiplier == DEFAULT_SCORE_MULTIPLIER

    def test_byok_rag_configuration_nondefault_values(self) -> None:
        """Test ByokRag accepts and stores non-default configuration values."""
        byok_rag = ByokRag(
            rag_id="rag_id",
            backend="custom_type",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=1.0,
        )
        assert byok_rag is not None
        assert byok_rag.rag_id == "rag_id"
        assert byok_rag.backend == "custom_type"
        assert byok_rag.rag_type == "inline::custom_type"
        assert byok_rag.embedding_model == "embedding_model"
        assert byok_rag.embedding_dimension == 1024
        assert byok_rag.vector_db_id == "vector_db_id"
        assert byok_rag.db_path == "tests/configuration/rag.txt"


class TestByokRagValidation:
    """Tests for ByokRag validation."""

    def test_byok_rag_configuration_wrong_dimension(self) -> None:
        """Test that embedding_dimension <= 0 raises ValidationError."""
        with pytest.raises(ValidationError, match="should be greater than 0"):
            _ = ByokRag(
                rag_id="rag_id",
                backend="custom",
                embedding_model="embedding_model",
                embedding_dimension=-1024,
                vector_db_id="vector_db_id",
                db_path="tests/configuration/rag.txt",
                score_multiplier=1.0,
            )

    def test_byok_rag_configuration_empty_rag_id(self) -> None:
        """Test that empty rag_id raises ValidationError."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            _ = ByokRag(
                rag_id="",
                backend="custom",
                embedding_model="embedding_model",
                embedding_dimension=1024,
                vector_db_id="vector_db_id",
                db_path="tests/configuration/rag.txt",
                score_multiplier=1.0,
            )

    def test_byok_rag_configuration_empty_embedding_model(self) -> None:
        """Test that empty embedding_model raises ValidationError."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            _ = ByokRag(
                rag_id="rag_id",
                backend="custom",
                embedding_model="",
                embedding_dimension=1024,
                vector_db_id="vector_db_id",
                db_path="tests/configuration/rag.txt",
                score_multiplier=1.0,
            )

    def test_byok_rag_configuration_empty_vector_db_id(self) -> None:
        """Test that empty vector_db_id raises ValidationError."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            _ = ByokRag(
                rag_id="rag_id",
                backend="custom",
                embedding_model="embedding_model",
                embedding_dimension=1024,
                vector_db_id="",
                db_path="tests/configuration/rag.txt",
                score_multiplier=1.0,
            )

    def test_byok_rag_configuration_custom_score_multiplier(self) -> None:
        """Test ByokRag with custom score_multiplier."""
        byok_rag = ByokRag(
            rag_id="rag_id",
            backend="custom",
            vector_db_id="vector_db_id",
            embedding_model="embedding_model",
            embedding_dimension=1024,
            db_path="tests/configuration/rag.txt",
            score_multiplier=2.5,
        )
        assert byok_rag.score_multiplier == 2.5

    def test_byok_rag_configuration_score_multiplier_must_be_positive(self) -> None:
        """Test that score_multiplier must be greater than 0."""
        with pytest.raises(ValidationError, match="greater than 0"):
            _ = ByokRag(
                rag_id="rag_id",
                backend="custom",
                vector_db_id="vector_db_id",
                embedding_model="embedding_model",
                embedding_dimension=1024,
                db_path="tests/configuration/rag.txt",
                score_multiplier=0.0,
            )

    def test_byok_rag_faiss_requires_db_path(self) -> None:
        """Test that inline::faiss requires db_path."""
        with pytest.raises(ValidationError, match="db_path is required"):
            _ = ByokRag(
                rag_id="rag_id",
                backend="faiss",
                vector_db_id="vector_db_id",
            )

    def test_byok_rag_pgvector_defaults(self) -> None:
        """Test pgvector auto-populates connection fields with env var defaults."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            store = ByokRag(
                rag_id="pg_store",
                backend="pgvector",
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

    def test_byok_rag_pgvector_custom_connection_fields(self) -> None:
        """Test pgvector accepts custom connection field values."""
        store = ByokRag(
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
        password = store.password.get_secret_value()  # pylint: disable=no-member
        assert password == "secret"

    def test_byok_rag_pgvector_partial_overrides(self) -> None:
        """Test pgvector fills only missing connection fields with defaults."""
        store = ByokRag(
            rag_id="pg_store",
            backend="pgvector",
            vector_db_id="vs_pg",
            host="custom-host",
        )
        assert store.host == "custom-host"
        assert store.port == "${env.POSTGRES_PORT}"

    def test_byok_rag_pgvector_does_not_require_db_path(self) -> None:
        """Test pgvector does not require db_path."""
        store = ByokRag(
            rag_id="pg_store",
            backend="pgvector",
            vector_db_id="vs_pg",
        )
        assert store.db_path is None

    def test_byok_rag_legacy_rag_type_faiss(self) -> None:
        """Test backward compatibility: rag_type='inline::faiss' still works."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            store = ByokRag(  # pyright: ignore[reportCallIssue]
                rag_id="rag_id",
                rag_type="inline::faiss",
                vector_db_id="vector_db_id",
                db_path="tests/configuration/rag.txt",
            )
            assert store.rag_type == "inline::faiss"
            assert store.backend == "faiss"
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1


class TestHelperFunctions:
    """Tests for _strip_rag_type_prefix and _synthesize_rag_type."""

    def test_strip_inline_prefix(self) -> None:
        """Test stripping inline:: prefix."""
        assert _strip_rag_type_prefix("inline::faiss") == "faiss"

    def test_strip_remote_prefix(self) -> None:
        """Test stripping remote:: prefix."""
        assert _strip_rag_type_prefix("remote::pgvector") == "pgvector"

    def test_strip_no_prefix(self) -> None:
        """Test stripping when no prefix present."""
        assert _strip_rag_type_prefix("faiss") == "faiss"

    def test_synthesize_faiss(self) -> None:
        """Test synthesizing rag_type for faiss backend."""
        assert _synthesize_rag_type("faiss") == "inline::faiss"

    def test_synthesize_pgvector(self) -> None:
        """Test synthesizing rag_type for pgvector backend."""
        assert _synthesize_rag_type("pgvector") == "remote::pgvector"

    def test_synthesize_unknown(self) -> None:
        """Test synthesizing rag_type for unknown backend defaults to inline."""
        assert _synthesize_rag_type("chromadb") == "inline::chromadb"
