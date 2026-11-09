# PII Redaction Engine

PII and sensitive-data redaction for Lightspeed Core, built on
[Microsoft Presidio](https://github.com/data-privacy-stack/presidio). It detects
and replaces sensitive values in text with typed markers (`<PERSON>`,
`<EMAIL_ADDRESS>`, …), using regex recognizers for structured data and a spaCy
NLP model for free-text entities.

```python
from pii_redaction_engine.anonymizer import PIIAnonymizer

anonymizer = PIIAnonymizer()
anonymizer.anonymize_text("sam@redhat.com from Red Hat asks about OpenShift")
# -> "<EMAIL_ADDRESS> from Red Hat asks about OpenShift"
```

Which entities, allow/deny lists, and options apply are configured with
`RedactionConfig`:

```python
from pii_redaction_engine.anonymizer import (
    DEFAULT_ENTITIES,
    PIIAnonymizer,
    RedactionConfig,
)

anonymizer = PIIAnonymizer(
    RedactionConfig(
        entities=DEFAULT_ENTITIES | {"ORGANIZATION"},  # also redact organizations
        allow_list=["OpenShift", "RHEL"],              # ...but keep these
        deny_list={"ORGANIZATION": ["Red Hat"]},       # always redact these
    ),
)
```

The spaCy model is pinned to `en_core_web_lg` and must be installed separately
(it is not pulled in automatically):

```
python -m spacy download en_core_web_lg
```

`en_core_web_lg` ships without a torch dependency, which keeps the install
lightweight. The trade-off is weaker person/location recall: it mislabels many
non-English place names and surnames as organizations, which are exempt from
redaction by default.

## Provenance and attribution

This code is **vendored** from Red Hat's internal `data-anonymizer` library
(`gitlab.cee.redhat.com/uxe-data-ai-solutions/data-anonymizer`), developed by the
UXE Data & AI Solutions team for the Ask Red Hat agent. It was vendored rather than 
consumed as an external dependency to keep it maintainable within Lightspeed Core 
without a cross-repo release and support burden.

Original authors / contributors to `data-anonymizer`:
- Ryan Mullett (rdmullett)
- Vamsi Mathala (vamsi-01)
- Michael Hoang (mike-hoang)

The Lightspeed Core team maintains this copy and owns its tuning, testing,
accuracy bar, and support for Lightspeed workloads. Redaction is not guaranteed 100% 
correct for every PII variation; validation for Lightspeed is owned in this repository.

Licensed under Apache-2.0 (the Lightspeed Core license). Presidio and the spaCy
models are used under their respective open-source licenses.

## Customizations over stock Presidio

The value over a from-scratch Presidio config is domain tuning carried over from
`data-anonymizer`:

- **Organization detection is off by default** — product/tech names (`OpenShift`,
  `RHEL`, `Sosreport`) would otherwise be flagged as organizations. Add
  `"ORGANIZATION"` to `RedactionConfig.entities`, usually paired with an
  `allow_list`, to enable it.
- **Structural matches outrank NER guesses** — an IP/hostname/email/URL matched by
  regex is not re-labelled as a person/location by the model.
- **Custom recognizers** — `EmailRecognizer` (handles emails separated by special
  characters) and `HostnameRecognizer` (ccTLDs, internal TLDs, and file-extension
  vs domain disambiguation for support text).
- **Curated phone regions** — ~60 regions, deliberately excluding CZ/VN because
  their formats collide with CVE and Bugzilla identifiers common in support text.
- **Case-normalization pass** — a second pass over a title-cased copy recovers
  ALL-CAPS locations (e.g. address blocks) that spaCy's case-sensitive NER misses.
- **allow_list / deny_list** — keep specific terms, or always redact them
  regardless of what the model detects.
