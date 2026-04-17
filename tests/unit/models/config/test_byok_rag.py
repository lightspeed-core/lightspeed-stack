"""Unit tests for ByokRag model."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from constants import (
    DEFAULT_BYOK_RAG_RELEVANCE_CUTOFF_SCORE,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RAG_TYPE,
    DEFAULT_SCORE_MULTIPLIER,
)
from models.config import ByokRag, ByokRagSection, Configuration


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
            db_path=Path("tests/configuration/rag.txt"),
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
            db_path=Path("tests/configuration/rag.txt"),
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
            db_path=Path("tests/configuration/rag.txt"),
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
            db_path=Path("tests/configuration/rag.txt"),
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
            db_path=Path("tests/configuration/rag.txt"),
        )


def test_byok_rag_configuration_custom_score_multiplier() -> None:
    """Test ByokRag with custom score_multiplier."""
    byok_rag = ByokRag(
        rag_id="rag_id",
        vector_db_id="vector_db_id",
        db_path="tests/configuration/rag.txt",
        score_multiplier=2.5,
    )
    assert byok_rag.score_multiplier == 2.5


def test_byok_rag_configuration_score_multiplier_must_be_positive() -> None:
    """Test that score_multiplier must be greater than 0."""
    with pytest.raises(ValidationError, match="greater than 0"):
        _ = ByokRag(
            rag_id="rag_id",
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            score_multiplier=0.0,
        )


def test_byok_rag_section_explicit_null_yields_defaults() -> None:
    """``byok_rag: null`` in YAML normalizes to defaults (empty entries, default cutoff)."""
    cfg = Configuration.model_validate(
        {
            "name": "t",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://x:1",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "byok_rag": None,
        }
    )
    assert cfg.byok_rag.entries == []
    assert (
        cfg.byok_rag.relevance_cutoff_score == DEFAULT_BYOK_RAG_RELEVANCE_CUTOFF_SCORE
    )


def test_byok_rag_section_object_and_legacy_list_in_configuration() -> None:
    """``byok_rag`` accepts a section object or a legacy list of stores."""
    db_path = "tests/configuration/rag.txt"
    from_list = Configuration.model_validate(
        {
            "name": "t",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://x:1",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "byok_rag": [
                {
                    "rag_id": "r1",
                    "vector_db_id": "vs1",
                    "db_path": db_path,
                },
            ],
        }
    )
    assert from_list.byok_rag.entries[0].rag_id == "r1"
    assert (
        from_list.byok_rag.relevance_cutoff_score
        == DEFAULT_BYOK_RAG_RELEVANCE_CUTOFF_SCORE
    )

    from_obj = Configuration.model_validate(
        {
            "name": "t",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://x:1",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "byok_rag": {
                "entries": [
                    {
                        "rag_id": "r2",
                        "vector_db_id": "vs2",
                        "db_path": db_path,
                    },
                ],
                "relevance_cutoff_score": 0.42,
            },
        }
    )
    assert from_obj.byok_rag.entries[0].rag_id == "r2"
    assert from_obj.byok_rag.relevance_cutoff_score == 0.42


def test_byok_rag_section_rejects_negative_cutoff() -> None:
    """relevance_cutoff_score must be non-negative."""
    with pytest.raises(ValidationError):
        _ = ByokRagSection(
            entries=[],
            relevance_cutoff_score=-0.1,
        )
