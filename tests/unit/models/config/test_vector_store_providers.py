"""Unit tests for vector_store_providers config models."""

import copy
from typing import Any

import pytest
import yaml
from pydantic import SecretStr, TypeAdapter, ValidationError

from models.config import Configuration, VectorStoreProvider

_PROVIDER_ADAPTER = TypeAdapter(VectorStoreProvider)

_BASE_CONFIG_PATH = "tests/configuration/lightspeed-stack.yaml"


def _base_config_dict() -> dict[str, Any]:
    """Load the base lightspeed-stack.yaml fixture as a fresh dict."""
    with open(_BASE_CONFIG_PATH, "r", encoding="utf-8") as file:
        return copy.deepcopy(yaml.safe_load(file))


def _faiss_provider(
    *,
    provider_id: str = "notebooks",
    default: bool = False,
    path: str = "/var/lib/notebooks.db",
) -> dict[str, Any]:
    """Return a minimal valid faiss vector_store_providers entry."""
    return {
        "id": provider_id,
        "type": "faiss",
        "default": default,
        "embedding_model": "/rag-content/embeddings_model",
        "embedding_dimension": 768,
        "config": {"path": path},
    }


def test_faiss_provider_accepts_nested_config() -> None:
    """Faiss provider accepts nested config and required embedding fields."""
    provider = _PROVIDER_ADAPTER.validate_python(
        {
            "id": "notebooks",
            "type": "faiss",
            "embedding_model": "/rag-content/embeddings_model",
            "embedding_dimension": 768,
            "default": True,
            "config": {"path": "/var/lib/notebooks.db"},
        }
    )
    assert provider.id == "notebooks"
    assert provider.type == "faiss"
    assert provider.config.path == "/var/lib/notebooks.db"
    assert provider.embedding_dimension == 768
    assert provider.default is True


def test_faiss_requires_path() -> None:
    """Faiss provider rejects missing path under config."""
    with pytest.raises(ValidationError):
        _PROVIDER_ADAPTER.validate_python(
            {
                "id": "notebooks",
                "type": "faiss",
                "embedding_model": "/emb",
                "embedding_dimension": 768,
                "config": {},
            }
        )


def test_requires_embedding_model_and_dimension() -> None:
    """Provider entry requires embedding_model and embedding_dimension."""
    with pytest.raises(ValidationError):
        _PROVIDER_ADAPTER.validate_python(
            {
                "id": "notebooks",
                "type": "faiss",
                "config": {"path": "/tmp/x.db"},
            }
        )


def test_pgvector_applies_env_defaults() -> None:
    """Pgvector provider fills unset connection fields with env placeholders."""
    provider = _PROVIDER_ADAPTER.validate_python(
        {
            "id": "nb-pg",
            "type": "pgvector",
            "embedding_model": "/emb",
            "embedding_dimension": 768,
            "default": True,
            "config": {},
        }
    )
    assert provider.config.host == "${env.POSTGRES_HOST}"
    assert provider.config.password == SecretStr("${env.POSTGRES_PASSWORD}")


def test_rejects_byok_prefix_id() -> None:
    """Provider id must not use the byok_ prefix reserved for BYOK RAG."""
    with pytest.raises(ValidationError, match="byok_"):
        _PROVIDER_ADAPTER.validate_python(
            {
                "id": "byok_notebooks",
                "type": "faiss",
                "embedding_model": "/emb",
                "embedding_dimension": 768,
                "config": {"path": "/tmp/x.db"},
            }
        )


def test_rejects_invalid_id_chars() -> None:
    """Provider id must match [a-z0-9_-]+."""
    with pytest.raises(ValidationError):
        _PROVIDER_ADAPTER.validate_python(
            {
                "id": "NoteBooks",
                "type": "faiss",
                "embedding_model": "/emb",
                "embedding_dimension": 768,
                "config": {"path": "/tmp/x.db"},
            }
        )


def test_rejects_unknown_type() -> None:
    """Unknown product type values are rejected."""
    with pytest.raises(ValidationError):
        _PROVIDER_ADAPTER.validate_python(
            {
                "id": "x",
                "type": "chroma",
                "embedding_model": "/emb",
                "embedding_dimension": 768,
                "config": {"path": "/tmp/x.db"},
            }
        )


def test_rejects_non_empty_list_with_no_default() -> None:
    """Non-empty list with no default: true is rejected."""
    config_dict = _base_config_dict()
    config_dict["vector_store_providers"] = [_faiss_provider(default=False)]
    with pytest.raises(ValidationError, match="default"):
        Configuration(**config_dict)


def test_rejects_multiple_defaults() -> None:
    """Non-empty list with more than one default: true is rejected."""
    config_dict = _base_config_dict()
    config_dict["vector_store_providers"] = [
        _faiss_provider(provider_id="a", default=True, path="/tmp/a.db"),
        _faiss_provider(provider_id="b", default=True, path="/tmp/b.db"),
    ]
    with pytest.raises(ValidationError, match="default"):
        Configuration(**config_dict)


def test_duplicate_ids_rejected() -> None:
    """Provider ids must be unique within vector_store_providers."""
    config_dict = _base_config_dict()
    config_dict["vector_store_providers"] = [
        _faiss_provider(provider_id="notebooks", default=True, path="/tmp/a.db"),
        _faiss_provider(provider_id="notebooks", default=False, path="/tmp/b.db"),
    ]
    with pytest.raises(ValidationError, match="unique|duplicate"):
        Configuration(**config_dict)


def test_empty_list_ok_without_default() -> None:
    """Empty vector_store_providers list is valid without a designated default."""
    config_dict = _base_config_dict()
    config_dict["vector_store_providers"] = []
    cfg = Configuration(**config_dict)
    assert cfg.vector_store_providers == []


def test_single_default_provider_accepted() -> None:
    """Non-empty list with exactly one default: true validates."""
    config_dict = _base_config_dict()
    config_dict["vector_store_providers"] = [
        _faiss_provider(provider_id="notebooks", default=True),
        _faiss_provider(provider_id="other", default=False, path="/tmp/other.db"),
    ]
    cfg = Configuration(**config_dict)
    by_id = {provider.id: provider.default for provider in cfg.vector_store_providers}
    assert by_id == {"notebooks": True, "other": False}
