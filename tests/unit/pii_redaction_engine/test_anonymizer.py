"""Model-free unit tests for the redaction engine.

These cover configuration and the startup guard without loading a spaCy model
(which is not installed in the unit-test environment). End-to-end anonymization
behavior is validated where the model is available.
"""

# pylint: disable=protected-access

import pytest
from presidio_analyzer import RecognizerResult

from pii_redaction_engine.anonymizer import (
    DEFAULT_ENTITIES,
    PIIAnonymizer,
    RedactionConfig,
)


def _allow_checker(allow_list: list[str] | None, match: str = "exact") -> PIIAnonymizer:
    """Build a PIIAnonymizer with only the allow-list attributes set (no model)."""
    obj = PIIAnonymizer.__new__(PIIAnonymizer)
    obj.allow_list = allow_list
    obj.allow_list_match = match
    return obj


def test_default_config_entities() -> None:
    """The default config enables the standard entities; org and URL are off."""
    config = RedactionConfig()
    assert config.entities == set(DEFAULT_ENTITIES)
    assert "ORGANIZATION" not in config.entities
    assert "URL" not in config.entities
    assert config.allow_list is None
    assert config.deny_list is None
    assert config.case_normalization is True


def test_default_config_entities_are_independent_instances() -> None:
    """Each RedactionConfig gets its own entities set (no shared mutable default)."""
    first = RedactionConfig()
    first.entities.add("ORGANIZATION")
    assert "ORGANIZATION" not in RedactionConfig().entities


def test_unknown_spacy_model_rejected() -> None:
    """A model that is not installed fails fast rather than being downloaded."""
    with pytest.raises(ValueError, match="not installed"):
        PIIAnonymizer._require_installed("en_core_web_does_not_exist")


def test_normalize_case_title_cases_uppercase_runs() -> None:
    """An ALL-CAPS run is title-cased while the rest of the text is left alone."""
    assert PIIAnonymizer._normalize_case("go to KATRINEHOLM now") == (
        "go to Katrineholm now"
    )


def test_normalize_case_preserves_offsets() -> None:
    """Recasing keeps length, so spans found in the copy map onto the original."""
    original = "go to KATRINEHOLM now"
    normalized = PIIAnonymizer._normalize_case(original)
    assert len(normalized) == len(original)
    assert normalized[6:17] == "Katrineholm"


def test_normalize_case_skips_length_changing_runs() -> None:
    """A run whose title-casing changes length is left as-is (offsets would shift)."""
    # "İ".title() expands (adds a combining mark), so the guard skips the run.
    original = "İİİ road"
    assert PIIAnonymizer._normalize_case(original) == original


def test_prefer_structural_drops_overlapping_ner() -> None:
    """A NER guess overlapping a structural match is dropped; others survive."""
    structural = RecognizerResult("IP_ADDRESS", 0, 8, 0.6)
    overlapping = RecognizerResult("PERSON", 0, 8, 0.85)
    separate = RecognizerResult("LOCATION", 20, 30, 0.85)

    kept = PIIAnonymizer._prefer_structural([structural, overlapping, separate])

    kept_spans = {(r.entity_type, r.start, r.end) for r in kept}
    assert kept_spans == {("IP_ADDRESS", 0, 8), ("LOCATION", 20, 30)}


def test_prefer_structural_keeps_non_overlapping_ner() -> None:
    """With no overlap, every result is returned unchanged."""
    structural = RecognizerResult("IP_ADDRESS", 0, 8, 0.6)
    person = RecognizerResult("PERSON", 20, 30, 0.85)

    kept = PIIAnonymizer._prefer_structural([structural, person])

    assert len(kept) == 2


def test_is_allowed_empty_and_none_allow_list() -> None:
    """With no allow list, nothing is allowed."""
    assert _allow_checker(None)._is_allowed("RHEL") is False
    assert _allow_checker([])._is_allowed("RHEL") is False


def test_is_allowed_exact_match() -> None:
    """Exact matching allows only verbatim terms."""
    checker = _allow_checker(["RHEL", "OpenShift"])
    assert checker._is_allowed("RHEL") is True
    assert checker._is_allowed("rhel") is False
    assert checker._is_allowed("Fedora") is False


def test_is_allowed_regex_match() -> None:
    """Regex matching allows terms matching any allow-list pattern (case-insensitive)."""
    checker = _allow_checker(["rh.*"], match="regex")
    assert checker._is_allowed("RHEL") is True
    assert checker._is_allowed("Fedora") is False
