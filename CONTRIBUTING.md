# CONTRIBUTING

<!-- the following line is used by tool to autogenerate Table of Content when the document is changed -->
<!-- vim-markdown-toc GFM -->

* [TLDR;](#tldr)
* [Before you start](#before-you-start)
* [New feature requests](#new-feature-requests)
* [Prerequisites](#prerequisites)
    * [Tooling installation](#tooling-installation)
* [Setting up your development environment](#setting-up-your-development-environment)
* [Local validation](#local-validation)
* [PR description](#pr-description)
* [Pull request size](#pull-request-size)
* [Backports](#backports)
    * [Installation](#installation)
    * [Usage](#usage)
* [Definition of Done](#definition-of-done)
    * [A deliverable is considered done when](#a-deliverable-is-considered-done-when)
* [AI assistants](#ai-assistants)
    * [Mark substantial AI-generated content](#mark-substantial-ai-generated-content)
    * [Copyright and licence notices](#copyright-and-licence-notices)
* [Automation](#automation)
    * [Pre-commit hook settings](#pre-commit-hook-settings)
* [Code coverage measurement](#code-coverage-measurement)
* [Linters](#linters)
    * [OpenAPI (Spectral)](#openapi-spectral)
    * [Type hints checks](#type-hints-checks)
    * [Ruff](#ruff)
    * [Pylint](#pylint)
    * [Security checks](#security-checks)
* [Code style](#code-style)
    * [Function standards](#function-standards)
        * [Documentation](#documentation)
        * [Type annotations](#type-annotations)
        * [Naming conventions](#naming-conventions)
        * [Async functions](#async-functions)
        * [Error handling](#error-handling)
    * [Formatting rules](#formatting-rules)
    * [Docstrings style](#docstrings-style)

<!-- vim-markdown-toc -->

## TLDR;

1. Create an RFE for new features before implementation work starts.
2. Fork the repository and make your changes in a topic branch.
3. Keep the pull request focused on one feature, fix, or refactor.
4. Add or update tests and documentation for user-visible behavior.
5. Run `uv run make format`, `uv run make verify`, and `uv run make test-unit`.
6. Open a pull request against the `main` branch with a valid JIRA prefix in the title.

## Before you start

Lightspeed Core Stack is an AI-powered assistant built on FastAPI, LLM providers,
agents, and RAG services. Changes often affect several layers of the stack, so
please check the existing code, configuration, and tests before adding a new
pattern.

Prefer small, easy-to-review changes. If you are unsure whether a change belongs
in this repository, or whether it should be split into multiple pull requests,
open the RFE or issue first and describe the intended scope.

## New feature requests

1. Create an RFE. For Red Hat contributors, create it in the LCORE project. For
   external contributors, create it in GitHub. The RFE gives reviewers a shared
   place to discuss the requirement, expected behavior, and release timing.
2. Wait for vetting. Pavel Tisnovsky and Stefan Bunciak review RFEs for project
   fit, priority, and alignment with the roadmap.
3. Include tests and documentation. Feature work should cover the behavior,
   configuration options, and any important operational notes.

Bug fixes do not need a separate RFE unless they change public behavior or grow
into feature work.

## Prerequisites

- `git`
- Python 3.12, 3.13, or 3.14, as defined by `pyproject.toml`
- `pip`
- `uv`
- Node.js 18 or newer, including `npm` and `npx`

The project requires Python 3.12 or newer. Python 3.12 brought performance and
typing improvements that are useful for modern ML, AI, LLM, and asynchronous
service code. The supported range is controlled by `requires-python` in
`pyproject.toml`.

Node.js is required for the local OpenAPI lint check. The `make verify` target
runs `make lint-openapi`, which calls:

```bash
npx --yes @stoplight/spectral-cli@6 lint docs/devel_doc/openapi.json
```

If `npx` is not installed, `lint-openapi` is skipped locally with a message and
`make verify` can still succeed. CI always runs the Spectral check, so installing
Node locally is the best way to catch OpenAPI problems before opening a PR.

### Tooling installation

Install `uv` and confirm it is available:

```bash
pip install --user uv
uv --version
```

Install Node.js from your operating system package manager or from the Node.js
download page. For example:

```bash
# Fedora
sudo dnf install nodejs

# macOS with Homebrew
brew install node

node --version
npx --version
```

CI currently uses Node 22 for Spectral; an active LTS release is sufficient for
local development.

## Setting up your development environment

Clone your fork and install the development dependencies from the project root:

```bash
# clone your fork
git clone https://github.com/YOUR-GIT-PROFILE/lightspeed-stack.git

# move into the directory
cd lightspeed-stack
uv sync --group dev --group ogxlibdev
```

Use `uv run` for project commands so the correct virtual environment and pinned
dependencies are used:

```bash
uv run make test-unit
uv run make test-integration
uv run make format
uv run make verify
uv run make check-types
```

If you need to debug dependency or import problems, first check which Python is
being used:

```bash
which python
uv run which python
```

Then confirm that dependencies were installed from the project root with:

```bash
uv sync --group dev --group ogxlibdev
```

Do not assume that an activated shell environment is using the same interpreter
as `uv run`.

Happy hacking!

## Local validation

Run the same checks locally that reviewers and CI expect:

```bash
uv run make format
uv run make verify
uv run make test-unit
```

Run integration or end-to-end tests when the change affects runtime behavior,
configuration, providers, persistence, authentication, or external service
integration:

```bash
uv run make test-integration
uv run make test-e2e
```

If your change updates API models, endpoint response shapes, router tags, or
OpenAPI metadata, regenerate the OpenAPI schema and commit the generated output:

```bash
uv run make schema
```

## PR description

- PR titles must start with a JIRA issue key prefix or the target branch of a
  backport in brackets. CI enforces this with `pr-title-checker` using
  `.github/pr-title-checker-config.json`.
- Allowed prefixes are `LCORE-`, `RSPEED-`, `MGTM-`, `OLS-`, `RHIDP-`,
  `LEADS-`, `CWFHEALTH-`, and `[release/`.
- Example: `LCORE-740: add type hints for model unit tests`.
- Fill in the relevant parts of the pull request template. Remove sections that
  do not apply so reviewers can focus on the actual change.
- Describe what changed, why it changed, how it was tested, and any rollout,
  migration, compatibility, or follow-up concerns.
- CodeRabbitAI may add an automated PR summary. Treat it as supplemental; the
  human-written PR description is still the source of review context.

## Pull request size

* Keep pull requests small. Aim for about 200 lines when possible and generally
  stay under 500 lines. Research shows smaller PRs are reviewed and merged more
  quickly, reduce reviewer cognitive load, make testing easier, and lower the
  risk of introducing bugs. If a change must be larger, break it into a clear
  sequence of smaller commits or dependent PRs, include a concise summary of
  the intent and scope, and highlight the critical files or areas to review.

* Make each pull request address a single feature or bug fix. Combining
  multiple unrelated changes in one PR makes reviews harder and increases the
  chance of overlooked issues. Break larger work into smaller, self-contained
  units that can be reviewed and merged independently. For bigger tasks,
  sequence dependent PRs, provide clear descriptions of scope and intent, and
  call out which files or behaviors need careful review.

* Keep the count of modified files small in addition to limiting total lines
  changed. Touching many files increases reviewer overhead, makes it harder to
  understand the scope, and raises the chance of missed regressions. When a
  change necessarily spans multiple files, group related edits into logical,
  incremental PRs; move large, nonfunctional refactors into separate commits or
  PRs; and add a clear summary and guided review notes that point reviewers to
  the most important files and risk areas.

* When you split a larger task into several smaller PRs, craft detailed commit
  messages that explain what each change does and how it fits into the broader
  effort. Include the rationale, any trade-offs, and links or references to
  related PRs or tickets. Good messages preserve context across multiple
  submissions, speed up reviews, and make it easier for future maintainers to
  trace the evolution of the code.

* Ensure each pull request is a self-contained unit that can be merged
  independently. An atomic PR has a single, clear objective—such as fixing a
  bug or adding one feature—and includes only the changes necessary to achieve
  that goal. Avoid coupling the PR to other unmerged branches or relying on
  external context; if work must be split, sequence dependent PRs so each stage
  is reviewable on its own. Don’t mix unrelated change types (for example, bug
  fixes, refactors, and new features) in the same PR. When appropriate,
  separate large refactors or formatting changes into their own PRs, and add
  concise descriptions that state the PR’s intent and any necessary migration
  or rollout steps.



## Backports

We use [cherry_picker](https://pypi.org/project/cherry-picker/) to backport
merged pull requests to release branches. See the
[cherry_picker documentation](https://cherry-picker.readthedocs.io/) for full
details.

### Installation

```bash
pip install --user cherry_picker
```

### Usage

After a pull request has been merged to `main`, backport it to one or more
release branches:

```bash
# backport to a single release branch
cherry_picker <commit-sha> release/0.6

# backport to multiple release branches
cherry_picker <commit-sha> release/0.5 release/0.6
```

`cherry_picker` creates a branch, cherry-picks the commit, and opens a pull
request against the target release branch.

If the commit you want to backport is a merge commit, append `^-` to the hash so
that `cherry_picker` applies the correct parent diff:

```bash
cherry_picker <merge-commit-sha>^- release/0.6
```

If there are conflicts, `cherry_picker` pauses so you can resolve them. After
resolving:

```bash
git add .
cherry_picker --continue
```

To abort a backport in progress:

```bash
cherry_picker --abort
```

See the [branching documentation](docs/maintenance/branching.md) for more details on the
branching strategy and release workflow.

## Definition of Done

### A deliverable is considered done when

- Code is complete, reviewed, and merged to the relevant branch.
- User-facing documentation has been updated where relevant.
- Acceptance criteria in the related Jira ticket are verified.
- The pull request title and commits include the Jira number where required.
- Unit tests pass in CI for relevant changes.
- Integration tests pass in CI for relevant changes.
- End-to-end tests pass in CI for relevant changes.
- Linters and type checks pass in CI.
- The change has been reviewed by at least one peer.
- The change has been acknowledged by at least one project owner when required.

## AI assistants

### Mark substantial AI-generated content

Nontrivial or substantial AI-generated and AI-assisted content should be marked
when appropriate. This is especially important when a code assistant produced a
large portion of a change and you have confirmed that the suggestion is not a
copy of existing third-party code.

You can identify the assistant in a commit message or pull request description.
For example:

```text
Assisted-by: <name of code assistant>
```

If a source file contains a substantial generated block, a short source comment
may also be appropriate:

```text
Generated by: <name of code assistant>
```

### Copyright and licence notices

If the contents of an entire file, or several files, were substantially
generated by a code assistant with little creative input or modification from
you, copyright protection may be limited. In that situation, clearly marking the
generated content is particularly important.

## Automation

### Pre-commit hook settings

You can run formatters and linters automatically before each commit by copying
the provided hook into your local Git hooks directory:

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

This step is manual because Git treats executable hooks as local configuration,
not repository content that should be enabled automatically for every clone.

## Code coverage measurement

Unit and integration test runs measure code coverage. If coverage falls below
the thresholds configured in `pyproject.toml`, the test command fails.

Coverage reports are written as JSON and JUnit-compatible output under the test
artifact directory. By default, that directory is `tests/test_results`; override
it with the `ARTIFACT_DIR` environment variable when needed.

## Linters

The project uses Black, Ruff, Pyright, Pylint, Pydocstyle, Mypy, Bandit, and
Spectral. Configuration lives in `pyproject.toml`, the `Makefile`, and the
OpenAPI Spectral workflow.

Run the complete lint and type-check suite with:

```bash
uv run make verify
```

### OpenAPI (Spectral)

OpenAPI is linted with [Spectral](https://stoplight.io/open-api/) through the
`lint-openapi` target. This target is part of `make verify`.

If you introduce a new router tag with `APIRouter(tags=[...])`, also extend the
global tag list in `src/app/main.py` and regenerate `docs/devel_doc/openapi.json`.
See [docs/contributing/openapi-tags-and-spectral.md](docs/contributing/openapi-tags-and-spectral.md)
for details.

### Type hints checks

Run the type hint checks with:

```bash
uv run make check-types
```

The first run can be slow. Later runs are usually faster because Mypy reuses its
cache.

### Ruff

List the Ruff rule groups recognized by your installed Ruff version with:

```bash
uv run ruff linter
```

Ruff rule documentation is available at
[https://docs.astral.sh/ruff/rules/](https://docs.astral.sh/ruff/rules/).

Use `noqa` comments only when there is a clear reason to suppress a rule:

```python
# noqa: E501
```

### Pylint

List Pylint messages with:

```bash
uv run pylint --list-msgs
```

Pylint documentation is available at
[https://pylint.readthedocs.io/en/latest/user_guide/checkers/features.html](https://pylint.readthedocs.io/en/latest/user_guide/checkers/features.html).

Use targeted disables when a rule must be suppressed:

```python
# pylint: disable=C0415
```

### Security checks

Static security checks are performed with Bandit:

```bash
uv run make security-check
```

Never commit secrets, tokens, private keys, or provider credentials. Use
environment variables or configuration mechanisms designed for sensitive values.

## Code style

### Function standards

#### Documentation

All modules, classes, and functions should have clear docstrings. Keep the first
sentence concise and add details only when they help future readers understand
the behavior, parameters, return values, or raised exceptions.

#### Type annotations

Use complete type annotations for function parameters, return values, and class
attributes.

- Use `typing_extensions.Self` for Pydantic model validators.
- Prefer modern union syntax such as `str | int`.
- Use `Optional[Type]` where the surrounding codebase already follows that
  convention.

#### Naming conventions

Use `snake_case` for functions and variables. Prefer descriptive,
action-oriented names such as `get_`, `validate_`, `build_`, and `check_` when
they match the behavior.

#### Async functions

Use `async def` for I/O work and calls to external services. Keep synchronous
helpers synchronous when they only transform local data.

#### Error handling

- Use FastAPI `HTTPException` with appropriate status codes in endpoint code.
- Handle `APIConnectionError` from OGX where appropriate.
- Preserve useful context in logs without exposing secrets or credentials.

### Formatting rules

Code formatting is handled by Black and Ruff:

```bash
uv run make format
```

Black documentation is available at
[https://black.readthedocs.io/en/stable/](https://black.readthedocs.io/en/stable/).

### Docstrings style

We use [Google's docstring style](https://google.github.io/styleguide/pyguide.html).

Example:

```python
def function_with_pep484_type_annotations(param1: int, param2: str) -> bool:
    """Example function with PEP 484 type annotations.

    Args:
        param1: The first parameter.
        param2: The second parameter.

    Returns:
        The return value. True for success, False otherwise.

    Raises:
        ValueError: If the first parameter does not contain a valid model name.
    """
```

For more examples, follow the existing codebase.
