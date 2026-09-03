"""Unit tests for unified-mode OGX configuration synthesis (LCORE-2336).

Covers the synthesizer pipeline and its helpers in
``src/ogx_configuration.py``: baseline loading, deep-merge semantics,
high-level inference expansion, the full synthesis pipeline, and the
write-to-file step (persistent path, mode 0600).
"""

# pylint: disable=too-many-lines

import logging
import os
import stat
import sys
from pathlib import Path
from typing import Any, Optional, get_args

import pytest
import yaml
from ogx.core.stack import replace_env_vars

from models.config import UnifiedInferenceProvider
from ogx_configuration import (
    CONDITIONAL_OPENAI_PROVIDER_ID,
    PROVIDER_TYPE_MAP,
    apply_high_level_inference,
    deep_merge_list_replace,
    ensure_mcp_tool_runtime,
    has_synthesis_input,
    load_default_baseline,
    main,
    migrate_config_dumb,
    synthesize_configuration,
    synthesize_to_file,
)

OPENAI_CONDITIONAL_PROVIDER_ID = CONDITIONAL_OPENAI_PROVIDER_ID
OPENAI_CONDITIONAL_API_KEY = "${env.OPENAI_API_KEY:=}"

# ---------------------------------------------------------------------------
# ensure_mcp_tool_runtime
# ---------------------------------------------------------------------------


def _tool_runtime_ids(ogx_config: dict[str, Any]) -> list[Optional[str]]:
    """Return provider_id values from providers.tool_runtime."""
    providers = ogx_config.get("providers") or {}
    return [
        entry.get("provider_id")
        for entry in providers.get("tool_runtime") or []
        if isinstance(entry, dict)
    ]


def _inference_entries(ogx_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return inference provider dicts from a synthesized or baseline config."""
    providers = ogx_config.get("providers") or {}
    return [
        entry for entry in providers.get("inference") or [] if isinstance(entry, dict)
    ]


def _openai_inference_entries(ogx_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return remote::openai inference rows, including the conditional-id form."""
    return [
        entry
        for entry in _inference_entries(ogx_config)
        if entry.get("provider_type") == "remote::openai"
        or entry.get("provider_id") in ("openai", OPENAI_CONDITIONAL_PROVIDER_ID)
    ]


def test_ensure_mcp_tool_runtime_appends_and_preserves_rag() -> None:
    """MCP is appended; existing rag-runtime is untouched."""
    ogx_config: dict[str, Any] = {
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
    ensure_mcp_tool_runtime(ogx_config)
    assert _tool_runtime_ids(ogx_config) == [
        "rag-runtime",
        "model-context-protocol",
    ]

    found = False
    found_entry = {}
    for entry in ogx_config["providers"]["tool_runtime"]:
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
    ogx_config: dict[str, Any] = {
        "apis": ["tool_runtime"],
        "providers": {"tool_runtime": [existing]},
    }
    ensure_mcp_tool_runtime(ogx_config)
    assert ogx_config["providers"]["tool_runtime"] == [existing]


def test_ensure_mcp_tool_runtime_adds_api_when_missing() -> None:
    """Thin baselines get tool_runtime in apis and the MCP provider."""
    ogx_config: dict[str, Any] = {}
    ensure_mcp_tool_runtime(ogx_config)
    assert "tool_runtime" in ogx_config["apis"]
    assert _tool_runtime_ids(ogx_config) == ["model-context-protocol"]


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
    """Default stack ships MCP beside file-search."""
    baseline = load_default_baseline()
    ids = _tool_runtime_ids(baseline)
    assert "file-search" in ids
    assert "model-context-protocol" in ids


def test_load_default_baseline_includes_file_processors() -> None:
    """Default stack ships file_processors so vector-store file attach works."""
    baseline = load_default_baseline()
    assert "file_processors" in baseline["apis"]
    processors = baseline["providers"]["file_processors"]
    assert any(
        p.get("provider_id") == "pypdf" and p.get("provider_type") == "inline::pypdf"
        for p in processors
    )


def test_load_default_baseline_openai_is_conditional_on_api_key() -> None:
    """OpenAI is present only when OPENAI_API_KEY is set (LCORE-3607)."""
    baseline = load_default_baseline()
    openai_entries = _openai_inference_entries(baseline)
    assert openai_entries == [
        {
            "provider_id": OPENAI_CONDITIONAL_PROVIDER_ID,
            "provider_type": "remote::openai",
            "config": {
                "api_key": OPENAI_CONDITIONAL_API_KEY,
                "allowed_models": ["${env.E2E_OPENAI_MODEL:=gpt-4o-mini}"],
            },
        }
    ]
    ids = [entry["provider_id"] for entry in _inference_entries(baseline)]
    assert "sentence-transformers" in ids


@pytest.mark.parametrize("openai_api_key", [None, ""])
def test_default_baseline_resolves_when_openai_api_key_missing(
    monkeypatch: pytest.MonkeyPatch, openai_api_key: Optional[str]
) -> None:
    """Unset or empty OPENAI_API_KEY disables openai without EnvVarError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if openai_api_key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", openai_api_key)

    resolved = replace_env_vars(load_default_baseline())
    openai_entries = _openai_inference_entries(resolved)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] is None
    ids = [entry["provider_id"] for entry in _inference_entries(resolved)]
    assert "sentence-transformers" in ids


def test_default_baseline_resolves_when_openai_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set OPENAI_API_KEY resolves to the same openai provider as before."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    resolved = replace_env_vars(load_default_baseline())
    openai_entries = _openai_inference_entries(resolved)
    assert len(openai_entries) == 1
    openai = openai_entries[0]
    assert openai["provider_id"] == "openai"
    assert openai["config"]["api_key"] == "sk-test-key"


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
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
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
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "openai"
    assert entry["provider_type"] == "remote::openai"
    assert entry["config"]["api_key"] == "${env.OPENAI_API_KEY}"
    assert entry["config"]["allowed_models"] == ["gpt-4o-mini"]


def test_apply_high_level_inference_hyphenates_provider_id() -> None:
    """sentence_transformers emits the hyphenated id the ecosystem expects."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {"providers": [{"type": "sentence_transformers"}]}
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "sentence-transformers"
    assert entry["provider_type"] == "inline::sentence-transformers"
    # no api_key / allowed_models -> no config block emitted
    assert "config" not in entry


def test_apply_high_level_inference_replaces_existing_provider_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A high-level provider replaces a baseline entry with the same id."""
    ogx_config: dict[str, Any] = {
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
    with caplog.at_level("INFO", logger="lightspeed_stack.ogx_configuration"):
        apply_high_level_inference(ogx_config, inference)
    ids = [p["provider_id"] for p in ogx_config["providers"]["inference"]]
    assert ids == ["openai", "other"]  # replaced in place, not duplicated
    openai = ogx_config["providers"]["inference"][0]
    assert openai["config"]["api_key"] == "${env.NEW_KEY}"
    assert "provider_id='openai'" in caplog.text


def test_apply_high_level_inference_replaces_conditional_provider_id() -> None:
    """The baseline ${env.OPENAI_API_KEY:+openai} row matches id openai."""
    ogx_config: dict[str, Any] = {
        "providers": {
            "inference": [
                {
                    "provider_id": OPENAI_CONDITIONAL_PROVIDER_ID,
                    "provider_type": "remote::openai",
                    "config": {"api_key": OPENAI_CONDITIONAL_API_KEY},
                },
                {
                    "provider_id": "sentence-transformers",
                    "provider_type": "inline::sentence-transformers",
                },
            ]
        }
    }
    inference = {"providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]}
    apply_high_level_inference(ogx_config, inference)
    openai_entries = _openai_inference_entries(ogx_config)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] == "openai"
    assert openai_entries[0]["config"]["api_key"] == "${env.OPENAI_API_KEY}"
    ids = [entry["provider_id"] for entry in _inference_entries(ogx_config)]
    assert ids == ["openai", "sentence-transformers"]


def test_apply_high_level_inference_uses_explicit_id() -> None:
    """An explicit id is emitted as provider_id instead of the type-derived id."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "id": "vllm-prod",
                "api_key_env": "VLLM_API_KEY",
            }
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm-prod"
    assert entry["provider_type"] == "remote::vllm"


def test_apply_high_level_inference_same_type_distinct_ids() -> None:
    """Two providers of the same type with distinct ids both appear."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
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
    apply_high_level_inference(ogx_config, inference)
    by_id = {e["provider_id"]: e for e in ogx_config["providers"]["inference"]}
    assert set(by_id) == {"vllm-prod", "vllm-staging"}
    assert all(e["provider_type"] == "remote::vllm" for e in by_id.values())
    assert by_id["vllm-prod"]["config"]["url"] == "http://prod:8000"
    assert by_id["vllm-staging"]["config"]["url"] == "http://staging:8000"


def test_apply_high_level_inference_duplicate_id_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Duplicate id keeps the last entry and logs an info message."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
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
    with caplog.at_level("INFO", logger="lightspeed_stack.ogx_configuration"):
        apply_high_level_inference(ogx_config, inference)
    entries = ogx_config["providers"]["inference"]
    assert len(entries) == 1
    assert entries[0]["provider_id"] == "vllm-shared"
    assert entries[0]["config"]["api_token"] == "${env.SECOND_KEY}"
    assert "provider_id='vllm-shared'" in caplog.text


def test_apply_high_level_inference_merges_extra() -> None:
    """The extra mapping is merged verbatim into the provider config block."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "vllm_rhaiis", "extra": {"url": "http://x", "tls_verify": False}}
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm-rhaiis"
    assert entry["provider_type"] == "remote::vllm"
    assert entry["config"] == {"url": "http://x", "tls_verify": False}


def test_apply_high_level_inference_emits_api_token_for_vllm() -> None:
    """vLLM providers emit api_token from api_key_env, not api_key."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "vllm", "api_key_env": "VLLM_API_KEY"},
            {"type": "vllm_rhaiis", "api_key_env": "VLLM_API_KEY"},
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    vllm = ogx_config["providers"]["inference"][0]
    vllm_rhaiis = ogx_config["providers"]["inference"][1]
    assert vllm["provider_id"] == "vllm"
    assert vllm["provider_type"] == "remote::vllm"
    assert vllm["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert "api_key" not in vllm["config"]
    assert vllm_rhaiis["provider_id"] == "vllm-rhaiis"
    assert vllm_rhaiis["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert "api_key" not in vllm_rhaiis["config"]


def test_apply_high_level_inference_maps_ollama() -> None:
    """ollama maps to remote::ollama with extra config merged."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {"type": "ollama", "extra": {"base_url": "http://localhost:11434"}}
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "ollama"
    assert entry["provider_type"] == "remote::ollama"
    assert entry["config"]["base_url"] == "http://localhost:11434"


def test_apply_high_level_inference_maps_vllm() -> None:
    """vllm maps to remote::vllm with extra config merged."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "api_key_env": "VLLM_API_KEY",
                "extra": {"base_url": "${env.VLLM_URL:=}"},
            }
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["provider_id"] == "vllm"
    assert entry["provider_type"] == "remote::vllm"
    assert entry["config"]["api_token"] == "${env.VLLM_API_KEY}"
    assert entry["config"]["base_url"] == "${env.VLLM_URL:=}"


def test_apply_high_level_inference_extra_cannot_override_api_key_env() -> None:
    """api_key_env always wins over a conflicting key in extra."""
    ogx_config: dict[str, Any] = {"providers": {"inference": []}}
    inference = {
        "providers": [
            {
                "type": "vllm",
                "api_key_env": "VLLM_API_KEY",
                "extra": {"api_token": "hardcoded"},
            }
        ]
    }
    apply_high_level_inference(ogx_config, inference)
    entry = ogx_config["providers"]["inference"][0]
    assert entry["config"]["api_token"] == "${env.VLLM_API_KEY}"


def test_unified_inference_provider_accepts_ollama_and_vllm() -> None:
    """Pydantic model accepts the new ollama and vllm Literal values."""
    ollama = UnifiedInferenceProvider(type="ollama")
    assert ollama.type == "ollama"
    vllm = UnifiedInferenceProvider(type="vllm")
    assert vllm.type == "vllm"


def test_apply_high_level_inference_empty_is_noop() -> None:
    """No providers -> the inference list is left as-is."""
    ogx_config: dict[str, Any] = {"providers": {"inference": [{"provider_id": "x"}]}}
    apply_high_level_inference(ogx_config, {"providers": []})
    assert ogx_config["providers"]["inference"] == [{"provider_id": "x"}]


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
        "ogx": {"config": {"baseline": "default"}},
        "inference": {"providers": []},
    }
    result = synthesize_configuration(lcs_config, default_baseline=default_baseline)
    assert "model-context-protocol" in _tool_runtime_ids(result)
    assert "rag-runtime" in _tool_runtime_ids(result)


def test_synthesize_empty_baseline_skips_mcp_ensure() -> None:
    """baseline: empty must not assume MCP."""
    lcs_config = {
        "ogx": {
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
        "ogx": {
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
        "ogx": {
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
        "ogx": {"config": {"profile": str(profile)}},
    }
    result = synthesize_configuration(lcs_config)
    assert "tool_runtime" in result["apis"]
    assert "model-context-protocol" in _tool_runtime_ids(result)


def test_synthesize_empty_profile_still_ensures_mcp(tmp_path: Path) -> None:
    """A profile that loads {} still gets ensure; only baseline: empty skips it."""
    profile = tmp_path / "empty-profile.yaml"
    profile.write_text("{}\n", encoding="utf-8")
    lcs_config = {
        "ogx": {"config": {"profile": str(profile)}},
    }
    result = synthesize_configuration(lcs_config)
    assert "tool_runtime" in result["apis"]
    assert "model-context-protocol" in _tool_runtime_ids(result)


def test_synthesize_from_empty_baseline_only_native_override() -> None:
    """baseline: empty starts from {} so native_override is the whole output."""
    lcs = {
        "ogx": {
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
        "ogx": {
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
    openai_entries = _openai_inference_entries(result)
    assert len(openai_entries) == 1
    openai = openai_entries[0]
    assert openai["provider_id"] == "openai"
    assert openai["config"]["api_key"] == "${env.OPENAI_API_KEY}"
    # native_override deep-merged last
    assert result["safety"]["default_shield_id"] == "custom"


def test_synthesize_vllm_appends_and_keeps_conditional_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-level vLLM appends; baseline openai stays conditional and disables."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VLLM_API_KEY", "vllm-test-key")
    lcs = {
        "ogx": {"config": {"baseline": "default"}},
        "inference": {
            "providers": [
                {
                    "type": "vllm",
                    "api_key_env": "VLLM_API_KEY",
                    "extra": {"url": "http://vllm:8000"},
                }
            ]
        },
    }
    result = synthesize_configuration(lcs)
    openai_entries = _openai_inference_entries(result)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] == OPENAI_CONDITIONAL_PROVIDER_ID
    vllm = next(
        entry for entry in _inference_entries(result) if entry["provider_id"] == "vllm"
    )
    assert vllm["provider_type"] == "remote::vllm"

    resolved = replace_env_vars(result)
    resolved_openai = _openai_inference_entries(resolved)
    assert len(resolved_openai) == 1
    assert resolved_openai[0]["provider_id"] is None
    assert any(entry["provider_id"] == "vllm" for entry in _inference_entries(resolved))


def _byo_llm_deprecation_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return WARN records that name the byo-llm baseline replacement."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "byo-llm" in record.getMessage()
    ]


@pytest.mark.parametrize(
    "lcs",
    [
        {"ogx": {"config": {"baseline": "default"}}},
        {"ogx": {"config": {}}},
        {},
    ],
)
def test_synthesize_default_path_keeps_conditional_openai(
    lcs: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """default or omitted baseline keeps the OpenAI row and warns naming byo-llm."""
    with caplog.at_level("WARNING", logger="lightspeed_stack.ogx_configuration"):
        result = synthesize_configuration(lcs)
    warnings = _byo_llm_deprecation_warnings(caplog)
    assert len(warnings) == 1
    assert "removed in release 0.8" in warnings[0]
    openai_entries = _openai_inference_entries(result)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] == OPENAI_CONDITIONAL_PROVIDER_ID
    ids = [entry["provider_id"] for entry in _inference_entries(result)]
    assert "sentence-transformers" in ids


def test_synthesize_byo_llm_strips_openai(caplog: pytest.LogCaptureFixture) -> None:
    """byo-llm drops the OpenAI row, keeps the embedder, and does not warn."""
    lcs = {"ogx": {"config": {"baseline": "byo-llm"}}}
    with caplog.at_level("WARNING", logger="lightspeed_stack.ogx_configuration"):
        result = synthesize_configuration(lcs)
    assert _byo_llm_deprecation_warnings(caplog) == []
    assert _openai_inference_entries(result) == []
    ids = [entry["provider_id"] for entry in _inference_entries(result)]
    assert ids == ["sentence-transformers"]
    assert "model-context-protocol" in _tool_runtime_ids(result)


def test_synthesize_byo_llm_with_vllm_appends_without_openai() -> None:
    """byo-llm + high-level vLLM appends vLLM and does not restore OpenAI."""
    lcs = {
        "ogx": {"config": {"baseline": "byo-llm"}},
        "inference": {
            "providers": [
                {
                    "type": "vllm",
                    "api_key_env": "VLLM_API_KEY",
                    "extra": {"url": "http://vllm:8000"},
                }
            ]
        },
    }
    result = synthesize_configuration(lcs)
    assert _openai_inference_entries(result) == []
    vllm = next(
        entry for entry in _inference_entries(result) if entry["provider_id"] == "vllm"
    )
    assert vllm["provider_type"] == "remote::vllm"
    assert "sentence-transformers" in [
        entry["provider_id"] for entry in _inference_entries(result)
    ]


def test_synthesize_byo_llm_with_openai_appends_one_row() -> None:
    """byo-llm + high-level openai appends a single openai row."""
    lcs = {
        "ogx": {"config": {"baseline": "byo-llm"}},
        "inference": {
            "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
        },
    }
    result = synthesize_configuration(lcs)
    openai_entries = _openai_inference_entries(result)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] == "openai"
    assert openai_entries[0]["config"]["api_key"] == "${env.OPENAI_API_KEY}"


def test_synthesize_empty_baseline_does_not_strip_openai(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """baseline: empty is unchanged: no OpenAI strip and no deprecation WARN."""
    lcs = {
        "ogx": {
            "config": {
                "baseline": "empty",
                "native_override": {"version": 2, "apis": ["inference"]},
            }
        }
    }
    with caplog.at_level("WARNING", logger="lightspeed_stack.ogx_configuration"):
        result = synthesize_configuration(lcs)
    assert _byo_llm_deprecation_warnings(caplog) == []
    assert result == {"version": 2, "apis": ["inference"]}


def test_synthesize_profile_ignores_byo_llm(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """profile: wins over baseline: byo-llm; no OpenAI strip and no WARN."""
    profile = {
        "version": 2,
        "apis": ["inference"],
        "providers": {
            "inference": [
                {
                    "provider_id": "openai",
                    "provider_type": "remote::openai",
                    "config": {"api_key": "${env.OPENAI_API_KEY}"},
                }
            ]
        },
        "marker": "from-profile",
    }
    (tmp_path / "my-profile.yaml").write_text(yaml.dump(profile), encoding="utf-8")
    lcs = {
        "ogx": {
            "config": {
                "profile": "my-profile.yaml",
                "baseline": "byo-llm",
            }
        }
    }
    with caplog.at_level("WARNING", logger="lightspeed_stack.ogx_configuration"):
        result = synthesize_configuration(lcs, config_file_dir=str(tmp_path))
    assert _byo_llm_deprecation_warnings(caplog) == []
    assert result["marker"] == "from-profile"
    openai_entries = _openai_inference_entries(result)
    assert len(openai_entries) == 1
    assert openai_entries[0]["provider_id"] == "openai"


def test_synthesize_loads_profile_relative_to_config_dir(tmp_path: Path) -> None:
    """A relative profile: resolves against the config file's directory (R8)."""
    profile = {"version": 2, "apis": ["inference"], "marker": "from-profile"}
    (tmp_path / "my-profile.yaml").write_text(yaml.dump(profile), encoding="utf-8")
    lcs = {"ogx": {"config": {"profile": "my-profile.yaml"}}}
    result = synthesize_configuration(lcs, config_file_dir=str(tmp_path))
    assert result["marker"] == "from-profile"


def test_synthesize_uses_provided_default_baseline() -> None:
    """An explicit default_baseline arg is used without touching the shipped one."""
    lcs: dict[str, Any] = {"ogx": {"config": {"baseline": "default"}}}
    result = synthesize_configuration(lcs, default_baseline={"marker": "injected"})
    assert result["marker"] == "injected"


def test_synthesize_enriches_byok_rag_like_legacy() -> None:
    """BYOK RAG enrichment runs during synthesis for legacy parity (R7)."""
    lcs = {
        "ogx": {"config": {"baseline": "empty"}},
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "kb1",
                        "vector_db_id": "kb1",
                        "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
                        "embedding_dimension": 768,
                    }
                ],
            },
        },
    }
    result = synthesize_configuration(lcs)
    # enrichment created the storage backends + vector_io provider section
    assert "storage" in result
    assert "vector_io" in result.get("providers", {})


def test_synthesize_includes_vector_store() -> None:
    """vector_store enrichment runs during unified synthesis."""
    lcs_config = {
        "ogx": {
            "use_as_library_client": True,
            "config": {"baseline": "default"},
        },
        "vector_store": {
            "default_provider": "notebooks",
            "providers": [
                {
                    "id": "notebooks",
                    "type": "faiss",
                    "embedding_model": "/rag-content/embeddings_model",
                    "embedding_dimension": 768,
                    "config": {"path": "/tmp/notebooks.db"},
                }
            ],
        },
    }
    result = synthesize_configuration(lcs_config)
    ids = {p["provider_id"] for p in result["providers"]["vector_io"]}
    assert "notebooks" in ids
    assert result["vector_stores"]["default_provider_id"] == "notebooks"
    assert result["vector_stores"]["default_embedding_model"]["model_id"] == (
        "vsprov_notebooks_embedding"
    )


# ---------------------------------------------------------------------------
# synthesize_to_file
# ---------------------------------------------------------------------------


def test_synthesize_to_file_writes_mode_0600(tmp_path: Path) -> None:
    """The synthesized file is written owner-only (R10) and round-trips."""
    out = tmp_path / "nested" / "run.yaml"
    lcs = {"ogx": {"config": {"baseline": "empty", "native_override": {"v": 2}}}}
    synthesize_to_file(lcs, str(out), str(tmp_path))
    assert out.exists()
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {"v": 2}


def test_synthesize_to_file_tightens_perms_on_overwrite(tmp_path: Path) -> None:
    """A pre-existing world-readable file is re-chmodded to 0600 on each boot."""
    out = tmp_path / "run.yaml"
    out.write_text("stale", encoding="utf-8")
    os.chmod(out, 0o644)
    lcs = {"ogx": {"config": {"baseline": "empty", "native_override": {"v": 3}}}}
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
        "ogx": {
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
    assert "library_client_config_path" not in migrated["ogx"]
    assert migrated["ogx"]["use_as_library_client"] is True
    # whole run.yaml lifted into native_override with an empty baseline
    assert migrated["ogx"]["config"]["baseline"] == "empty"
    assert migrated["ogx"]["config"]["native_override"] == _LEGACY_RUN_YAML


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
    lcs = {"ogx": {"config": {"profile": profile_path.name}}}
    result = synthesize_configuration(lcs, config_file_dir=str(profile_path.parent))
    # The profile drives the baseline: run.yaml-shaped keys survive synthesis.
    assert result["version"] == 2
    assert "inference" in result["apis"]
    assert result["providers"]["inference"], "profile must configure inference"


# ---------------------------------------------------------------------------
# CLI auto-detection (LCORE-2338): main() dispatches unified vs legacy
# ---------------------------------------------------------------------------


def test_has_synthesis_input_detection() -> None:
    """The raw-dict detection mirrors the root-model synthesis-input check."""
    assert has_synthesis_input({"ogx": {"config": {"baseline": "default"}}})
    assert has_synthesis_input({"inference": {"providers": [{"type": "openai"}]}})
    assert has_synthesis_input({"vector_store": {"providers": [{"id": "nb"}]}})
    assert not has_synthesis_input({})
    assert not has_synthesis_input({"ogx": {"library_client_config_path": "run.yaml"}})
    # empty provider lists and null sections are not synthesis inputs
    assert not has_synthesis_input({"inference": {"providers": []}})
    assert not has_synthesis_input({"inference": None, "ogx": None})


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    """Invoke the module CLI with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["ogx_configuration.py", *argv])
    main()


def test_main_unified_config_synthesizes_without_input_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A unified config is synthesized; the legacy --input file is ignored.

    This is the server-mode contract (spec "Trigger mechanism"): the container
    entrypoint always passes -i, but in unified mode no run.yaml mount needs
    to exist.
    """
    lcs = {
        "ogx": {
            "config": {
                "baseline": "empty",
                "native_override": {"version": 2, "marker": "synthesized"},
            }
        }
    }
    cfg_path = tmp_path / "lightspeed-stack.yaml"
    cfg_path.write_text(yaml.dump(lcs), encoding="utf-8")
    out_path = tmp_path / "generated-run.yaml"

    _run_main(
        monkeypatch,
        [
            "-c",
            str(cfg_path),
            "-i",
            str(tmp_path / "does-not-exist.yaml"),
            "-o",
            str(out_path),
        ],
    )

    assert yaml.safe_load(out_path.read_text(encoding="utf-8")) == {
        "version": 2,
        "marker": "synthesized",
    }
    # synthesized output carries the 0600 secret-safety contract (R10)
    assert stat.S_IMODE(os.stat(out_path).st_mode) == 0o600


def test_main_unified_config_resolves_relative_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative profile: in the config resolves against the config's dir (R8)."""
    profile = {"version": 2, "apis": ["inference"], "marker": "from-profile"}
    (tmp_path / "my-profile.yaml").write_text(yaml.dump(profile), encoding="utf-8")
    lcs = {"ogx": {"config": {"profile": "my-profile.yaml"}}}
    cfg_path = tmp_path / "lightspeed-stack.yaml"
    cfg_path.write_text(yaml.dump(lcs), encoding="utf-8")
    out_path = tmp_path / "generated-run.yaml"

    _run_main(monkeypatch, ["-c", str(cfg_path), "-o", str(out_path)])

    assert yaml.safe_load(out_path.read_text(encoding="utf-8"))["marker"] == (
        "from-profile"
    )


def test_main_legacy_config_enriches_input_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy config (no synthesis input) enriches the --input run.yaml."""
    run_yaml = {"version": 2, "apis": ["inference"]}
    run_path = tmp_path / "run.yaml"
    run_path.write_text(yaml.dump(run_yaml), encoding="utf-8")
    lcs = {
        "ogx": {"library_client_config_path": str(run_path)},
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "kb1",
                        "vector_db_id": "kb1",
                        "db_path": "/var/lib/kb1/faiss.db",
                        "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
                        "embedding_dimension": 768,
                    }
                ]
            }
        },
    }
    cfg_path = tmp_path / "lightspeed-stack.yaml"
    cfg_path.write_text(yaml.dump(lcs), encoding="utf-8")
    out_path = tmp_path / "enriched-run.yaml"

    _run_main(
        monkeypatch,
        ["-c", str(cfg_path), "-i", str(run_path), "-o", str(out_path)],
    )

    enriched = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    # original content survives and BYOK enrichment was applied to the input
    assert enriched["version"] == 2
    vector_io_ids = {p["provider_id"] for p in enriched["providers"]["vector_io"]}
    assert "byok_kb1" in vector_io_ids
