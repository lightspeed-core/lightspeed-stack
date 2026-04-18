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
from models.config import ByokRag, Configuration


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
    assert byok_rag.relevance_cutoff_score == DEFAULT_BYOK_RAG_RELEVANCE_CUTOFF_SCORE
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


def test_byok_rag_explicit_null_yields_empty_list() -> None:
    """``byok_rag: null`` in YAML normalizes to an empty list."""
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
    assert cfg.byok_rag == []


def test_byok_rag_list_in_configuration() -> None:
    """``byok_rag`` is a YAML list of stores."""
    db_path = "tests/configuration/rag.txt"
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
            "byok_rag": [
                {
                    "rag_id": "r1",
                    "vector_db_id": "vs1",
                    "db_path": db_path,
                },
            ],
        }
    )
    assert cfg.byok_rag[0].rag_id == "r1"
    assert (
        cfg.byok_rag[0].relevance_cutoff_score
        == DEFAULT_BYOK_RAG_RELEVANCE_CUTOFF_SCORE
    )


def test_byok_rag_rejects_top_level_mapping() -> None:
    """A mapping (including ``entries``) at top level is not valid."""
    db_path = "tests/configuration/rag.txt"
    with pytest.raises(ValidationError):
        Configuration.model_validate(
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


def test_byok_rag_rejects_negative_cutoff_on_entry() -> None:
    """relevance_cutoff_score on each entry must be non-negative."""
    with pytest.raises(ValidationError):
        _ = ByokRag(
            rag_id="rag_id",
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            relevance_cutoff_score=-0.1,
        )


@pytest.mark.parametrize(
    "non_finite",
    [float("inf"), float("-inf"), float("nan")],
)
def test_byok_rag_rejects_non_finite_relevance_cutoff(non_finite: float) -> None:
    """relevance_cutoff_score must be finite (reject inf and nan)."""
    with pytest.raises(ValidationError):
        _ = ByokRag(
            rag_id="rag_id",
            vector_db_id="vector_db_id",
            db_path="tests/configuration/rag.txt",
            relevance_cutoff_score=non_finite,
        )
