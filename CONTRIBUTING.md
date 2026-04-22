# CONTRIBUTING

<!-- the following line is used by tool to autogenerate Table of Content when the document is changed -->
<!-- vim-markdown-toc GFM -->

* [TLDR;](#tldr)
* [Prerequisites](#prerequisites)
    * [Tooling installation](#tooling-installation)
* [Setting up your development environment](#setting-up-your-development-environment)
* [PR description](#pr-description)
* [Pull request size](#pull-request-size)
* [Definition of Done](#definition-of-done)
    * [A deliverable is to be considered “done” when](#a-deliverable-is-to-be-considered-done-when)
* [AI assistants](#ai-assistants)
    * [“Mark” code with substantial AI-generated portions.](#mark-code-with-substantial-ai-generated-portions)
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
    * [Function Standards](#function-standards)
        * [Documentation](#documentation)
        * [Type annotations](#type-annotations)
        * [Naming conventions](#naming-conventions)
        * [Async functions](#async-functions)
        * [Error handling](#error-handling)
    * [Formatting rules](#formatting-rules)
    * [Docstrings style](#docstrings-style)

<!-- vim-markdown-toc -->

## TLDR;

1. Create your own fork of the repo
2. Make changes to the code in your fork
3. Run unit tests and integration tests
4. Check the code with linters
5. Submit PR from your fork to main branch of the project repo


## Prerequisites

- git
- Python 3.12 or 3.13
- pip
- **Node.js** (18 or newer; **npm** and **`npx`** ship with Node). **`make verify`** runs **`lint-openapi`**, which calls **`npx --yes @stoplight/spectral-cli@6`** (see `Makefile`). If **`npx`** is not installed, **`lint-openapi` is skipped** with a message so **`make verify` still succeeds** locally; install Node to run the OpenAPI check. **CI** always runs Spectral (see `.github/workflows/openapi_spectral.yaml`).

The development requires at least [Python 3.12](https://docs.python.org/3/whatsnew/3.12.html) due to significant improvement on performance, optimizations which benefit modern ML, AI, LLM, NL stacks, and improved asynchronous processing capabilities. It is also possible to use Python 3.13.



### Tooling installation

1. `pip install --user uv`
1. `uv --version` -- should return no error
1. Install [Node.js](https://nodejs.org/en/download) (LTS is fine) or use your OS package manager, e.g. Fedora: `sudo dnf install nodejs`, macOS with [Homebrew](https://brew.sh/): `brew install node`. Confirm `node --version` and `npx --version` work. CI uses Node 22 for Spectral (see `.github/workflows/openapi_spectral.yaml`).



## Setting up your development environment

```bash
# clone your fork
git clone https://github.com/YOUR-GIT-PROFILE/lightspeed-stack.git

# move into the directory
cd lightspeed-stack

# setup your devel environment with uv
uv sync --group dev

# Now you can run test commands trough make targets, or prefix the rest of commands with `uv run`, eg. `uv run make test` or do `uv venv`, which creates virtual environment and prints activation command, and run commands inside venv.

# run unit tests
make test-unit

# run integration tests
make test-integration

# code formatting
# (this is also run automatically as part of pre-commit hook if configured)
make format

# code style and docstring style
# (this is also run automatically as part of pre-commit hook if configured)
make verify

# check type hints
# (this is also run automatically as part of pre-commit hook)
make check-types
```

Happy hacking!


## PR description

* Jira ticket needs to be added into PR title, for example: `LCORE-740: type hints for models unit tests`
* Fill-in all relevant information in the PR template
    - unused parts of PR template (like information about testing etc.) can be deleted
* Please note that CodeRabbitAI will create a summary of your pull request


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



## Definition of Done

### A deliverable is to be considered “done” when

* Code is complete, commented, and merged to the relevant release branch
* User facing documentation written (where relevant)
* Acceptance criteria in the related Jira ticket (where applicable) are verified and fulfilled
* Pull request title+commit includes Jira number
* Changes are covered by unit tests that run cleanly in the CI environment (where relevant)
* Changes are covered by integration tests that run cleanly in the CI environment (where relevant)
* Changes are covered by E2E tests that run cleanly in the CI environment (where relevant)
* All linters are running cleanly in the CI environment
* Code changes reviewed by at least one peer
* Code changes acked by at least one project owner

## AI assistants

### “Mark” code with substantial AI-generated portions.

Nontrivial and substantial AI-generated or AI-assisted content should be
“marked” in appropriate cases. In deciding how to approach this, consider
adopting one or more of the following recommendations. (This assumes you have
not concluded that a suggestion is a match to some existing third-party code.) 

In a commit message, or in a pull request/merge request description field,
identify the code assistant that you used, perhaps elaborating on how it was
used. You may wish to use a trailer like “Assisted-by:” or “Generated-by:”. For
example:

```
Assisted-by: <name of code assistant>
```

In a source file comment, indicate the use of the code assistant. For example:

```
Generated by: <name of code assistant>
```

### Copyright and licence notices

If the contents of an entire file or files in PR were substantially generated
by a code assistant with little to no creative input or modification by you
(which should typically not be the case), copyright protection may be limited,
but it is particularly appropriate to mark the contents of the file as
recommended above.

## Automation

### Pre-commit hook settings

It is possible to run formatters and linters automatically for all commits. You just need
to copy file `hooks/pre-commit` into subdirectory `.git/hooks/`. It must be done manually
because the copied file is an executable script (so from GIT point of view it is unsafe
to enable it automatically).


## Code coverage measurement

During testing, code coverage is measured. If the coverage is below the defined threshold (see `pyproject.toml` settings for actual value stored in section `[tool.coverage.report]`), tests will fail. We measured and checked code coverage in order to be able to develop software with high quality.

Code coverage reports are generated in JSON and also in format compatible with [_JUnit_ test automation framework](https://junit.org/junit5/). It is also possible to start `make coverage-report` to generate code coverage reports in the form of interactive HTML pages. These pages are stored in the `htmlcov` subdirectory. Just open the index page from this subdirectory in your web browser.



## Linters

_Black_, _Ruff_, Pyright, _Pylint_, __Pydocstyle__, __Mypy__, and __Bandit__ tools are used as linters. There are a bunch of linter rules enabled for this repository. All of them are specified in `pyproject.toml`, such as in sections `[tool.ruff]` and `[tool.pylint."MESSAGES CONTROL"]`. Some specific rules can be disabled using `ignore` parameter (empty now).

### OpenAPI (Spectral)

OpenAPI is linted with [Spectral](https://stoplight.io/open-api/) via **`npx --yes @stoplight/spectral-cli@6`** in the **`lint-openapi`** target (`make lint-openapi`, part of **`make verify`**). If **`npx`** is missing, **`lint-openapi`** skips Spectral locally; install **Node.js** to run it (see [Prerequisites](#prerequisites) and [Tooling installation](#tooling-installation)). **CI** always runs the Spectral step. If you introduce a **new** router tag (`APIRouter(tags=[...])`), you must also extend the global tag list in `src/app/main.py` and regenerate `docs/openapi.json`. See **[docs/contributing/openapi-tags-and-spectral.md](docs/contributing/openapi-tags-and-spectral.md)**.


### Type hints checks

It is possible to check if type hints added into the code are correct and whether assignments, function calls etc. use values of the right type. This check is invoked by following command:

```
make check-types
```

Please note that type hints check might be very slow on the first run.
Subsequent runs are much faster thanks to the cache that Mypy uses. This check
is part of a CI job that verifies sources.


### Ruff

List of all _Ruff_ rules recognized by Ruff can be retrieved by:


```
ruff linter
```

Description of all _Ruff_ rules are available on https://docs.astral.sh/ruff/rules/

Ruff rules can be disabled in source code (for a given line or block) by using a special `noqa` comment line. For example:

```python
# noqa: E501
```

### Pylint

List of all _Pylint_ rules can be retrieved by:

```
pylint --list-msgs
```

Description of all rules are available on https://pylint.readthedocs.io/en/latest/user_guide/checkers/features.html

To disable _Pylint_ rule in source code, the comment line in following format can be used:

```python
# pylint: disable=C0415
```



### Security checks

Static security check is performed by _Bandit_ tool. The check can be started by using:

```
make security-check
```



## Code style

### Function Standards

#### Documentation

All functions require docstrings with brief descriptions

#### Type annotations

Use complete type annotations for parameters and return types

- Use `typing_extensions.Self` for model validators
- Union types: `str | int` (modern syntax)
- Optional: `Optional[Type]`

#### Naming conventions

Use snake_case with descriptive, action-oriented names (get_, validate_, check_)

#### Async functions

Use `async def` for I/O operations and external API calls

#### Error handling

- Use FastAPI `HTTPException` with appropriate status codes for API endpoints
- Handle `APIConnectionError` from Llama Stack where appropriate

### Formatting rules

Code formatting rules are checked by __Black__. More info can be found on [https://black.readthedocs.io/en/stable/](https://black.readthedocs.io/en/stable/).

### Docstrings style
We are using [Google's docstring style](https://google.github.io/styleguide/pyguide.html).

Here is simple example:
```python
def function_with_pep484_type_annotations(param1: int, param2: str) -> bool:
    """Example function with PEP 484 type annotations.
    
    Args:
        param1: The first parameter.
        param2: The second parameter.
    
    Returns:
        The return value. True for success, False otherwise.
    
    Raises:
        ValueError: If the first parameter does not contain proper model name
    """
```

For further guidance, see the rest of our codebase, or check sources online. There are many, e.g. [this one](https://gist.github.com/redlotus/3bc387c2591e3e908c9b63b97b11d24e).


