"""Presidio-based PII detection and redaction.

Bootstrapped from Red Hat's internal data-anonymizer library; see README.md for
attribution and the customizations over stock Presidio.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import spacy.util
from presidio_analyzer import (
    AnalyzerEngine,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    IpRecognizer,
    PhoneRecognizer,
    SpacyRecognizer,
    UrlRecognizer,
)
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import RecognizerResult as AnonymizerRecognizerResult

from pii_redaction_engine.recognizers.email_recognizer import EmailRecognizer
from pii_redaction_engine.recognizers.hostname_recognizer import HostnameRecognizer

# Entity types detected by default. ORGANIZATION and URL are intentionally off:
# organization detection over-flags product/tech names (OpenShift, RHEL), and URLs
# are usually wanted in telemetry. Enable them via RedactionConfig.entities.
DEFAULT_ENTITIES: frozenset[str] = frozenset(
    {"EMAIL_ADDRESS", "HOSTNAME", "IP_ADDRESS", "LOCATION", "PERSON", "PHONE_NUMBER"}
)


@dataclass
class RedactionConfig:
    """Configuration for :class:`PIIAnonymizer`.

    Attributes:
        entities: Entity types to detect and redact. Defaults to DEFAULT_ENTITIES.
        allow_list: Terms kept in the text even if detected as PII.
        allow_list_match: How allow_list is interpreted, "exact" or "regex".
        deny_list: Entity type -> terms always flagged as that type, regardless of
            NER/regex detection (enables the entity type even if otherwise off).
        case_normalization: Run a second pass over an ALL-CAPS-normalized copy to
            recover locations spaCy's case-sensitive NER misses.

    """

    entities: set[str] = field(default_factory=lambda: set(DEFAULT_ENTITIES))
    allow_list: Optional[list[str]] = None
    allow_list_match: str = "exact"
    deny_list: Optional[dict[str, list[str]]] = None
    case_normalization: bool = True


class PIIAnonymizer:
    """Detect and redact PII in text using Presidio with Red Hat-specific tuning.

    See the package README for the customizations over stock Presidio.
    """

    # The spaCy NER model, pinned for the whole project. It ships with the base install
    # (no torch dependency). It mislabels most non-English place names and surnames as ORG
    # rather than GPE/LOC/PERSON, so with organizations exempt it detects few locations and
    # no people; this is an accepted trade-off for keeping the install lightweight.
    SPACY_MODEL = "en_core_web_lg"

    # spaCy NER labels that are never PII. ORGANIZATION is appended to this list unless
    # the caller opts in, since organization names are exempt from anonymization.
    BASE_LABELS_TO_IGNORE = [
        "CARDINAL",
        "EVENT",
        "LANGUAGE",
        "LAW",
        "MONEY",
        "ORDINAL",
        "PERCENT",
        "PRODUCT",
        "QUANTITY",
        "WORK_OF_ART",
    ]

    # Runs of 3+ uppercase letters. spaCy's NER is case sensitive and misses entities
    # written in all caps, which is common in address blocks ("KATRINEHOLM", "GUERET").
    ALL_CAPS_PATTERN = re.compile(r"\b[^\Wa-z\d_]{3,}\b")

    # Mirrors the regex_flags default AnalyzerEngine.analyze() applies to allow_list terms.
    ALLOW_LIST_REGEX_FLAGS = re.IGNORECASE | re.MULTILINE | re.DOTALL

    # Entities matched by regex rather than by the NER model. A structural match is near
    # certain, so it outranks any NER guess covering the same span: spaCy scores its guesses
    # at 0.85, which otherwise beats IpRecognizer's 0.6 and reports an IP address as a person.
    STRUCTURAL_ENTITIES = {"EMAIL_ADDRESS", "HOSTNAME", "IP_ADDRESS", "URL"}
    NER_ENTITIES = {"LOCATION", "ORGANIZATION", "PERSON"}

    # All caps text is an address block trait, so the case normalized pass only looks for
    # locations. Letting it report people as well turns recased acronyms into false
    # positives ("RHEL" -> "Rhel"), and it finds no people the first pass misses anyway.
    CASE_NORMALIZED_ENTITIES = ["LOCATION"]

    # Presidio defaults to eight regions, which misses most non-anglophone numbers.
    # Each added region also widens what counts as a phone number, so the list is not
    # free: CZ and VN are deliberately absent. Czech formats match a CVE identifier
    # ("CVE-2024-21626" -> "2024-21626") and Vietnamese ones match a bare Bugzilla id.
    # Both are common in support text and worthless once redacted, and numbers from
    # either country are still matched by the other regions' formats.
    PHONE_SUPPORTED_REGIONS = [
        "US",
        "GB",
        "DE",
        "FR",
        "IL",
        "IN",
        "CA",
        "BR",
        "ES",
        "PT",
        "IT",
        "NL",
        "AT",
        "CH",
        "SE",
        "NO",
        "DK",
        "FI",
        "JP",
        "AU",
        "NZ",
        "MX",
        "AE",
        "IE",
        "BE",
        "RU",
        "ZA",
        "KR",
        "TH",
        "PH",
        "MY",
        "SG",
        "HK",
        "TW",
        "ID",
        "EG",
        "SA",
        "KE",
        "NG",
        "GH",
        "TR",
        "UA",
        "RO",
        "HU",
        "BG",
        "HR",
        "SK",
        "SI",
        "LT",
        "LV",
        "EE",
        "IS",
        "GR",
        "CY",
        "MT",
    ]

    def __init__(self, config: Optional[RedactionConfig] = None) -> None:
        """Build the analyzer and anonymizer for the given configuration.

        Args:
            config: Redaction configuration (entities, allow/deny lists, options).
                Defaults to ``RedactionConfig()`` (the standard entity set).

        """
        config = config or RedactionConfig()

        self.registry = RecognizerRegistry()
        self.registry.add_recognizer(EmailRecognizer())
        self.registry.add_recognizer(HostnameRecognizer())
        self.registry.add_recognizer(IpRecognizer())
        self.registry.add_recognizer(
            PhoneRecognizer(supported_regions=self.PHONE_SUPPORTED_REGIONS)
        )
        self.registry.add_recognizer(SpacyRecognizer())
        self.registry.add_recognizer(UrlRecognizer())

        for entity_type, terms in (config.deny_list or {}).items():
            self.registry.add_recognizer(
                PatternRecognizer(supported_entity=entity_type, deny_list=terms)
            )

        # spaCy's ORGANIZATION label is ignored unless organization detection is
        # enabled, since it over-flags product and technology names.
        labels_to_ignore = list(self.BASE_LABELS_TO_IGNORE)
        if "ORGANIZATION" not in config.entities:
            labels_to_ignore.append("ORGANIZATION")

        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [
                    {
                        "lang_code": "en",
                        "model_name": self._require_installed(self.SPACY_MODEL),
                    }
                ],
                "ner_model_configuration": {"labels_to_ignore": labels_to_ignore},
            }
        ).create_engine()

        self.analyzer = AnalyzerEngine(registry=self.registry, nlp_engine=nlp_engine)
        self.anonymizer = AnonymizerEngine()

        # Deny-listed entity types are honoured even when not in the entity set.
        self.entities = list(config.entities | set(config.deny_list or {}))

        self.allow_list = config.allow_list
        self.allow_list_match = config.allow_list_match
        self.case_normalization = config.case_normalization

    @classmethod
    def _require_installed(cls, model_name: str) -> str:
        """
        Reject a model that is not installed, before Presidio tries to fetch it.

        Presidio downloads a model it cannot find rather than failing. That would pull
        several hundred MB at runtime, so a model that is not already present is rejected
        before it gets that far.

        Args:
            model_name (str): Name of the spaCy model to load.

        Returns:
            str: The same name, once it is known to be installed.

        Raises:
            ValueError: If the named model is not installed.

        """
        if not spacy.util.is_package(model_name):
            raise ValueError(
                f"spaCy model '{model_name}' is not installed. "
                f"Install it with: python -m spacy download {model_name}"
            )

        return model_name

    @classmethod
    def _normalize_case(cls, content_text: str) -> str:
        """
        Title case any run of 3+ uppercase letters, leaving every other character alone.

        Character offsets are preserved so that spans found in the normalized text point
        at the same substring in the original.

        Args:
            content_text (str): Input string to normalize.

        Returns:
            str: The input with all caps words title cased.

        """
        characters = list(content_text)

        for match in cls.ALL_CAPS_PATTERN.finditer(content_text):
            word = match.group(0)
            # The pattern excludes only ASCII a-z, so lowercase non-ASCII runs (e.g.
            # Cyrillic/Greek) also match; isupper() keeps the pass to genuine all-caps.
            if not word.isupper():
                continue
            title_cased = word.title()
            # Some characters change length when recased (e.g. "ß" -> "Ss"), which would
            # shift every following offset. Skip those rather than misalign the spans.
            if len(title_cased) == len(word):
                characters[match.start() : match.end()] = title_cased

        return "".join(characters)

    @classmethod
    def _prefer_structural(
        cls, results: list[RecognizerResult]
    ) -> list[RecognizerResult]:
        """
        Drop NER guesses that overlap a structural match.

        An IP address or hostname is identified by its shape, so a model guessing that the
        same characters are a person or a place is wrong by construction. Presidio resolves
        the overlap on score alone, which lets the guess win.

        Args:
            results (List[RecognizerResult]): Detected entities, before conflict resolution.

        Returns:
            List[RecognizerResult]: The input without NER matches covering a structural one.

        """
        structural = [
            result
            for result in results
            if result.entity_type in cls.STRUCTURAL_ENTITIES
        ]
        if not structural:
            return results

        return [
            result
            for result in results
            if not (
                result.entity_type in cls.NER_ENTITIES
                and any(
                    result.start < found.end and result.end > found.start
                    for found in structural
                )
            )
        ]

    def _is_allowed(self, value: str) -> bool:
        """
        Check a span of the original text against the allow list.

        Recasing hides the original spelling from the analyzer, so an allowed term such as
        "RHEL" stops matching the allow list once it becomes "Rhel". Second pass matches are
        therefore re-checked against the text the caller actually passed in.

        Args:
            value (str): The matched substring, taken from the original text.

        Returns:
            bool: True if the caller allowed this term to stay in the text.

        """
        if not self.allow_list:
            return False

        if self.allow_list_match == "regex":
            pattern = "|".join(term for term in self.allow_list if term)
            return (
                bool(pattern)
                and re.search(pattern, value, self.ALLOW_LIST_REGEX_FLAGS) is not None
            )

        return value in self.allow_list

    def _analyze(self, content_text: str) -> list[RecognizerResult]:
        """
        Run PII detection over the text, then again over a case normalized copy.

        The second pass only contributes matches that do not overlap a first pass match,
        so recasing can add entities that spaCy missed but never override what it found.

        Args:
            content_text (str): Input string to be processed for PII.

        Returns:
            List[RecognizerResult]: Detected entities, as offsets into content_text.

        """

        def run(text: str, entities: list[str]) -> list[RecognizerResult]:
            return self.analyzer.analyze(
                allow_list=self.allow_list,
                allow_list_match=self.allow_list_match,
                text=text,
                entities=entities,
                language="en",
            )

        entity_matches = run(content_text, self.entities)

        recased_entities = (
            [
                entity
                for entity in self.CASE_NORMALIZED_ENTITIES
                if entity in self.entities
            ]
            if self.case_normalization
            else []
        )

        if recased_entities:
            normalized_text = self._normalize_case(content_text)
            if normalized_text != content_text and len(normalized_text) == len(
                content_text
            ):
                for match in run(normalized_text, recased_entities):
                    overlaps = any(
                        match.start < found.end and match.end > found.start
                        for found in entity_matches
                    )
                    if overlaps or self._is_allowed(
                        content_text[match.start : match.end]
                    ):
                        continue
                    entity_matches.append(match)

        return self._prefer_structural(entity_matches)

    def anonymize_text(self, content_text: str) -> str:
        """Process the input string for PII.

        Args:
            content_text (str): Input string to be processed for PII.

        Returns:
            str: Anonymized string for the given input.

        """
        if not content_text:
            return content_text

        entity_matches = self._analyze(content_text)
        sorted_entity_matches = sorted(
            entity_matches, key=lambda x: x.start, reverse=True
        )

        # presidio_analyzer and presidio_anonymizer each define their own
        # RecognizerResult class; convert the analyzer's results to the anonymizer's
        # type so the call is correctly typed (same fields).
        anonymizer_results = [
            AnonymizerRecognizerResult(
                match.entity_type, match.start, match.end, match.score
            )
            for match in sorted_entity_matches
        ]

        result = self.anonymizer.anonymize(
            text=content_text,
            analyzer_results=anonymizer_results,
            # Fixes: https://github.com/microsoft/presidio/pull/1932
            merge_entities_with_spaces=False,
        )

        return result.text

    def anonymize_list(self, content_list: list[str]) -> list[str] | None:
        """Process the input list of strings for PII.

        Args:
            content_list: Input strings to be processed for PII.

        Returns:
            List[str] | None: Anonymized content for the given input.

        """
        if not content_list:
            return content_list

        anonymized_content = []

        for each_line in content_list:
            anonymized_text = self.anonymize_text(each_line)
            anonymized_content.append(anonymized_text)

        return anonymized_content
