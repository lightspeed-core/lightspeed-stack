"""Unit tests for unified-mode synthesizer and migration tool (LCORE-836)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from llama_stack_configuration import (
    PROVIDER_TYPE_MAP,
    apply_high_level_inference,
    deep_merge_list_replace,
    load_default_baseline,
    migrate_config_dumb,
    synthesize_configuration,
)

# =============================================================================
# deep_merge_list_replace
# =============================================================================


def test_deep_merge_scalar_replace() -> None:
    """Overlay scalar replaces base scalar."""
    result = deep_merge_list_replace({"a": 1}, {"a": 2})
    assert result == {"a": 2}


def test_deep_merge_adds_new_keys() -> None:
    """Overlay keys not in base are added."""
    result = deep_merge_list_replace({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_deep_merge_nested_map_merges() -> None:
    """Nested maps merge recursively."""
    base = {"a": {"x": 1, "y": 2}}
    overlay = {"a": {"y": 20, "z": 30}}
    result = deep_merge_list_replace(base, overlay)
    assert result == {"a": {"x": 1, "y": 20, "z": 30}}


def test_deep_merge_list_replaces() -> None:
    """Lists are replaced, not appended."""
    base = {"items": [1, 2, 3]}
    overlay = {"items": [9]}
    result = deep_merge_list_replace(base, overlay)
    assert result == {"items": [9]}


def test_deep_merge_does_not_mutate_inputs() -> None:
    """Neither base nor overlay are mutated."""
    base = {"a": {"x": 1}}
    overlay = {"a": {"x": 2}}
    result = deep_merge_list_replace(base, overlay)
    assert base == {"a": {"x": 1}}
    assert overlay == {"a": {"x": 2}}
    assert result == {"a": {"x": 2}}


def test_deep_merge_type_mismatch_replaces() -> None:
    """If overlay type != base type at same key, overlay wins."""
    # base is map, overlay is scalar
    result = deep_merge_list_replace({"a": {"x": 1}}, {"a": "replaced"})
    assert result == {"a": "replaced"}


# =============================================================================
# apply_high_level_inference
# =============================================================================


def test_apply_high_level_inference_single_provider() -> None:
    """Single provider with api_key_env and allowed_models."""
    ls_config: dict[str, Any] = {}
    inference = {
        "providers": [
            {
                "type": "openai",
                "api_key_env": "OPENAI_API_KEY",
                "allowed_models": ["gpt-4o-mini"],
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    assert ls_config["providers"]["inference"] == [
        {
            "provider_id": "openai",
            "provider_type": "remote::openai",
            "config": {
                "api_key": "${env.OPENAI_API_KEY}",
                "allowed_models": ["gpt-4o-mini"],
            },
        }
    ]


def test_apply_high_level_inference_replaces_existing() -> None:
    """Providers list is replaced entirely, not merged."""
    ls_config = {"providers": {"inference": [{"provider_id": "stale"}]}}
    apply_high_level_inference(
        ls_config, {"providers": [{"type": "sentence_transformers"}]}
    )
    assert ls_config["providers"]["inference"] == [
        {
            "provider_id": "sentence_transformers",
            "provider_type": "inline::sentence-transformers",
        }
    ]


def test_apply_high_level_inference_extra_merged() -> None:
    """`extra` dict fields merge into emitted config."""
    ls_config: dict[str, Any] = {}
    inference = {
        "providers": [
            {
                "type": "vertexai",
                "extra": {"project_id": "my-project", "location": "us-central1"},
            }
        ]
    }
    apply_high_level_inference(ls_config, inference)
    assert ls_config["providers"]["inference"][0]["config"] == {
        "project_id": "my-project",
        "location": "us-central1",
    }


def test_provider_type_map_covers_all_literals() -> None:
    """Every Literal value declared on UnifiedInferenceProvider.type has a mapping."""
    # pylint: disable=import-outside-toplevel
    from models.config import UnifiedInferenceProvider

    literal_values = (
        UnifiedInferenceProvider.model_fields[  # pylint: disable=unsubscriptable-object
            "type"
        ].annotation.__args__
    )
    for value in literal_values:
        assert value in PROVIDER_TYPE_MAP


# =============================================================================
# synthesize_configuration
# =============================================================================


MINIMAL_BASELINE: dict[str, Any] = {
    "version": 2,
    "apis": ["inference"],
    "providers": {
        "inference": [
            {"provider_id": "stock", "provider_type": "remote::stock", "config": {}}
        ]
    },
    "safety": {"default_shield_id": "llama-guard"},
}


def test_synthesize_errors_without_config() -> None:
    """Without llama_stack.config present, synthesize raises ValueError."""
    with pytest.raises(ValueError, match="llama_stack.config"):
        synthesize_configuration({"llama_stack": {}})


def test_synthesize_uses_default_baseline_when_no_profile() -> None:
    """With neither profile nor native_override, result is the baseline (through enrichment)."""
    lcs_config: dict[str, Any] = {"llama_stack": {"config": {}}}
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    # Baseline preserved (enrichment is a no-op without byok_rag/rag/okp)
    assert result["safety"] == {"default_shield_id": "llama-guard"}
    assert result["providers"]["inference"] == [
        {"provider_id": "stock", "provider_type": "remote::stock", "config": {}}
    ]


def test_synthesize_loads_profile_from_path(tmp_path: Path) -> None:
    """Profile path is loaded as the baseline."""
    profile_data = {
        "version": 2,
        "apis": ["inference"],
        "providers": {"inference": [{"provider_id": "profile_p"}]},
    }
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml.dump(profile_data))

    lcs_config: dict[str, Any] = {
        "llama_stack": {"config": {"profile": str(profile_path)}}
    }
    result = synthesize_configuration(lcs_config)
    assert result["providers"]["inference"] == [{"provider_id": "profile_p"}]


def test_synthesize_profile_relative_path(tmp_path: Path) -> None:
    """Relative profile path resolves against config_file_dir."""
    profile_data = {"version": 2}
    (tmp_path / "p.yaml").write_text(yaml.dump(profile_data))
    lcs_config: dict[str, Any] = {"llama_stack": {"config": {"profile": "p.yaml"}}}
    result = synthesize_configuration(lcs_config, config_file_dir=tmp_path)
    assert result == {"version": 2}


def test_synthesize_applies_high_level_inference() -> None:
    """High-level inference section expands into native providers list."""
    lcs_config: dict[str, Any] = {
        "llama_stack": {
            "config": {
                "inference": {
                    "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
                }
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    assert result["providers"]["inference"] == [
        {
            "provider_id": "openai",
            "provider_type": "remote::openai",
            "config": {"api_key": "${env.OPENAI_API_KEY}"},
        }
    ]


def test_synthesize_native_override_deep_merges() -> None:
    """native_override deep-merges on top (scalar path)."""
    lcs_config: dict[str, Any] = {
        "llama_stack": {
            "config": {
                "native_override": {
                    "safety": {"default_shield_id": "overridden"},
                }
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    assert result["safety"]["default_shield_id"] == "overridden"


def test_synthesize_native_override_list_replaces() -> None:
    """native_override replaces lists, not appends."""
    lcs_config: dict[str, Any] = {
        "llama_stack": {
            "config": {
                "native_override": {
                    "providers": {
                        "inference": [{"provider_id": "override-only"}],
                    }
                }
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    assert result["providers"]["inference"] == [{"provider_id": "override-only"}]


def test_synthesize_precedence_override_beats_high_level() -> None:
    """When high-level and native_override both touch the same path, override wins."""
    lcs_config: dict[str, Any] = {
        "llama_stack": {
            "config": {
                "inference": {"providers": [{"type": "openai"}]},
                "native_override": {
                    "providers": {
                        "inference": [{"provider_id": "override-wins"}],
                    }
                },
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    assert result["providers"]["inference"] == [{"provider_id": "override-wins"}]


def test_synthesize_preserves_env_var_refs_verbatim() -> None:
    """Secrets stay as ${env.FOO} references; never resolved into the output."""
    lcs_config: dict[str, Any] = {
        "llama_stack": {
            "config": {
                "inference": {
                    "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
                }
            }
        }
    }
    result = synthesize_configuration(lcs_config, default_baseline=MINIMAL_BASELINE)
    api_key_value = result["providers"]["inference"][0]["config"]["api_key"]
    assert api_key_value == "${env.OPENAI_API_KEY}"


# =============================================================================
# Built-in default baseline loader
# =============================================================================


def test_load_default_baseline_returns_dict() -> None:
    """The shipped default baseline loads as a dict with expected keys."""
    baseline = load_default_baseline()
    assert isinstance(baseline, dict)
    assert baseline.get("version") == 2
    assert "providers" in baseline


# =============================================================================
# migrate_config_dumb
# =============================================================================


def test_migrate_dumb_lossless_roundtrip(tmp_path: Path) -> None:
    """Dumb migration places full run.yaml under config.native_override."""
    run_yaml_content = {
        "version": 2,
        "apis": ["inference"],
        "providers": {"inference": [{"provider_id": "opa"}]},
    }
    lcs_yaml_content = {
        "name": "LCS",
        "llama_stack": {
            "use_as_library_client": True,
            "library_client_config_path": str(tmp_path / "run.yaml"),
        },
    }

    run_yaml_path = tmp_path / "run.yaml"
    run_yaml_path.write_text(yaml.dump(run_yaml_content))
    lcs_yaml_path = tmp_path / "lightspeed-stack.yaml"
    lcs_yaml_path.write_text(yaml.dump(lcs_yaml_content))
    output_path = tmp_path / "unified.yaml"

    migrate_config_dumb(str(run_yaml_path), str(lcs_yaml_path), str(output_path))

    result = yaml.safe_load(output_path.read_text())

    # Legacy path is gone
    assert "library_client_config_path" not in result["llama_stack"]
    # Unified config has full run.yaml under native_override
    assert result["llama_stack"]["config"]["native_override"] == run_yaml_content
    # Other fields preserved
    assert result["llama_stack"]["use_as_library_client"] is True
    assert result["name"] == "LCS"


def test_migrate_then_synthesize_reproduces_run_yaml(tmp_path: Path) -> None:
    """End-to-end round trip: run.yaml → migrate → synthesize → original content."""
    run_yaml_content = {
        "version": 2,
        "apis": ["inference", "vector_io"],
        "providers": {
            "inference": [{"provider_id": "rt", "provider_type": "remote::rt"}]
        },
        "safety": {"default_shield_id": "guard"},
    }
    lcs_yaml_content = {
        "name": "LCS",
        "llama_stack": {
            "use_as_library_client": True,
            "library_client_config_path": str(tmp_path / "run.yaml"),
        },
    }
    run_yaml_path = tmp_path / "run.yaml"
    run_yaml_path.write_text(yaml.dump(run_yaml_content))
    lcs_yaml_path = tmp_path / "lightspeed-stack.yaml"
    lcs_yaml_path.write_text(yaml.dump(lcs_yaml_content))
    output_path = tmp_path / "unified.yaml"
    migrate_config_dumb(str(run_yaml_path), str(lcs_yaml_path), str(output_path))

    unified = yaml.safe_load(output_path.read_text())
    synthesized = synthesize_configuration(unified)

    # Synthesized == original run.yaml (lossless round trip in dumb mode)
    assert synthesized == run_yaml_content
