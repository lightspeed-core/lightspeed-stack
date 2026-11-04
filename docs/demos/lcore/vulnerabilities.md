# Vulnerability management in LCore

---

![LCORE](images/lcore.jpg)

Pavel Tišnovský,
ptisnovs@redhat.com

---

&bdquo;Do You Control Your Dependencies Or Are They Controlling You?&ldquo;

---

## Requirements

* LCore published on PyPI
* Images based on UBI
* Images published on catalog.redhat.com
* Images published on Quay.io

---

## Problems

* UBI is not minimal anymore
    - many packages and many CVEs
* Many Python dependencies
* Image Health index degrades over time
    - quickly under the new policy
* [Example](https://catalog.redhat.com/en/software/containers/lightspeed-core/lightspeed-stack-rhel9/69149c6590bc83e678940a63#security)

---

## Direct vs transitive dependencies

```
$ uv pip list | wc -l
284

$ uv tree | wc -l

Resolved 322 packages in 2ms
649
```

---

## Current state (LCore)

![State](../vulnerabilities/lcore_state.svg)

---

## Severities

![Severities](../vulnerabilities/lcore_severity.svg)

---

## Days to resolve CVE

![Days to resolve](../vulnerabilities/lcore_days.svg)

---

## Packages with most CVEs

![Packages with most CVEs](../vulnerabilities/lcore_packages.svg)

---

## New CVEs over time

![New CVEs over time](../vulnerabilities/lcore_timeline.svg)

---

## Not just LCore!

* providers
* rag-content (tool)

---

## Current state (Rag content)

![State](../vulnerabilities/rag_content_state.svg)

---

## Severities

![Severities](../vulnerabilities/rag_content_severity.svg)

---

## Days to resolve CVE

![Days to resolve](../vulnerabilities/rag_content_days.svg)

---

## Packages with most CVEs

![Packages with most CVEs](../vulnerabilities/rag_content_packages.svg)

---

## New CVEs over time

![New CVEs over time](../vulnerabilities/rag_content_timeline.svg)

---

## CVE fixes

* pyproject.toml + uv.lock
* requirements.txt used by Konflux
    - public packages
    - RHOAI packages

---

![RHOAI](../rhoai_packages/component_diagram.svg)

---

![RHOAI](../rhoai_packages/sequence_diagram.svg)

---

## Cost for every fix (PR)

* Fullsend
    - Effort: high · Cost: $2.84 - $4.28

---

## Thank you

