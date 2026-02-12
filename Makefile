SHELL := /bin/bash

ARTIFACT_DIR := $(if $(ARTIFACT_DIR),$(ARTIFACT_DIR),tests/test_results)
PATH_TO_PLANTUML := ~/bin

# Python registry to where the package should be uploaded
PYTHON_REGISTRY = pypi

# PyTorch version
TORCH_VERSION := 2.9.0


# Default configuration files (override with: make run CONFIG=myconfig.yaml)
CONFIG ?= lightspeed-stack.yaml
LLAMA_STACK_CONFIG ?= run.yaml

run: ## Run the service locally
	uv run src/lightspeed_stack.py -c $(CONFIG)

run-llama-stack: ## Start Llama Stack with enriched config (for local service mode)
	uv run src/llama_stack_configuration.py -c $(CONFIG) -i $(LLAMA_STACK_CONFIG) -o $(LLAMA_STACK_CONFIG) && \
	AZURE_API_KEY=$$(grep '^AZURE_API_KEY=' .env | cut -d'=' -f2-) \
	uv run llama stack run $(LLAMA_STACK_CONFIG)

test-unit: ## Run the unit tests
	@echo "Running unit tests..."
	@echo "Reports will be written to ${ARTIFACT_DIR}"
	COVERAGE_FILE="${ARTIFACT_DIR}/.coverage.unit" uv run python -m pytest tests/unit --cov=src --cov-report term-missing --cov-report "json:${ARTIFACT_DIR}/coverage_unit.json" --junit-xml="${ARTIFACT_DIR}/junit_unit.xml" --cov-fail-under=60

test-integration: ## Run integration tests tests
	@echo "Running integration tests..."
	@echo "Reports will be written to ${ARTIFACT_DIR}"
	COVERAGE_FILE="${ARTIFACT_DIR}/.coverage.integration" uv run python -m pytest tests/integration --cov=src --cov-report term-missing --cov-report "json:${ARTIFACT_DIR}/coverage_integration.json" --junit-xml="${ARTIFACT_DIR}/junit_integration.xml" --cov-fail-under=10

test-e2e: ## Run end to end tests for the service
	script -q -e -c "uv run behave --color --format pretty --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt"

test-e2e-local: ## Run end to end tests for the service
	uv run behave --color --format pretty --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt

benchmarks: ## Run benchmarks
	uv run python -m pytest -vv tests/benchmarks/

check-types: ## Checks type hints in sources
	uv run mypy --explicit-package-bases --disallow-untyped-calls --disallow-untyped-defs --disallow-incomplete-defs --ignore-missing-imports --disable-error-code attr-defined src/ tests/unit tests/integration tests/e2e/ dev-tools/

security-check: ## Check the project for security issues
	uv run bandit -c pyproject.toml -r src tests dev-tools

format: ## Format the code into unified format
	uv run black .
	uv run ruff check . --fix

schema:	## Generate OpenAPI schema file
	uv run scripts/generate_openapi_schema.py docs/openapi.json

openapi-doc:	docs/openapi.json scripts/fix_openapi_doc.py	## Generate OpenAPI documentation
	openapi-to-markdown --input_file docs/openapi.json --output_file output.md
	python3 scripts/fix_openapi_doc.py <  output.md > docs/openapi.md
	rm output.md

# TODO uv migration
requirements.txt:	pyproject.toml pdm.lock ## Generate requirements.txt file containing hashes for all non-devel packages
	pdm export --prod --format requirements --output requirements.txt --no-extras --without evaluation

docs-build:	## Build MkDocs documentation site
	uv run mkdocs build

docs-serve:	## Serve MkDocs documentation locally with hot-reload
	uv run mkdocs serve

docs-readmes:	## Generate README.md files in source directories
	uv run scripts/gen_doc.py

docs/config.puml:	src/models/config.py ## Generate PlantUML class diagram for configuration
	pyreverse src/models/config.py --output puml --output-directory=docs/
	mv docs/classes.puml docs/config.puml

docs/config.png:	docs/config.puml ## Generate an image with configuration graph
	pushd docs && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar --theme rose config.puml && \
	mv classes.png config.png && \
	popd

docs/config.svg:	docs/config.puml ## Generate an SVG with configuration graph
	pushd docs && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar --theme rose config.puml -tsvg && \
	xmllint --format classes.svg > config.svg && \
	rm classes.svg && \
	popd

shellcheck: ## Run shellcheck
	wget -qO- "https://github.com/koalaman/shellcheck/releases/download/stable/shellcheck-stable.linux.x86_64.tar.xz" | tar -xJv \
	shellcheck --version
	shellcheck -- */*.sh

black:	## Check source code using Black code formatter
	uv run black --check .

pylint:	## Check source code using Pylint static code analyser
	uv run pylint src tests dev-tools

pyright:	## Check source code using Pyright static type checker
	uv run pyright src dev-tools

docstyle:	## Check the docstring style using Docstyle checker
	uv run pydocstyle -v src dev-tools

ruff:	## Check source code using Ruff linter
	uv run ruff check . --per-file-ignores=tests/*:S101 --per-file-ignores=scripts/*:S101

verify:	## Run all linters
	$(MAKE) black
	$(MAKE) pylint
	$(MAKE) pyright
	$(MAKE) ruff
	$(MAKE) docstyle
	$(MAKE) check-types

distribution-archives:	## Generate distribution archives to be uploaded into Python registry
	rm -rf dist
	uv run python -m build

upload-distribution-archives:	## Upload distribution archives into Python registry
	uv run python -m twine upload --repository ${PYTHON_REGISTRY} dist/*

konflux-requirements:	## generate hermetic requirements.*.txt file for konflux build
	./scripts/konflux_requirements.sh

konflux-rpm-lock:	## generate rpm.lock.yaml file for konflux build
	./scripts/generate-rpm-lock.sh

help: ## Show this help screen
	@echo 'Usage: make <OPTIONS> ... <TARGETS>'
	@echo ''
	@echo 'Available targets are:'
	@echo ''
	@grep -E '^[ a-zA-Z0-9_./-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-33s\033[0m %s\n", $$1, $$2}'
	@echo ''
