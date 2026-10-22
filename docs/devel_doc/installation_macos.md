# Lightspeed Core Stack installation on macOS

## Prerequisites

- brew
- git
- Python 3.12 or 3.13
- pip

## Installation steps

1. `brew install uv`
1. `uv --version` -- should return no error
1. Clone the repo to the current dir:
`git clone https://github.com/lightspeed-core/lightspeed-stack`
1. `cd lightspeed-stack`
1. `uv sync`
1. (Optional) If you plan to use OpenTelemetry tracing with in-process PII redaction:
   `uv run python -m spacy download en_core_web_lg`
