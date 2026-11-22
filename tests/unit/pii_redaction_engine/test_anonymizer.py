"""Model-free unit tests for the redaction engine.

These cover configuration and the startup guard without loading a spaCy model
(which is not installed in the unit-test environment). End-to-end anonymization
behavior is validated where the model is available.
"""

# pylint: disable=protected-access

import pytest
from presidio_analyzer import RecognizerResult
from pytest_mock import MockerFixture

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


def test_financial_and_id_entities_redacted_by_default() -> None:
    """Checksum/strict-format financial and government-id types are on by default."""
    expected = {
        "ABA_ROUTING_NUMBER",
        "CREDIT_CARD",
        "CRYPTO",
        "IBAN_CODE",
        "US_ITIN",
        "US_SSN",
    }
    assert expected <= set(DEFAULT_ENTITIES)
    # These are structural (pattern/checksum), so they must outrank NER guesses.
    assert expected <= PIIAnonymizer.STRUCTURAL_ENTITIES


def test_loose_predefined_recognizers_stay_off_by_default() -> None:
    """Noisy digit-run recognizers must not be enabled (they flag support-text ids)."""
    noisy = {"US_BANK_NUMBER", "US_PASSPORT", "US_DRIVER_LICENSE", "MEDICAL_LICENSE"}
    assert noisy.isdisjoint(DEFAULT_ENTITIES)


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


@pytest.fixture(name="anonymizer")
def anonymizer_fixture(mocker: MockerFixture) -> PIIAnonymizer:
    """Use the real registry and anonymizer with a model-free analyzer."""
    mocker.patch.object(PIIAnonymizer, "_require_installed", return_value="mock_model")
    mocker.patch("pii_redaction_engine.anonymizer.NlpEngineProvider")
    mocker.patch("pii_redaction_engine.anonymizer.AnalyzerEngine")
    return PIIAnonymizer(
        RedactionConfig(
            entities={"LOCATION", "PERSON", "IP_ADDRESS"},
            allow_list=["RHEL"],
            deny_list={"INTERNAL_PROJECT": ["project cedar"]},
        )
    )


def test_anonymize_text_adds_recased_match_and_preserves_allowed_term(
    anonymizer: PIIAnonymizer, mocker: MockerFixture
) -> None:
    """Apply new matches to the original text and preserve allow-listed spelling."""
    analyze = mocker.patch.object(
        anonymizer.analyzer,
        "analyze",
        side_effect=[
            [],
            [
                RecognizerResult("LOCATION", 6, 17, 0.9),
                RecognizerResult("LOCATION", 23, 27, 0.9),
            ],
        ],
    )

    assert anonymizer.anonymize_text("go to KATRINEHOLM with RHEL") == (
        "go to <LOCATION> with RHEL"
    )
    original, recased = analyze.call_args_list
    assert original.kwargs["text"] == "go to KATRINEHOLM with RHEL"
    assert recased.kwargs["text"] == "go to Katrineholm with Rhel"
    assert recased.kwargs["entities"] == ["LOCATION"]


def test_anonymize_text_keeps_first_pass_overlap(
    anonymizer: PIIAnonymizer, mocker: MockerFixture
) -> None:
    """A higher-scoring second-pass match cannot override a first-pass span."""
    analyze = mocker.patch.object(
        anonymizer.analyzer,
        "analyze",
        side_effect=[
            [RecognizerResult("PERSON", 0, 4, 0.6)],
            [RecognizerResult("LOCATION", 0, 4, 0.9)],
        ],
    )

    assert anonymizer.anonymize_text("JANE arrived") == "<PERSON> arrived"
    assert analyze.call_count == 2


def test_anonymize_text_prefers_structural_match(
    anonymizer: PIIAnonymizer, mocker: MockerFixture
) -> None:
    """Use the structural replacement even when the NER guess scores higher."""
    mocker.patch.object(
        anonymizer.analyzer,
        "analyze",
        return_value=[
            RecognizerResult("IP_ADDRESS", 3, 12, 0.6),
            RecognizerResult("PERSON", 3, 12, 0.9),
        ],
    )

    assert anonymizer.anonymize_text("at 192.0.2.1 now") == "at <IP_ADDRESS> now"


@pytest.mark.parametrize(
    ("text", "case_normalization", "entities"),
    [
        ("visit ROME", False, ["LOCATION"]),
        ("visit ROME", True, ["PERSON"]),
        ("visit Rome", True, ["LOCATION"]),
    ],
    ids=["disabled", "no-eligible-entities", "unchanged-text"],
)
def test_anonymize_text_skips_unneeded_second_pass(
    anonymizer: PIIAnonymizer,
    mocker: MockerFixture,
    text: str,
    case_normalization: bool,
    entities: list[str],
) -> None:
    """Call the analyzer once when case normalization cannot add matches."""
    anonymizer.case_normalization = case_normalization
    anonymizer.entities = entities
    analyze = mocker.patch.object(anonymizer.analyzer, "analyze", return_value=[])

    assert anonymizer.anonymize_text(text) == text
    analyze.assert_called_once()


def test_anonymize_text_registers_and_requests_deny_list_entity(
    anonymizer: PIIAnonymizer, mocker: MockerFixture
) -> None:
    """Run the configured deny-list recognizer and redact its match."""
    text = "open project cedar"
    recognizer = anonymizer.registry.get_recognizers(
        language="en", entities=["INTERNAL_PROJECT"]
    )[0]
    matches = recognizer.analyze(text, entities=["INTERNAL_PROJECT"])
    analyze = mocker.patch.object(anonymizer.analyzer, "analyze", return_value=matches)

    assert anonymizer.anonymize_text(text) == "open <INTERNAL_PROJECT>"
    assert "INTERNAL_PROJECT" in analyze.call_args.kwargs["entities"]
