"""Unit tests for unified-mode Llama Stack configuration synthesis (LCORE-2336).

Covers the synthesizer pipeline and its helpers in
``src/llama_stack_configuration.py``: baseline loading, deep-merge semantics,
high-level inference expansion, the full synthesis pipeline, and the
write-to-file step (persistent path, mode 0600).
"""

import os
import stat
from pathlib import Path
from typing import Any, Optional, get_args

import pytest
import yaml

from llama_stack_configuration import (
    PROVIDER_TYPE_MAP,
    apply_high_level_inference,
    deep_merge_list_replace,
    ensure_mcp_tool_runtime,
    load_default_baseline,
    migrate_config_dumb,
    synthesize_configuration,
    synthesize_to_file,
)
from models.config import UnifiedInferenceProvider

# ---------------------------------------------------------------------------
# ensure_mcp_tool_runtime
# ---------------------------------------------------------------------------


def _tool_runtime_ids(ls_config: dict[str, Any]) -> list[Optional[str]]:
    """Return provider_id values from providers.tool_runtime."""
    providers = ls_config.get("providers") or {}
    return [
        entry.get("provider_id")
        for entry in providers.get("tool_runtime") or []
        if isinstance(entry, dict)
    ]


def test_ensure_mcp_tool_runtime_appends_and_preserves_rag() -> None:
    """MCP is appended; existing rag-runtime is untouched."""
    ls_config: dict[str, Any] = {
        "apis": ["tool_runtime"],
        "providers": {
            "tool_runtime": [
                {
                    "provider_id": "rag-runtime",
                    "provider_type": "inline::rag-runtime",
                    "config": {},
                }
            ]
        },
    }
    ensure_mcp_tool_runtime(ls_config)
    assert _tool_runtime_ids(ls_config) == [
        "rag-runtime",
        "model-context-protocol",
    ]

    found = False
    found_entry = {}
    for entry in ls_config["providers"]["tool_runtime"]:
        if (
            isinstance(entry, dict)
            and entry.get("provider_id") == "model-context-protocol"
        ):
            found = True
            found_entry = entry
            break
    assert found
    assert found_entry["provider_type"] == "remote::model-context-protocol"
    assert found_entry["config"] == {}


def test_ensure_mcp_tool_runtime_idempotent() -> None:
    """If MCP already exists, do not duplicate or rewrite it."""
    existing = {
        "provider_id": "model-context-protocol",
        "provider_type": "remote::model-context-protocol",
        "config": {"keep": True},
    }
    ls_config: dict[str, Any] = {
        "apis": ["tool_runtime"],
        "providers": {"tool_runtime": [existing]},
    }
    ensure_mcp_tool_runtime(ls_config)
    assert ls_config["providers"]["tool_runtime"] == [existing]


def test_ensure_mcp_tool_runtime_adds_api_when_missing() -> None:
    """Thin baselines get tool_runtime in apis and the MCP provider."""
    ls_config: dict[str, Any] = {}
    ensure_mcp_tool_runtime(ls_config)
    assert "tool_runtime" in ls_config["apis"]
    assert _tool_runtime_ids(ls_config) == ["model-context-protocol"]


# ---------------------------------------------------------------------------
# load_default_baseline
# ---------------------------------------------------------------------------


def test_load_default_baseline_returns_usable_dict() -> None:
    """The shipped baseline parses and carries the keys synthesis relies on."""
    baseline = load_default_baseline()
    assert isinstance(baseline, dict)
    assert "providers" in baseline
    assert "inference" in baseline["providers"]
    # The PoC gotcha: external_providers_dir must carry a default so the
    # baseline resolves when EXTERNAL_PROVIDERS_DIR is unset.
    assert ":=" in baseline["external_providers_dir"]


def test_load_default_baseline_includes_mcp_tool_runtime() -> None:
    """Default stack ships MCP beside rag-runtime (same rationale as RAG)."""
    baseline = load_default_baseline()
    ids = _tool_runtime_ids(baseline)
    assert "rag-runtime" in ids
    assert "model-context-protocol" in ids


# ---------------------------------------------------------------------------
# deep_merge_list_replace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base,overlay,expected",
    [
        # scalars replace
        ({"a": 1}, {"a": 2}, {"a": 2}),
        # maps merge recursively, untouched keys preserved
        (
            {"safety": {"default_shield_id": "llama-guard", "x": 1}},
            {"safety": {"x": 2}},
            {"safety": {"default_shield_id": "llama-guard", "x": 2}},
        ),
        # lists replace wholesale (no append)
        (
            {"safety": {"excluded_categories": ["violence", "sexual"]}},
            {"safety": {"excluded_categories": ["spam"]}},
            {"safety": {"excluded_categories": ["spam"]}},
        ),
        # new keys are added
        ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}),
        # type mismatch (map replaced by scalar) — overlay wins
        ({"a": {"nested": 1}}, {"a": 5}, {"a": 5}),
        # type mismatch (scalar replaced by map) — overlay wins
        ({"a": 5}, {"a": {"nested": 1}}, {"a": {"nested": 1}}),
    ],
)
def test_deep_merge_list_replace_semantics(
    base: dict[str, Any], overlay: dict[str, Any], expected: dict[str, Any]
) -> None:
    """Maps merge recursively; lists and scalars replace (Decision T2 / R5)."""
    assert deep_merge_list_replace(base, overlay) == expected


def test_deep_merge_list_replace_does_not_mutate_inputs() -> None:
    """The merge returns a new structure and leaves its arguments untouched."""
    base = {"safety": {"excluded_categories": ["a"]}}
    overlay = {"safety": {"excluded_categories": ["b"]}}
    result = deep_merge_list_replace(base, overlay)
    assert base == {"safety": {"excluded_categories": ["a"]}}
    assert overlay == {"safety": {"excluded_categories": ["b"]}}
    # mutating the result must not leak back into base
    result["safety"]["excluded_categories"].append("c")
    assert base["safety"]["excluded_categories"] == ["a"]


# ---------------------------------------------------------------------------
# apply_high_level_inference
# ---------------------------------------------------------------------------


def test_apply_high_level_inference_maps_type_and_emits_env_ref() -> None:
    """A remote provider maps to its provider_type with an ${env} api_key (R6)."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "openai",
                "api_key_env": "OPENAI_API_KEY",
                "allowed_models": ["gpt-4o-mini"],
                "extra": {},
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "openai"
    assert entry["provider_type"] == "remote::openai"
    assert entry["config"]["api_key"] == "${env.OPENAI_API_KEY}"
    assert entry["config"]["allowed_models"] == ["gpt-4o-mini"]


def test_apply_high_level_inference_hyphenates_provider_id() -> None:
    """sentence_transformers emits the hyphenated id the ecosystem expects."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {"providers": [{"type": "sentence_transformers"}]}
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "sentence-transformers"
    assert entry["provider_type"] == "inline::sentence-transformers"
    # no api_key / allowed_models -> no config block emitted
    assert "config" not in entry


def test_apply_high_level_inference_replaces_existing_provider_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A high-level provider replaces a baseline entry with the same id."""
    ls_config: dict[str, Any] = {
        "providers": {
            "inference": [
                {
                    "provider_id": "openai",
                    "provider_type": "remote::openai",
                    "config": {"api_key": "stale"},
                },
                {"provider_id": "other", "provider_type": "remote::vllm"},
            ]
        }
    }
    inference = {"providers": [{"type": "openai", "api_key_env": "NEW_KEY"}]}
    with caplog.at_level("INFO", logger="lightspeed_stack.llama_stack_configuration"):
        apply_high_level_inference(ls_config, inference)
    ids = [p["provider_id"] for p in ls_config["providers"]["inference"]]
    assert ids == ["openai", "other"]  # replaced in place, not duplicated
    openai = ls_config["providers"]["inference"][0]
    assert openai["config"]["api_key"] == "${env.NEW_KEY}"
    assert "provider_id='openai'" in caplog.text


def test_apply_high_level_inference_uses_explicit_id() -> None:
    """An explicit id is emitted as provider_id instead of the type-derived id."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "id": "vllm-prod",
                "api_key_env": "VLLM_API_KEY",
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm-prod"
    assert entry["provider_type"] == "remote::vllm"


def test_apply_high_level_inference_same_type_distinct_ids() -> None:
    """Two providers of the same type with distinct ids both appear."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "id": "vllm-prod",
                "api_key_env": "VLLM_PROD_KEY",
                "extra": {"url": "http://prod:8000"},
            },
            {
                "type": "vllm",
                "id": "vllm-staging",
                "api_key_env": "VLLM_STAGING_KEY",
                "extra": {"url": "http://staging:8000"},
            },
        ]
    }
    apply_high_level_inference(ls_config, inference)
    by_id = {e["provider_id"]: e for e in ls_config["providers"]["inference"]}
    assert set(by_id) == {"vllm-prod", "vllm-staging"}
    assert all(e["provider_type"] == "remote::vllm" for e in by_id.values())
    assert by_id["vllm-prod"]["config"]["url"] == "http://prod:8000"
    assert by_id["vllm-staging"]["config"]["url"] == "http://staging:8000"


def test_apply_high_level_inference_duplicate_id_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Duplicate id keeps the last entry and logs an info message."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "id": "vllm-shared",
                "api_key_env": "FIRST_KEY",
            },
            {
                "type": "vllm",
                "id": "vllm-shared",
                "api_key_env": "SECOND_KEY",
            },
        ]
    }
    with caplog.at_level("INFO", logger="lightspeed_stack.llama_stack_configuration"):
        apply_high_level_inference(ls_config, inference)
    entries = ls_config["providers"]["inference"]
    assert len(entries) == 1
    assert entries[0]["provider_id"] == "vllm-shared"
    assert entries[0]["config"]["api_token"] == "${env.SECOND_KEY}"
    assert "provider_id='vllm-shared'" in caplog.text


def test_apply_high_level_inference_merges_extra() -> None:
    """The extra mapping is merged verbatim into the provider config block."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "vllm_rhaiis", "extra": {"url": "http://x", "tls_verify": False}}
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm-rhaiis"
    assert entry["provider_type"] == "remote::vllm"
    assert entry["config"] == {"url": "http://x", "tls_verify": False}


def test_apply_high_level_inference_emits_api_token_for_vllm() -> None:
    """vLLM providers emit api_token from api_key_env, not api_key."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "vllm", "api_key_env": "VLLM_API_KEY"},
            {"type": "vllm_rhaiis", "api_key_env": "VLLM_API_KEY"},
        ]
    }
    apply_high_level_inference(ls_config, inference)
    vllm = ls_config["providers"]["inference"][0]
    vllm_rhaiis = ls_config["providers"]["inference"][1]
    assert vllm["provider_id"] == "vllm"
    assert vllm["provider_type"] == "remote::vllm"
    assert vllm["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert "api_key" not in vllm["config"]
    assert vllm_rhaiis["provider_id"] == "vllm-rhaiis"
    assert vllm_rhaiis["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert "api_key" not in vllm_rhaiis["config"]


def test_apply_high_level_inference_maps_ollama() -> None:
    """ollama maps to remote::ollama with extra config merged."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "ollama", "extra": {"base_url": "http://localhost:11434"}}
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "ollama"
    assert entry["provider_type"] == "remote::ollama"
    assert entry["config"]["base_url"] == "http://localhost:11434"


def test_apply_high_level_inference_maps_vllm() -> None:
    """vllm maps to remote::vllm with extra config merged."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "api_key_env": "VLLM_API_KEY",
                "extra": {"base_url": "${env.VLLM_URL:=}"},
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm"
    assert entry["provider_type"] == "remote::vllm"
    assert entry["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert entry["config"]["base_url"] == "${env.VLLM_URL:=}"


def test_apply_high_level_inference_extra_cannot_override_api_key_env() -> None:
    """api_key_env always wins over a conflicting key in extra."""
    ls_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "api_key_env": "VLLM_API_KEY",
                "extra": {"api_token": "hardcoded"},
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    entry = ls_config["providers"]["inference"][0]
    assert entry["config"]["api_token"] == "${env.VLLM_API_KEY}"


def test_unified_inference_provider_accepts_ollama_and_vllm() -> None:
    """Pydantic model accepts the new ollama and vllm Literal values."""
    ollama = UnifiedInferenceProvider(type="ollama")
    assert ollama.type == "ollama"
    vllm = UnifiedInferenceProvider(type="vllm")
    assert vllm.type == "vllm"


def test_apply_high_level_inference_empty_is_noop() -> None:
    """No providers -> the inference list is left as-is."""
    ls_config: dict[str, Any] = {"providers": {"inference": [{"provider_id": "x"}]}}
    apply_high_level_inference(ls_config, {"providers": []})
    assert ls_config["providers"]["inference"] == [{"provider_id": "x"}]


def test_provider_type_map_covers_every_literal_value() -> None:
    """Every UnifiedInferenceProvider.type value has a PROVIDER_TYPE_MAP entry."""
    literal_values = set(
        get_args(
            UnifiedInferenceProvider.model_fields[  # pylint: disable=unsubscriptable-object
                "type"
            ].annotation
        )
    )
    assert literal_values == set(PROVIDER_TYPE_MAP)


# ---------------------------------------------------------------------------
# synthesize_configuration
# ---------------------------------------------------------------------------


def test_synthesize_default_baseline_ensures_mcp() -> None:
    """Non-empty default baseline path always gets MCP (even with no mcp_servers)."""
    default_baseline: dict[str, Any] = {
        "apis": ["inference", "tool_runtime"],
        "providers": {
            "inference": [],
            "tool_runtime": [
                {
                    "provider_id": "rag-runtime",
                    "provider_type": "inline::rag-runtime",
                    "config": {},
                }
            ],
        },
    }
    lcs_config = {
        "llama_stack": {"config": {"baseline": "default"}},
        "inference": {"providers": []},
    }
    result = synthesize_configuration(lcs_config, default_baseline=default_baseline)
    assert "model-context-protocol" in _tool_runtime_ids(result)
    assert "rag-runtime" in _tool_runtime_ids(result)


def test_synthesize_empty_baseline_skips_mcp_ensure() -> None:
    """baseline: empty must not assume MCP."""
    lcs_config = {
        "llama_stack": {
            "config": {
                "baseline": "empty",
                "native_override": {
                    "version": 2,
                    "apis": ["inference"],
                    "providers": {"inference": []},
                },
            }
        }
    }
    result = synthesize_configuration(lcs_config)
    assert "model-context-protocol" not in _tool_runtime_ids(result)
    assert result["apis"] == ["inference"]


def test_synthesize_empty_baseline_keeps_mcp_from_override() -> None:
    """MCP already in native_override is preserved when ensure is skipped."""
    lcs_config = {
        "llama_stack": {
            "config": {
                "baseline": "empty",
                "native_override": {
                    "providers": {
                        "tool_runtime": [
                            {
                                "provider_id": "model-context-protocol",
                                "provider_type": "remote::model-context-protocol",
                                "config": {},
                            }
                        ]
                    }
                },
            }
        }
    }
    result = synthesize_configuration(lcs_config)
    assert _tool_runtime_ids(result) == ["model-context-protocol"]


def test_synthesize_native_override_can_opt_out_of_mcp() -> None:
    """List-replace of tool_runtime after ensure removes MCP (opt-out)."""
    default_baseline: dict[str, Any] = {
        "apis": ["tool_runtime"],
        "providers": {"tool_runtime": []},
    }
    lcs_config = {
        "llama_stack": {
            "config": {
                "baseline": "default",
                "native_override": {
                    "providers": {
                        "tool_runtime": [
                            {
                                "provider_id": "rag-runtime",
                                "provider_type": "inline::rag-runtime",
                                "config": {},
                            }
                        ]
                    }
                },
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=default_baseline)
    assert _tool_runtime_ids(result) == ["rag-runtime"]


def test_synthesize_profile_missing_mcp_gets_ensure(
    tmp_path: Path,
) -> None:
    """A thin profile without MCP still receives the provider via ensure."""
    profile = tmp_path / "thin.yaml"
    profile.write_text(
        yaml.dump(
            {
                "apis": ["inference"],
                "providers": {"inference": []},
            }
        ),
        encoding="utf-8",
    )
    lcs_config = {
        "llama_stack": {"config": {"profile": str(profile)}},
    }
    result = synthesize_configuration(lcs_config)
    assert "tool_runtime" in result["apis"]
    assert "model-context-protocol" in _tool_runtime_ids(result)


def test_synthesize_empty_profile_still_ensures_mcp(tmp_path: Path) -> None:
    """A profile that loads {} still gets ensure; only baseline: empty skips it."""
    profile = tmp_path / "empty-profile.yaml"
    profile.write_text("{}\n", encoding="utf-8")
    lcs_config = {
        "llama_stack": {"config": {"profile": str(profile)}},
    }
    result = synthesize_configuration(lcs_config)
    assert "tool_runtime" in result["apis"]
    assert "model-context-protocol" in _tool_runtime_ids(result)


def test_synthesize_from_empty_baseline_only_native_override() -> None:
    """baseline: empty starts from {} so native_override is the whole output."""
    lcs = {
        "llama_stack": {
            "config": {
                "baseline": "empty",
                "native_override": {"version": 2, "apis": ["inference"]},
            }
        }
    }
    result = synthesize_configuration(lcs)
    assert result == {"version": 2, "apis": ["inference"]}


def test_synthesize_from_default_baseline_applies_inference_and_override() -> None:
    """Default baseline + high-level inference + native_override compose (R1/R5)."""
    lcs = {
        "llama_stack": {
            "config": {
                "baseline": "default",
                "native_override": {"safety": {"default_shield_id": "custom"}},
            }
        },
        "inference": {
            "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
        },
    }
    result = synthesize_configuration(lcs)
    # high-level inference landed (env ref, never a literal secret)
    openai = next(
        p for p in result["providers"]["inference"] if p["provider_id"] == "openai"
    )
    assert openai["config"]["api_key"] == "${env.OPENAI_API_KEY}"
    # native_override deep-merged last
    assert result["safety"]["default_shield_id"] == "custom"


def test_synthesize_loads_profile_relative_to_config_dir(tmp_path: Path) -> None:
    """A relative profile: resolves against the config file's directory (R8)."""
    profile = {"version": 2, "apis": ["inference"], "marker": "from-profile"}
    (tmp_path / "my-profile.yaml").write_text(yaml.dump(profile), encoding="utf-8")
    lcs = {"llama_stack": {"config": {"profile": "my-profile.yaml"}}}
    result = synthesize_configuration(lcs, config_file_dir=str(tmp_path))
    assert result["marker"] == "from-profile"


def test_synthesize_uses_provided_default_baseline() -> None:
    """An explicit default_baseline arg is used without touching the shipped one."""
    lcs: dict[str, Any] = {"llama_stack": {"config": {"baseline": "default"}}}
    result = synthesize_configuration(lcs, default_baseline={"marker": "injected"})
    assert result["marker"] == "injected"


def test_synthesize_enriches_byok_rag_like_legacy() -> None:
    """BYOK RAG enrichment runs during synthesis for legacy parity (R7)."""
    lcs = {
        "llama_stack": {"config": {"baseline": "empty"}},
        "byok_rag": [
            {
                "rag_id": "kb1",
                "vector_db_id": "kb1",
                "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
                "embedding_dimension": 768,
            }
        ],
    }
    result = synthesize_configuration(lcs)
    # enrichment created the storage backends + vector_io provider section
    assert "storage" in result
    assert "vector_io" in result.get("providers", {})


# ---------------------------------------------------------------------------
# synthesize_to_file
# ---------------------------------------------------------------------------


def test_synthesize_to_file_writes_mode_0600(tmp_path: Path) -> None:
    """The synthesized file is written owner-only (R10) and round-trips."""
    out = tmp_path / "nested" / "run.yaml"
    lcs = {
        "llama_stack": {"config": {"baseline": "empty", "native_override": {"v": 2}}}
    }
    synthesize_to_file(lcs, str(out), str(tmp_path))
    assert out.exists()
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {"v": 2}


def test_synthesize_to_file_tightens_perms_on_overwrite(tmp_path: Path) -> None:
    """A pre-existing world-readable file is re-chmodded to 0600 on each boot."""
    out = tmp_path / "run.yaml"
    out.write_text("stale", encoding="utf-8")
    os.chmod(out, 0o644)
    lcs = {
        "llama_stack": {"config": {"baseline": "empty", "native_override": {"v": 3}}}
    }
    synthesize_to_file(lcs, str(out), str(tmp_path))
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {"v": 3}


# ---------------------------------------------------------------------------
# migrate_config_dumb (LCORE-2337)
# ---------------------------------------------------------------------------


# A representative legacy run.yaml body with nested maps, lists, and env refs.
_LEGACY_RUN_YAML: dict[str, Any] = {
    "version": 2,
    "apis": ["agents", "inference", "safety", "vector_io"],
    "providers": {
        "inference": [
            {
                "provider_id": "openai",
                "provider_type": "remote::openai",
                "config": {
                    "api_key": "${env.OPENAI_API_KEY}",
                    "allowed_models": ["gpt-4o-mini"],
                },
            },
            {
                "provider_id": "sentence-transformers",
                "provider_type": "inline::sentence-transformers",
            },
        ],
    },
    "safety": {"default_shield_id": "llama-guard", "excluded_categories": []},
}


def _write_legacy_pair(tmp_path: Path) -> tuple[str, str]:
    """Write a legacy run.yaml + lightspeed-stack.yaml pair, return their paths."""
    run_path = tmp_path / "run.yaml"
    run_path.write_text(yaml.dump(_LEGACY_RUN_YAML), encoding="utf-8")
    lcs = {
        "name": "LCS",
        "service": {"host": "localhost", "port": 8080},
        "llama_stack": {
            "use_as_library_client": True,
            "library_client_config_path": "run.yaml",
        },
    }
    lcs_path = tmp_path / "lightspeed-stack.yaml"
    lcs_path.write_text(yaml.dump(lcs), encoding="utf-8")
    return str(run_path), str(lcs_path)


def test_migrate_config_dumb_structure(tmp_path: Path) -> None:
    """Dumb migration lifts run.yaml into native_override and drops the legacy path."""
    run_path, lcs_path = _write_legacy_pair(tmp_path)
    out_path = tmp_path / "unified.yaml"
    migrate_config_dumb(run_path, lcs_path, str(out_path))

    migrated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    # unrelated top-level content preserved
    assert migrated["name"] == "LCS"
    assert migrated["service"] == {"host": "localhost", "port": 8080}
    # legacy path dropped; use_as_library_client preserved
    assert "library_client_config_path" not in migrated["llama_stack"]
    assert migrated["llama_stack"]["use_as_library_client"] is True
    # whole run.yaml lifted into native_override with an empty baseline
    assert migrated["llama_stack"]["config"]["baseline"] == "empty"
    assert migrated["llama_stack"]["config"]["native_override"] == _LEGACY_RUN_YAML


def test_migrate_then_synthesize_reproduces_run_yaml(tmp_path: Path) -> None:
    """Round-trip: migrate -> synthesize reproduces the original run.yaml (R4)."""
    run_path, lcs_path = _write_legacy_pair(tmp_path)
    out_path = tmp_path / "unified.yaml"
    migrate_config_dumb(run_path, lcs_path, str(out_path))

    migrated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    synthesized = synthesize_configuration(migrated)
    assert synthesized == _LEGACY_RUN_YAML


def test_migrate_config_dumb_writes_output_0600(tmp_path: Path) -> None:
    """The migrated file may carry lifted secrets, so it is written owner-only."""
    run_path, lcs_path = _write_legacy_pair(tmp_path)
    out_path = tmp_path / "unified.yaml"
    migrate_config_dumb(run_path, lcs_path, str(out_path))
    assert stat.S_IMODE(os.stat(out_path).st_mode) == 0o600


def test_migrate_config_dumb_rejects_non_mapping_inputs(tmp_path: Path) -> None:
    """An empty/comment-only input fails with a clear ValueError, not AttributeError."""
    run_path, lcs_path = _write_legacy_pair(tmp_path)
    out_path = str(tmp_path / "unified.yaml")

    empty_lcs = tmp_path / "empty-lcs.yaml"
    empty_lcs.write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="did not parse to a mapping"):
        migrate_config_dumb(run_path, str(empty_lcs), out_path)

    empty_run = tmp_path / "empty-run.yaml"
    empty_run.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="did not parse to a mapping"):
        migrate_config_dumb(str(empty_run), lcs_path, out_path)


# ---------------------------------------------------------------------------
# reference profiles (LCORE-2346)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]
REFERENCE_PROFILES = sorted((REPO_ROOT / "examples" / "profiles").glob("*.yaml"))


def test_reference_profiles_exist() -> None:
    """The reference profiles shipped in examples/profiles/ are present."""
    names = {p.name for p in REFERENCE_PROFILES}
    assert {"openai-remote.yaml", "inline-faiss.yaml"} <= names


@pytest.mark.parametrize("profile_path", REFERENCE_PROFILES, ids=lambda p: p.name)
def test_reference_profile_loads_via_synthesizer(profile_path: Path) -> None:
    """Every examples/profiles/*.yaml loads cleanly as a synthesis baseline."""
    lcs = {"llama_stack": {"config": {"profile": profile_path.name}}}
    result = synthesize_configuration(lcs, config_file_dir=str(profile_path.parent))
    # The profile drives the baseline: run.yaml-shaped keys survive synthesis.
    assert result["version"] == 2
    assert "inference" in result["apis"]
    assert result["providers"]["inference"], "profile must configure inference"
