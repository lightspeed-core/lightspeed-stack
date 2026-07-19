# Lightspeed Core

![LCORE](images/lcore.jpg)

---

## Contributing guidelines

Pavel Tišnovský,
ptisnovs@redhat.com

---

## Goals

* To be able to verify, review, test, and merge changes as effectively as possible
* To make sure all feature requests and/or bug fixes are put into LCORE on time
* To keep the project maintainable

---

## How?

* By making clear what are requirements for contributors and LCORE team

---

## New features

* It is a good idea to create Feature request in JIRA first
* Then epics + issues can be created for this feature

---

## Setting up your development environment (1/2)

* Please don't create branches in upstream repository
* (and don't push directly into the `main` branch ;)

---

## Setting up your development environment (2/2)

* Fork LCORE
* Clone your fork
* Setup devel environment with `uv`
* Make a new branch
* Push into the branch
* Now pull request can be created from branch in your fork

---

## Pull requests

* Structure
* Descriptions
* Copyright
* AI-generated content

---

## PR structure

* Please keep PR as small as possible!
    - the time to review seems to have O(x^n) complexity
* All irrelevant changes will make review harder
    - + there's a chance it will be rejected (we tried to be nice)
* Try to think about the overall project structure
    - utility functions
    - short handlers
    - refactoring

---

## PR description

* PR titles must start with a JIRA issue key prefix. CI enforces this via
  `pr-title-checker` (config: `.github/pr-title-checker-config.json`).
  Allowed prefixes: `LCORE-`, `RSPEED-`, `MGTM-`, `OLS-`, `RHIDP-`, `LEADS-`,
  `CWFHEALTH-`, `[release/`
    - for example: `LCORE-740: type hints for models unit tests`
* Fill-in all relevant information in the PR template
    - unused parts of PR template (like information about testing etc.) can be deleted
* Use tags if you need/want to!
* Mark PR as "Draft" if it is not ready for review
* Please note that CodeRabbitAI will create a summary of your pull request

---

## AI assistants

* “Mark” code with substantial AI-generated portions.
    - nontrivial and substantial AI-generated or AI-assisted content
* In a pull request/merge request description field, identify the code assistant that you used

---

## Copyright and licence notices

* If the contents of an entire file or files in PR were substantially generated
by a code assistant with little to no creative input or modification by you
(which should typically not be the case), copyright protection may be limited,
but it is particularly appropriate to mark the contents of the file as
recommended above.

---

## Maintainer role

* Please ask (ping) if you need to be added as a maintainer

---

## Approving pull request

* As SME you can, of course, approve pull request!
* Please note that `/lgtm` does not work as expected
* Use GH style - go to "Code changes" page and press "Submit review" button

---

## Thank you

