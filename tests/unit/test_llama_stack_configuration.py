"""Unit tests for src/llama_stack_configuration.py."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from llama_stack_configuration import (
    _raw_byok_rag_store_list,
    construct_models_section,
    construct_storage_backends_section,
    construct_vector_io_providers_section,
    construct_vector_stores_section,
    dedupe_providers_vector_io,
    enrich_byok_rag,
    enrich_solr,
    generate_configuration,
)
from models.config import (
    Configuration,
    InferenceConfiguration,
    LlamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
)

# =============================================================================
# Test _raw_byok_rag_store_list
# =============================================================================


def test_raw_byok_rag_store_list_returns_list_as_is() -> None:
    """YAML list form returns the same sequence."""
    raw = [{"rag_id": "a"}]
    assert _raw_byok_rag_store_list(raw) is raw


def test_raw_byok_rag_store_list_non_list_yields_empty() -> None:
    """Only a list is used; mappings and other types yield []."""
    assert _raw_byok_rag_store_list({"entries": [{"rag_id": "x"}]}) == []
    assert _raw_byok_rag_store_list({}) == []
    assert _raw_byok_rag_store_list(None) == []
    assert _raw_byok_rag_store_list("byok") == []


# =============================================================================
# Test construct_vector_stores_section
# =============================================================================


def test_construct_vector_stores_section_empty() -> None:
    """Test with no BYOK RAG config."""
    ls_config: dict[str, Any] = {}
    byok_rag: list[dict[str, Any]] = []
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 0


def test_construct_vector_stores_section_preserves_existing() -> None:
    """Test preserves existing vector_stores entries."""
    ls_config = {
        "registered_resources": {
            "vector_stores": [
                {"vector_store_id": "existing", "provider_id": "existing_provider"},
            ]
        }
    }
    byok_rag: list[dict[str, Any]] = []
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["vector_store_id"] == "existing"


def test_construct_vector_stores_section_adds_new() -> None:
    """Test adds new BYOK RAG entries."""
    ls_config: dict[str, Any] = {}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "embedding_model": "test-model",
            "embedding_dimension": 512,
        },
    ]
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["vector_store_id"] == "store1"
    assert output[0]["provider_id"] == "byok_rag1"
    assert output[0]["embedding_model"] == "test-model"
    assert output[0]["embedding_dimension"] == 512


def test_construct_vector_stores_section_merge() -> None:
    """Test merges existing and new entries."""
    ls_config = {
        "registered_resources": {"vector_stores": [{"vector_store_id": "existing"}]}
    }
    byok_rag = [{"rag_id": "rag1", "vector_db_id": "new_store"}]
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 2


def test_construct_vector_stores_section_skips_duplicate_from_existing() -> None:
    """Test skips BYOK entry when vector_store_id already exists in config."""
    ls_config = {
        "registered_resources": {
            "vector_stores": [
                {"vector_store_id": "store1", "provider_id": "original_provider"},
            ]
        }
    }
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "embedding_model": "test-model",
            "embedding_dimension": 512,
        },
    ]
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_id"] == "original_provider"


def test_construct_vector_stores_section_skips_duplicate_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test skips BYOK entry when existing store uses an env var that resolves to the same ID."""
    monkeypatch.setenv("FAISS_VECTOR_STORE_ID", "vs_abc123")
    ls_config = {
        "registered_resources": {
            "vector_stores": [
                {
                    "vector_store_id": "${env.FAISS_VECTOR_STORE_ID}",
                    "provider_id": "faiss",
                },
            ]
        }
    }
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "vs_abc123",
            "embedding_model": "test-model",
            "embedding_dimension": 768,
        },
    ]
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_id"] == "faiss"


def test_construct_vector_stores_section_skips_duplicate_within_byok() -> None:
    """Test skips duplicate vector_db_id entries within the BYOK RAG list."""
    ls_config: dict[str, Any] = {}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "embedding_model": "model-a",
            "embedding_dimension": 512,
        },
        {
            "rag_id": "rag2",
            "vector_db_id": "store1",
            "embedding_model": "model-b",
            "embedding_dimension": 768,
        },
    ]
    output = construct_vector_stores_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["embedding_model"] == "model-a"


# =============================================================================
# Test construct_vector_io_providers_section
# =============================================================================


def test_construct_vector_io_providers_section_empty() -> None:
    """Test with no BYOK RAG config."""
    ls_config: dict[str, Any] = {"providers": {}}
    byok_rag: list[dict[str, Any]] = []
    output = construct_vector_io_providers_section(ls_config, byok_rag)
    assert len(output) == 0


def test_construct_vector_io_providers_section_preserves_existing() -> None:
    """Test preserves existing vector_io entries."""
    ls_config = {"providers": {"vector_io": [{"provider_id": "existing"}]}}
    byok_rag: list[dict[str, Any]] = []
    output = construct_vector_io_providers_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_id"] == "existing"


def test_construct_vector_io_providers_section_adds_new() -> None:
    """Test adds new BYOK RAG entries using rag_id for provider naming."""
    ls_config: dict[str, Any] = {"providers": {}}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "rag_type": "inline::faiss",
        },
    ]
    output = construct_vector_io_providers_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_id"] == "byok_rag1"
    assert output[0]["provider_type"] == "inline::faiss"
    assert output[0]["config"]["persistence"]["backend"] == "byok_rag1_storage"
    assert output[0]["config"]["persistence"]["namespace"] == "vector_io::faiss"


def test_construct_vector_io_providers_section_idempotent_reenrichment() -> None:
    """Re-running enrichment on already-enriched config must not duplicate BYOK providers."""
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "rag_type": "inline::faiss",
        },
    ]
    ls_config: dict[str, Any] = {"providers": {}}
    first = construct_vector_io_providers_section(ls_config, byok_rag)
    ls_config["providers"] = {"vector_io": first}
    second = construct_vector_io_providers_section(ls_config, byok_rag)
    assert len(second) == 1
    assert second[0]["provider_id"] == "byok_rag1"


def test_construct_vector_io_providers_section_collapses_existing_duplicates() -> None:
    """Legacy run.yaml may list the same provider_id multiple times; keep one."""
    dup = {
        "provider_id": "byok_rag1",
        "provider_type": "inline::faiss",
        "config": {
            "persistence": {
                "namespace": "vector_io::faiss",
                "backend": "byok_rag1_storage",
            }
        },
    }
    ls_config: dict[str, Any] = {
        "providers": {"vector_io": [dup, dup, dup]},
    }
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "rag_type": "inline::faiss",
        },
    ]
    output = construct_vector_io_providers_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_id"] == "byok_rag1"


def test_enrich_byok_rag_skipped_still_dedupes_vector_io() -> None:
    """When BYOK is off, existing duplicate vector_io entries are still collapsed."""
    dup = {
        "provider_id": "byok_x",
        "provider_type": "inline::faiss",
        "config": {"persistence": {"namespace": "vector_io::faiss", "backend": "b"}},
    }
    ls_config: dict[str, Any] = {"providers": {"vector_io": [dup, dup, dup]}}
    enrich_byok_rag(ls_config, [])
    assert len(ls_config["providers"]["vector_io"]) == 1


def test_dedupe_providers_vector_io_in_place() -> None:
    """dedupe_providers_vector_io keeps one entry per provider_id."""
    a = {"provider_id": "p1", "provider_type": "inline::faiss", "config": {}}
    ls_config: dict[str, Any] = {
        "providers": {"vector_io": [a, a, {"provider_id": "p2"}]}
    }
    dedupe_providers_vector_io(ls_config)
    ids = [p["provider_id"] for p in ls_config["providers"]["vector_io"]]
    assert ids == ["p1", "p2"]


# =============================================================================
# Test construct_storage_backends_section
# =============================================================================


def test_construct_storage_backends_section_empty() -> None:
    """Test with no BYOK RAG config."""
    ls_config: dict[str, Any] = {}
    byok_rag: list[dict[str, Any]] = []
    output = construct_storage_backends_section(ls_config, byok_rag)
    assert len(output) == 0


def test_construct_storage_backends_section_preserves_existing() -> None:
    """Test preserves existing backends."""
    ls_config = {
        "storage": {
            "backends": {
                "kv_default": {"type": "kv_sqlite", "db_path": "~/.llama/kv.db"}
            }
        }
    }
    byok_rag: list[dict[str, Any]] = []
    output = construct_storage_backends_section(ls_config, byok_rag)
    assert len(output) == 1
    assert "kv_default" in output


def test_construct_storage_backends_section_adds_new() -> None:
    """Test adds new BYOK RAG backend entries using rag_id for backend naming."""
    ls_config: dict[str, Any] = {}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "db_path": "/path/to/store1.db",
        },
    ]
    output = construct_storage_backends_section(ls_config, byok_rag)
    assert len(output) == 1
    assert "byok_rag1_storage" in output
    assert output["byok_rag1_storage"]["type"] == "kv_sqlite"
    assert output["byok_rag1_storage"]["db_path"] == "/path/to/store1.db"


# =============================================================================
# Test construct_models_section
# =============================================================================


def test_construct_models_section_empty() -> None:
    """Test with no BYOK RAG config."""
    ls_config: dict[str, Any] = {}
    byok_rag: list[dict[str, Any]] = []
    output = construct_models_section(ls_config, byok_rag)
    assert len(output) == 0


def test_construct_models_section_preserves_existing() -> None:
    """Test preserves existing models."""
    ls_config = {
        "registered_resources": {
            "models": [{"model_id": "existing", "model_type": "llm"}]
        }
    }
    byok_rag: list[dict[str, Any]] = []
    output = construct_models_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["model_id"] == "existing"


def test_construct_models_section_adds_embedding_model() -> None:
    """Test adds embedding model from BYOK RAG using rag_id for model naming."""
    ls_config: dict[str, Any] = {}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "embedding_model": "sentence-transformers/all-mpnet-base-v2",
            "embedding_dimension": 768,
        },
    ]
    output = construct_models_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["model_id"] == "byok_rag1_embedding"
    assert output[0]["model_type"] == "embedding"
    assert output[0]["provider_id"] == "sentence-transformers"
    assert output[0]["provider_model_id"] == "all-mpnet-base-v2"
    assert output[0]["metadata"]["embedding_dimension"] == 768


def test_construct_models_section_strips_prefix() -> None:
    """Test strips sentence-transformers/ prefix from embedding model."""
    ls_config: dict[str, Any] = {}
    byok_rag = [
        {
            "rag_id": "rag1",
            "vector_db_id": "store1",
            "embedding_model": "sentence-transformers//usr/path/model",
            "embedding_dimension": 768,
        },
    ]
    output = construct_models_section(ls_config, byok_rag)
    assert len(output) == 1
    assert output[0]["provider_model_id"] == "/usr/path/model"


def test_construct_storage_backends_section_raises_on_missing_rag_id() -> None:
    """Test raises ValueError when rag_id is missing from a BYOK RAG entry."""
    ls_config: dict[str, Any] = {}
    byok_rag = [{"vector_db_id": "store1"}]
    with pytest.raises(ValueError, match="missing required 'rag_id'"):
        construct_storage_backends_section(ls_config, byok_rag)


def test_construct_vector_stores_section_raises_on_missing_rag_id() -> None:
    """Test raises ValueError when rag_id is missing from a BYOK RAG entry."""
    ls_config: dict[str, Any] = {}
    byok_rag = [{"vector_db_id": "store1"}]
    with pytest.raises(ValueError, match="missing required 'rag_id'"):
        construct_vector_stores_section(ls_config, byok_rag)


def test_construct_vector_stores_section_raises_on_missing_vector_db_id() -> None:
    """Test raises ValueError when vector_db_id is missing from a BYOK RAG entry."""
    ls_config: dict[str, Any] = {}
    byok_rag = [{"rag_id": "rag1"}]
    with pytest.raises(ValueError, match="missing required 'vector_db_id'"):
        construct_vector_stores_section(ls_config, byok_rag)


def test_construct_vector_io_section_raises_on_missing_rag_id() -> None:
    """Test raises ValueError when rag_id is missing from a BYOK RAG entry."""
    ls_config: dict[str, Any] = {}
    byok_rag = [{"vector_db_id": "store1"}]
    with pytest.raises(ValueError, match="missing required 'rag_id'"):
        construct_vector_io_providers_section(ls_config, byok_rag)


def test_construct_models_section_raises_on_missing_rag_id() -> None:
    """Test raises ValueError when rag_id is missing from a BYOK RAG entry."""
    ls_config: dict[str, Any] = {}
    byok_rag = [{"vector_db_id": "store1", "embedding_model": "some-model"}]
    with pytest.raises(ValueError, match="missing required 'rag_id'"):
        construct_models_section(ls_config, byok_rag)


# =============================================================================
# Test generate_configuration
# =============================================================================


def test_generate_configuration_no_input_file(tmp_path: Path) -> None:
    """Test generate_configuration when input file does not exist."""
    config: dict[str, Any] = {}
    outfile = tmp_path / "output.yaml"

    with pytest.raises(FileNotFoundError):
        generate_configuration("/nonexistent/file.yaml", str(outfile), config)


def test_generate_configuration_dedupes_vector_io_on_load(tmp_path: Path) -> None:
    """Repeated vector_io entries with the same provider_id collapse on write."""
    entry: dict[str, Any] = {
        "provider_id": "byok_dupme",
        "provider_type": "inline::faiss",
        "config": {
            "persistence": {
                "namespace": "vector_io::faiss",
                "backend": "byok_dupme_storage",
            }
        },
    }
    infile = tmp_path / "in.yaml"
    outfile = tmp_path / "out.yaml"
    with open(infile, "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "version": 2,
                "providers": {"vector_io": [entry, entry, entry]},
                "registered_resources": {},
            },
            f,
        )
    generate_configuration(
        str(infile), str(outfile), {}, env_file=str(tmp_path / ".env")
    )
    with open(outfile, encoding="utf-8") as f:
        result = yaml.safe_load(f)
    dupme = [
        p
        for p in result["providers"]["vector_io"]
        if p.get("provider_id") == "byok_dupme"
    ]
    assert len(dupme) == 1


def test_generate_configuration_with_dict(tmp_path: Path) -> None:
    """Test generate_configuration accepts dict."""
    config: dict[str, Any] = {"byok_rag": []}
    outfile = tmp_path / "output.yaml"

    generate_configuration("tests/configuration/run.yaml", str(outfile), config)

    assert outfile.exists()
    with open(outfile, encoding="utf-8") as f:
        result = yaml.safe_load(f)
    assert "providers" in result


def test_generate_configuration_with_pydantic_model(tmp_path: Path) -> None:
    """Test generate_configuration accepts Pydantic model via model_dump()."""
    cfg = Configuration(  # type: ignore[call-arg]
        name="test",
        service=ServiceConfiguration(),  # type: ignore[call-arg]
        llama_stack=LlamaStackConfiguration(  # type: ignore[call-arg]
            use_as_library_client=True,
            library_client_config_path="run.yaml",
        ),
        user_data_collection=UserDataCollection(),  # type: ignore[call-arg]
        inference=InferenceConfiguration(),  # type: ignore[call-arg]
    )
    outfile = tmp_path / "output.yaml"

    # generate_configuration expects dict, so convert Pydantic model
    generate_configuration(
        "tests/configuration/run.yaml", str(outfile), cfg.model_dump()
    )

    assert outfile.exists()


def test_generate_configuration_with_byok(tmp_path: Path) -> None:
    """Test generate_configuration adds BYOK entries."""
    config = {
        "byok_rag": [
            {
                "rag_id": "rag1",
                "vector_db_id": "store1",
                "embedding_model": "test-model",
                "embedding_dimension": 256,
                "rag_type": "inline::faiss",
                "db_path": "/tmp/store1.db",
            },
        ],
    }
    outfile = tmp_path / "output.yaml"

    generate_configuration("tests/configuration/run.yaml", str(outfile), config)

    with open(outfile, encoding="utf-8") as f:
        result = yaml.safe_load(f)

    # Check registered_resources.vector_stores
    store_ids = [
        s["vector_store_id"] for s in result["registered_resources"]["vector_stores"]
    ]
    assert "store1" in store_ids

    # Check storage.backends - named after rag_id
    assert "byok_rag1_storage" in result["storage"]["backends"]

    # Check providers.vector_io - named after rag_id
    provider_ids = [p["provider_id"] for p in result["providers"]["vector_io"]]
    assert "byok_rag1" in provider_ids

    # Check registered_resources.models for embedding model - named after rag_id
    model_ids = [m["model_id"] for m in result["registered_resources"]["models"]]
    assert "byok_rag1_embedding" in model_ids


# =============================================================================
# Test enrich_solr
# =============================================================================


_OKP_RAG_CONFIG = {"inline": ["okp"]}


def test_enrich_solr_skips_when_not_enabled() -> None:
    """Test enrich_solr does nothing when OKP is not in rag inline or tool lists."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, {"inline": [], "tool": []}, {})
    assert not ls_config


def test_enrich_solr_skips_when_empty_config() -> None:
    """Test enrich_solr does nothing with empty rag config."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, {}, {})
    assert not ls_config


def test_enrich_solr_adds_vector_io_provider() -> None:
    """Test enrich_solr adds Solr provider to vector_io section."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    assert "providers" in ls_config
    assert "vector_io" in ls_config["providers"]
    provider_ids = [p["provider_id"] for p in ls_config["providers"]["vector_io"]]
    assert "okp_solr" in provider_ids


def test_enrich_solr_adds_vector_store_registration() -> None:
    """Test enrich_solr registers the Solr vector store."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    assert "registered_resources" in ls_config
    store_ids = [
        s["vector_store_id"] for s in ls_config["registered_resources"]["vector_stores"]
    ]
    assert "portal-rag" in store_ids


def test_enrich_solr_adds_embedding_model() -> None:
    """Test enrich_solr registers the Solr embedding model."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    model_ids = [m["model_id"] for m in ls_config["registered_resources"]["models"]]
    assert "solr_embedding" in model_ids


def test_enrich_solr_skips_duplicate_provider() -> None:
    """Test enrich_solr does not add duplicate Solr provider."""
    ls_config: dict[str, Any] = {
        "providers": {"vector_io": [{"provider_id": "okp_solr"}]}
    }
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    provider_ids = [p["provider_id"] for p in ls_config["providers"]["vector_io"]]
    assert provider_ids.count("okp_solr") == 1


def test_enrich_solr_skips_duplicate_vector_store() -> None:
    """Test enrich_solr does not add duplicate vector store registration."""
    ls_config: dict[str, Any] = {
        "registered_resources": {"vector_stores": [{"vector_store_id": "portal-rag"}]}
    }
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    store_ids = [
        s["vector_store_id"] for s in ls_config["registered_resources"]["vector_stores"]
    ]
    assert store_ids.count("portal-rag") == 1


def test_enrich_solr_preserves_existing_config() -> None:
    """Test enrich_solr preserves existing providers and resources."""
    ls_config: dict[str, Any] = {
        "providers": {"vector_io": [{"provider_id": "existing_provider"}]},
        "registered_resources": {
            "vector_stores": [{"vector_store_id": "existing_store"}],
            "models": [{"model_id": "existing_model"}],
        },
    }
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    provider_ids = [p["provider_id"] for p in ls_config["providers"]["vector_io"]]
    assert "existing_provider" in provider_ids
    assert "okp_solr" in provider_ids

    store_ids = [
        s["vector_store_id"] for s in ls_config["registered_resources"]["vector_stores"]
    ]
    assert "existing_store" in store_ids
    assert "portal-rag" in store_ids


def test_enrich_solr_default_chunk_filter_query() -> None:
    """Test enrich_solr uses the internal chunk filter when no user filter is set."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {})

    provider = next(
        p for p in ls_config["providers"]["vector_io"] if p["provider_id"] == "okp_solr"
    )
    assert (
        provider["config"]["chunk_window_config"]["chunk_filter_query"]
        == "is_chunk:true"
    )


def test_enrich_solr_user_chunk_filter_query_is_conjoined() -> None:
    """Test enrich_solr ANDs the user filter with the internal chunk filter."""
    ls_config: dict[str, Any] = {}
    enrich_solr(ls_config, _OKP_RAG_CONFIG, {"chunk_filter_query": "product:ansible"})

    provider = next(
        p for p in ls_config["providers"]["vector_io"] if p["provider_id"] == "okp_solr"
    )
    assert provider["config"]["chunk_window_config"]["chunk_filter_query"] == (
        "is_chunk:true AND product:ansible"
    )
