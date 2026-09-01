"""Integration tests for unified-mode synthesis (LCORE-2747).

These tests exercise the unified-mode synthesis path end to end — baseline
selection, enrichment, high-level inference expansion, and native_override
deep-merge — through real YAML files on disk, and confirm enrichment parity
with the legacy two-file path (requirement R7: enrichment yields the same
synthesized result in unified mode as legacy for equivalent inputs).

They fill the gap between the synthesizer unit tests (LCORE-2336, functions
in isolation) and the behave e2e suite (LCORE-2341/LCORE-2343, full running
service): everything here goes through the real configuration-load and
synthesis pipeline (``AppConfig.load_configuration``,
``synthesize_to_file``) without standing up the whole service.
"""

import copy
import os
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from configuration import configuration
from ogx_configuration import (
    CONDITIONAL_OPENAI_PROVIDER_ID,
    generate_configuration,
    load_default_baseline,
    migrate_config_dumb,
    synthesize_configuration,
    synthesize_to_file,
)

# A complete, valid lightspeed-stack.yaml used as the base for configs that
# are loaded through the real AppConfig.load_configuration pipeline;
# individual tests override its llama_stack / inference sections.
_BASE_CONFIG_PATH = "tests/configuration/lightspeed-stack.yaml"

# A representative operator-authored legacy run.yaml. It deliberately carries
# pre-existing entries in every section the enrichment touches (an existing
# vector_io provider, registered models, storage backends) so parity is
# checked for the append-to-existing paths, not just creation from nothing.
# It also already contains the default MCP tool_runtime provider: the unified
# pipeline runs ensure_mcp_tool_runtime for non-empty baselines while the
# legacy path does not, so exact parity is only expected for run.yaml files
# that (like all shipped ones) already carry that provider.
_OPERATOR_RUN_YAML: dict[str, Any] = {
    "version": 2,
    "apis": ["agents", "inference", "safety", "tool_runtime", "vector_io"],
    "providers": {
        "inference": [
            {
                "provider_id": "azure",
                "provider_type": "remote::azure",
                "config": {
                    "api_key": "${env.AZURE_API_KEY}",
                    "api_base": "https://azure.example.com",
                },
            },
            {
                "provider_id": "sentence-transformers",
                "provider_type": "inline::sentence-transformers",
            },
        ],
        "vector_io": [
            {
                "provider_id": "faiss",
                "provider_type": "inline::faiss",
                "config": {
                    "persistence": {
                        "backend": "kv_default",
                        "namespace": "vector_io::faiss",
                    }
                },
            }
        ],
        "tool_runtime": [
            {
                "provider_id": "model-context-protocol",
                "provider_type": "remote::model-context-protocol",
                "config": {},
            }
        ],
    },
    "storage": {
        "backends": {
            "kv_default": {
                "type": "kv_sqlite",
                "db_path": ".llama/kv_default.db",
            }
        }
    },
    "registered_resources": {
        "models": [
            {
                "model_id": "gpt-4o-mini",
                "provider_id": "azure",
                "model_type": "llm",
            }
        ]
    },
    "safety": {"default_shield_id": None, "excluded_categories": []},
}

# Enrichment inputs equivalent between the two modes: each dict is both the
# lightspeed config passed to legacy generate_configuration and the extra
# root-level content of the unified lightspeed-stack.yaml.
_BYOK_INPUTS: dict[str, Any] = {
    "rag": {
        "byok": {
            "stores": [
                {
                    "rag_id": "kb1",
                    "vector_db_id": "kb1",
                    "db_path": "/var/lib/kb1/faiss_store.db",
                    "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
                    "embedding_dimension": 768,
                }
            ],
        },
    },
}

_SOLR_INPUTS: dict[str, Any] = {
    "rag": {
        "okp": {
            "rhokp_url": "https://okp.example.com",
            "chunk_filter_query": "product:openshift",
        },
        "retrieval": {
            "inline": {"sources": ["okp"]},
        },
    },
}

_AZURE_INPUTS: dict[str, Any] = {
    "azure_entra_id": {
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "client_secret": "test-secret",
    }
}

_ALL_INPUTS: dict[str, Any] = {
    "rag": {
        **_BYOK_INPUTS["rag"],
        **_SOLR_INPUTS["rag"],
    },
    **_AZURE_INPUTS,
}


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    """Serialize ``data`` to ``path`` as YAML and return the path."""
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


def _legacy_enriched(tmp_path: Path, enrichment: dict[str, Any]) -> dict[str, Any]:
    """Run the legacy two-file path: enrich the operator run.yaml on disk."""
    run_path = _write_yaml(tmp_path / "run.yaml", _OPERATOR_RUN_YAML)
    out_path = tmp_path / "legacy-enriched.yaml"
    generate_configuration(str(run_path), str(out_path), enrichment)
    return yaml.safe_load(out_path.read_text(encoding="utf-8"))


def _base_config_dict() -> dict[str, Any]:
    """Load the base lightspeed-stack.yaml fixture as a fresh dict."""
    with open(_BASE_CONFIG_PATH, "r", encoding="utf-8") as file:
        return copy.deepcopy(yaml.safe_load(file))


def _load_and_synthesize(
    tmp_path: Path, lcs_dict: dict[str, Any]
) -> tuple[dict[str, Any], Path]:
    """Load a unified config through the real pipeline and synthesize it.

    Mirrors the runtime flow: the config file is validated via
    ``AppConfig.load_configuration`` (the same entry point the service uses),
    then — like ``client.AsyncOgxClientHolder`` — the raw operator
    YAML is re-read and handed to ``synthesize_to_file``.

    Returns the synthesized run.yaml as a dict plus the output file path.
    """
    cfg_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)
    configuration.load_configuration(str(cfg_path))
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    out_path = tmp_path / "synthesized-run.yaml"
    synthesize_to_file(raw, str(out_path), str(tmp_path))
    return yaml.safe_load(out_path.read_text(encoding="utf-8")), out_path


# ---------------------------------------------------------------------------
# R7 enrichment parity: unified synthesis vs legacy generate_configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "enrichment",
    [
        pytest.param(_BYOK_INPUTS, id="byok-rag"),
        pytest.param(_SOLR_INPUTS, id="solr-okp"),
        pytest.param(_AZURE_INPUTS, id="azure-entra-id"),
        pytest.param(_ALL_INPUTS, id="all-combined"),
    ],
)
def test_synthesis_parity_with_legacy_enrichment(
    tmp_path: Path, enrichment: dict[str, Any]
) -> None:
    """Unified synthesis equals legacy enrichment for equivalent inputs (R7).

    The unified equivalent of a legacy (run.yaml + enrichment inputs) setup
    uses the very same run.yaml as its synthesis profile: both paths then
    start from identical content and apply the same enrichment.
    """
    legacy = _legacy_enriched(tmp_path, enrichment)

    run_path = tmp_path / "run.yaml"  # written by _legacy_enriched
    unified_cfg: dict[str, Any] = {
        "ogx": {
            "use_as_library_client": True,
            "config": {"profile": str(run_path)},
        },
        **enrichment,
    }
    synthesized = synthesize_configuration(unified_cfg, config_file_dir=str(tmp_path))

    assert synthesized == legacy


def test_synthesis_parity_holds_through_real_config_load(tmp_path: Path) -> None:
    """R7 parity holds when the unified config passes the real load pipeline.

    Same comparison as above for the BYOK case, but the unified file is a
    complete lightspeed-stack.yaml validated by AppConfig.load_configuration
    and synthesized to disk via synthesize_to_file — the exact runtime flow.
    """
    legacy = _legacy_enriched(tmp_path, _BYOK_INPUTS)

    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {"profile": "run.yaml"},  # relative to the config file dir
    }
    lcs_dict.update(_BYOK_INPUTS)
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    assert synthesized == legacy


# ---------------------------------------------------------------------------
# Baseline selection through the real load + synthesis path
# ---------------------------------------------------------------------------


def test_default_baseline_through_real_load(tmp_path: Path) -> None:
    """baseline: default synthesizes from the shipped src/data/default_run.yaml."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {"baseline": "default"},
    }
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    baseline = load_default_baseline()
    assert synthesized["version"] == baseline["version"]
    assert set(baseline["apis"]).issubset(set(synthesized["apis"]))
    mcp_ids = {p["provider_id"] for p in synthesized["providers"]["tool_runtime"]}
    assert "model-context-protocol" in mcp_ids


def test_byo_llm_baseline_through_real_load(tmp_path: Path) -> None:
    """baseline: byo-llm synthesizes from default_run.yaml without the OpenAI row."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {"baseline": "byo-llm"},
    }
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    baseline = load_default_baseline()
    assert synthesized["version"] == baseline["version"]
    for entry in synthesized["providers"]["inference"]:
        if not isinstance(entry, dict):
            continue
        assert entry.get("provider_type") != "remote::openai"
        assert entry.get("provider_id") not in (
            "openai",
            CONDITIONAL_OPENAI_PROVIDER_ID,
        )
    inference_ids = [
        entry["provider_id"]
        for entry in synthesized["providers"]["inference"]
        if isinstance(entry, dict)
    ]
    assert "sentence-transformers" in inference_ids
    mcp_ids = {p["provider_id"] for p in synthesized["providers"]["tool_runtime"]}
    assert "model-context-protocol" in mcp_ids


def test_empty_baseline_with_native_override_through_real_load(
    tmp_path: Path,
) -> None:
    """baseline: empty + native_override reproduces the override exactly (T7)."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {
            "baseline": "empty",
            "native_override": copy.deepcopy(_OPERATOR_RUN_YAML),
        },
    }
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    assert synthesized == _OPERATOR_RUN_YAML


def test_profile_baseline_through_real_load_gets_mcp_ensured(
    tmp_path: Path,
) -> None:
    """A profile baseline is loaded from disk and MCP tool_runtime is ensured."""
    profile = {
        "version": 2,
        "apis": ["inference"],
        "marker": "from-profile",
    }
    _write_yaml(tmp_path / "my-profile.yaml", profile)

    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {"profile": "my-profile.yaml"},
    }
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    assert synthesized["marker"] == "from-profile"
    # ensure_mcp_tool_runtime ran (profile baselines are not "empty")
    assert "tool_runtime" in synthesized["apis"]
    mcp_ids = {p["provider_id"] for p in synthesized["providers"]["tool_runtime"]}
    assert "model-context-protocol" in mcp_ids


def test_native_override_deep_merge_through_real_load(tmp_path: Path) -> None:
    """native_override merges over the profile: scalars win, lists replace."""
    profile = {
        "version": 2,
        "apis": ["inference", "tool_runtime"],
        "providers": {
            "inference": [{"provider_id": "old", "provider_type": "remote::openai"}],
            "tool_runtime": [
                {
                    "provider_id": "model-context-protocol",
                    "provider_type": "remote::model-context-protocol",
                    "config": {},
                }
            ],
        },
        "safety": {"default_shield_id": "guard", "excluded_categories": []},
    }
    _write_yaml(tmp_path / "my-profile.yaml", profile)

    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {
            "profile": "my-profile.yaml",
            "native_override": {
                "providers": {
                    "inference": [
                        {"provider_id": "new", "provider_type": "remote::vllm"}
                    ]
                },
                "safety": {"default_shield_id": "other-guard"},
                "added_key": "added-value",
            },
        },
    }
    synthesized, _ = _load_and_synthesize(tmp_path, lcs_dict)

    # list replaced wholesale (deep_merge_list_replace semantics, R5)
    assert synthesized["providers"]["inference"] == [
        {"provider_id": "new", "provider_type": "remote::vllm"}
    ]
    # sibling dict keys merge: overridden scalar wins, untouched one survives
    assert synthesized["safety"]["default_shield_id"] == "other-guard"
    assert synthesized["safety"]["excluded_categories"] == []
    # brand-new top-level key added
    assert synthesized["added_key"] == "added-value"
    # untouched profile content survives
    assert synthesized["version"] == 2


def test_synthesized_file_written_owner_only(tmp_path: Path) -> None:
    """The synthesized run.yaml lands on disk with mode 0600 (R10)."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "config": {"baseline": "empty", "native_override": {"version": 2}},
    }
    _, out_path = _load_and_synthesize(tmp_path, lcs_dict)

    assert stat.S_IMODE(os.stat(out_path).st_mode) == 0o600


# ---------------------------------------------------------------------------
# Migrate-then-synthesize parity (LCORE-2337 migration tool)
# ---------------------------------------------------------------------------


def _migrate_then_synthesize(
    tmp_path: Path, run_yaml: dict[str, Any], enrichment: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Enrich a legacy pair both ways: directly, and after --migrate-config.

    Returns (legacy_enriched, migrated_synthesized) for comparison.
    """
    run_path = _write_yaml(tmp_path / "run.yaml", run_yaml)
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "library_client_config_path": str(run_path),
    }
    lcs_dict.update(enrichment)
    lcs_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)

    legacy_out = tmp_path / "legacy-enriched.yaml"
    generate_configuration(str(run_path), str(legacy_out), lcs_dict)
    legacy = yaml.safe_load(legacy_out.read_text(encoding="utf-8"))

    unified_path = tmp_path / "unified.yaml"
    migrate_config_dumb(str(run_path), str(lcs_path), str(unified_path))
    # the migrated file must load through the real validation pipeline
    configuration.load_configuration(str(unified_path))
    migrated_raw = yaml.safe_load(unified_path.read_text(encoding="utf-8"))
    synthesized = synthesize_configuration(migrated_raw, config_file_dir=str(tmp_path))
    return legacy, synthesized


def test_migrate_then_synthesize_round_trip_without_enrichment(
    tmp_path: Path,
) -> None:
    """Migrating a pair with no enrichment inputs reproduces run.yaml (T7)."""
    legacy, synthesized = _migrate_then_synthesize(tmp_path, _OPERATOR_RUN_YAML, {})
    assert synthesized == _OPERATOR_RUN_YAML
    assert legacy == synthesized


def test_migrate_then_synthesize_preserves_enrichment_parity(
    tmp_path: Path,
) -> None:
    """A migrated config still enriches like legacy mode did (R7 after R4).

    migrate_config_dumb keeps byok_rag/rag/okp/azure_entra_id untouched, so
    synthesizing the migrated config must yield the same result the legacy
    path produced for the original pair.
    """
    enrichment = _ALL_INPUTS
    legacy, synthesized = _migrate_then_synthesize(
        tmp_path, _OPERATOR_RUN_YAML, enrichment
    )
    assert synthesized == legacy


# ---------------------------------------------------------------------------
# Mode detection via the real config load
# ---------------------------------------------------------------------------


def test_load_rejects_config_block_and_legacy_path_together(
    tmp_path: Path,
) -> None:
    """A llama_stack.config block plus a legacy path fails the real load (R3)."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
        "config": {"baseline": "default"},
    }
    cfg_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)
    with pytest.raises(ValidationError, match="--migrate-config"):
        configuration.load_configuration(str(cfg_path))


def test_load_rejects_inference_providers_and_legacy_path_together(
    tmp_path: Path,
) -> None:
    """Top-level inference.providers plus a legacy path fails the real load."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
    }
    lcs_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    cfg_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)
    with pytest.raises(ValidationError, match="mutually exclusive"):
        configuration.load_configuration(str(cfg_path))


def test_load_rejects_library_mode_without_run_source(tmp_path: Path) -> None:
    """Library mode with neither synthesis input nor legacy path fails."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {"use_as_library_client": True}
    cfg_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)
    with pytest.raises(ValidationError, match="requires a run-configuration source"):
        configuration.load_configuration(str(cfg_path))


def test_load_accepts_minimal_unified_config(tmp_path: Path) -> None:
    """A minimal unified config (inference.providers only) loads cleanly."""
    lcs_dict = _base_config_dict()
    lcs_dict["ogx"] = {"use_as_library_client": True}
    lcs_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    cfg_path = _write_yaml(tmp_path / "lightspeed-stack.yaml", lcs_dict)
    configuration.load_configuration(str(cfg_path))

    loaded = configuration.configuration
    assert loaded.ogx.config is None
    assert loaded.inference.providers[0].type == "openai"
