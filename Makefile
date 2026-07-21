SHELL := /bin/bash

ARTIFACT_DIR := $(if $(ARTIFACT_DIR),$(ARTIFACT_DIR),tests/test_results)
PATH_TO_PLANTUML := ~/bin

# Python registry to where the package should be uploaded
PYTHON_REGISTRY = pypi


# Default configuration files (override with: make run CONFIG=myconfig.yaml)
CONFIG ?= lightspeed-stack.yaml
LLAMA_STACK_CONFIG ?= run.yaml

# Container configuration
LLAMA_STACK_CONTAINER_NAME ?= lightspeed-llama-stack
LLAMA_STACK_IMAGE ?= lightspeed-llama-stack:local
LLAMA_STACK_PORT ?= 8321
CONTAINER_RUNTIME ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)

.PHONY: run run-stack build-llama-stack-image remove-llama-stack-container stop-llama-stack-container start-llama-stack-container wait-for-llama-stack-health clean-llama-stack

run-stack: ## Run lightspeed-stack directly, without building dependent service/s
	uv run src/lightspeed_stack.py -c $(CONFIG)

run: start-llama-stack-container ## Run the service locally with dependent services
	@echo "Starting Lightspeed Core Stack..."
	@trap 'echo ""; echo "Stopping services..."; $(MAKE) stop-llama-stack-container' EXIT INT TERM; \
	$(MAKE) run-stack

build-llama-stack-image: remove-llama-stack-container ## Build llama-stack container image
	@echo "Building llama-stack container image..."
	@if [ -z "$(CONTAINER_RUNTIME)" ]; then \
		echo "ERROR: No container runtime found. Install podman or docker."; \
		exit 1; \
	fi
	$(CONTAINER_RUNTIME) build -f deploy/llama-stack/test.containerfile -t $(LLAMA_STACK_IMAGE) .

stop-llama-stack-container: ## Gracefully stop llama-stack container
	@if [ -n "$(CONTAINER_RUNTIME)" ] && $(CONTAINER_RUNTIME) inspect $(LLAMA_STACK_CONTAINER_NAME) >/dev/null 2>&1; then \
		echo "Stopping llama-stack container (timeout: 10s)..."; \
		if $(CONTAINER_RUNTIME) stop -t 10 $(LLAMA_STACK_CONTAINER_NAME) 2>/dev/null; then \
			echo "✓ Container stopped gracefully"; \
		else \
			echo "⚠ Container did not stop gracefully, capturing logs..."; \
			$(CONTAINER_RUNTIME) logs $(LLAMA_STACK_CONTAINER_NAME) > /tmp/llama-stack-failure.log 2>&1 || true; \
			echo "Logs saved to /tmp/llama-stack-failure.log"; \
			$(CONTAINER_RUNTIME) kill $(LLAMA_STACK_CONTAINER_NAME) 2>/dev/null || true; \
		fi; \
	fi

remove-llama-stack-container: ## Remove llama-stack container (saves logs first)
	@if [ -n "$(CONTAINER_RUNTIME)" ] && $(CONTAINER_RUNTIME) inspect $(LLAMA_STACK_CONTAINER_NAME) >/dev/null 2>&1; then \
		echo "Saving container logs before removal..."; \
		$(CONTAINER_RUNTIME) logs $(LLAMA_STACK_CONTAINER_NAME) > /tmp/llama-stack-last-run.log 2>&1 || true; \
		echo "Removing llama-stack container..."; \
		$(CONTAINER_RUNTIME) rm -f $(LLAMA_STACK_CONTAINER_NAME); \
		echo "✓ Container removed (logs saved to /tmp/llama-stack-last-run.log)"; \
	fi

start-llama-stack-container: build-llama-stack-image ## Start llama-stack container
	@echo "Starting llama-stack container..."
	$(CONTAINER_RUNTIME) run -d \
		--name $(LLAMA_STACK_CONTAINER_NAME) \
		-p $(LLAMA_STACK_PORT):8321 \
		--health-cmd "curl -f http://localhost:8321/v1/health || exit 1" \
		--health-interval 10s \
		--health-timeout 5s \
		--health-retries 3 \
		--health-start-period 15s \
		-v $(PWD)/$(LLAMA_STACK_CONFIG):/opt/app-root/run.yaml:z \
		-v $(PWD)/$(CONFIG):/opt/app-root/lightspeed-stack.yaml:ro,z \
		-v $(PWD)/scripts/llama-stack-entrypoint.sh:/opt/app-root/enrich-entrypoint.sh:ro,z \
		-v $(PWD)/src/llama_stack_configuration.py:/opt/app-root/llama_stack_configuration.py:ro,z \
		-e OPENAI_API_KEY \
		-e BRAVE_SEARCH_API_KEY \
		-e TAVILY_SEARCH_API_KEY \
		-e E2E_OPENAI_MODEL=$${E2E_OPENAI_MODEL:-gpt-4o-mini} \
		-e TENANT_ID=$${TENANT_ID:-} \
		-e CLIENT_ID=$${CLIENT_ID:-} \
		-e CLIENT_SECRET \
		-e RHAIIS_URL=$${RHAIIS_URL:-} \
		-e RHAIIS_PORT=$${RHAIIS_PORT:-} \
		-e RHAIIS_API_KEY \
		-e RHAIIS_MODEL=$${RHAIIS_MODEL:-} \
		-e RHEL_AI_URL=$${RHEL_AI_URL:-} \
		-e RHEL_AI_PORT=$${RHEL_AI_PORT:-} \
		-e RHEL_AI_API_KEY \
		-e RHEL_AI_MODEL=$${RHEL_AI_MODEL:-} \
		-e GOOGLE_APPLICATION_CREDENTIALS \
		-e VERTEX_AI_PROJECT=$${VERTEX_AI_PROJECT:-} \
		-e VERTEX_AI_LOCATION=$${VERTEX_AI_LOCATION:-} \
		-e WATSONX_BASE_URL=$${WATSONX_BASE_URL:-} \
		-e WATSONX_PROJECT_ID=$${WATSONX_PROJECT_ID:-} \
		-e WATSONX_API_KEY \
		-e LITELLM_DROP_PARAMS=true \
		-e AWS_BEARER_TOKEN_BEDROCK \
		-e LLAMA_STACK_LOGGING=$${LLAMA_STACK_LOGGING:-} \
		-e FAISS_VECTOR_STORE_ID=$${FAISS_VECTOR_STORE_ID:-} \
		-e RH_SERVER_OKP \
		-e SOLR_URL \
		-e SOLR_COLLECTION \
		-e SOLR_VECTOR_FIELD \
		-e SOLR_CONTENT_FIELD \
		-e SOLR_EMBEDDING_MODEL \
		-e SOLR_EMBEDDING_DIM \
		$(LLAMA_STACK_IMAGE)
	@$(MAKE) wait-for-llama-stack-health

wait-for-llama-stack-health: ## Wait for llama-stack container to be healthy
	@echo "Waiting for llama-stack container to be healthy..."
	@for i in {1..30}; do \
		STATUS=$$($(CONTAINER_RUNTIME) inspect --format='{{.State.Health.Status}}' $(LLAMA_STACK_CONTAINER_NAME) 2>/dev/null || echo "no-healthcheck"); \
		if [ "$$STATUS" = "healthy" ]; then \
			echo "✓ Llama-stack is healthy and ready!"; \
			exit 0; \
		fi; \
		echo "  Health status: $$STATUS (attempt $$i/30)"; \
		sleep 2; \
	done; \
	echo "✗ ERROR: Llama-stack did not become healthy within 60 seconds"; \
	echo "Container logs:"; \
	$(CONTAINER_RUNTIME) logs $(LLAMA_STACK_CONTAINER_NAME); \
	exit 1

clean-llama-stack: remove-llama-stack-container ## Remove container and image
	@if [ -n "$(CONTAINER_RUNTIME)" ] && $(CONTAINER_RUNTIME) images -q $(LLAMA_STACK_IMAGE) | grep -q .; then \
		echo "Removing llama-stack image..."; \
		$(CONTAINER_RUNTIME) rmi $(LLAMA_STACK_IMAGE); \
	fi

run-llama-stack: ## Start Llama Stack with enriched config (for local service mode)
	uv run src/llama_stack_configuration.py -c $(CONFIG) -i $(LLAMA_STACK_CONFIG) -o $(LLAMA_STACK_CONFIG) && \
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

test-e2e-local: ## Run end to end tests for the service (no script wrapper)
	uv run behave --color --format pretty --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt

# Tag-based subsets (@e2e_group_* on feature files). Default runs all groups; override for one shard, e.g.
#   E2E_BEHAVE_TAG_EXPR='not @skip and @e2e_group_2' make test-e2e-tagged-local
E2E_BEHAVE_TAG_EXPR ?= not @skip and (e2e_group_1 or e2e_group_2 or e2e_group_3)

test-e2e-tagged: ## Run e2e tests with E2E_BEHAVE_TAG_EXPR (default: all @e2e_group_*)
	script -q -e -c "uv run behave --color --format pretty --tags=\"$(E2E_BEHAVE_TAG_EXPR)\" -D dump_errors=true @tests/e2e/test_list.txt"

test-e2e-tagged-local: ## Same as test-e2e-tagged without script wrapper
	uv run behave --color --format pretty --tags="$(E2E_BEHAVE_TAG_EXPR)" -D dump_errors=true @tests/e2e/test_list.txt

benchmarks: ## Run benchmarks
	uv run python -m pytest -vv tests/benchmarks/

check-types-src: ## Check type hints in sources only
	uv run mypy -n10 --explicit-package-bases --disallow-untyped-calls --disallow-untyped-defs --disallow-incomplete-defs --ignore-missing-imports --disable-error-code attr-defined src/

check-types-tests: ## Check type hints in tests only
	uv run mypy -n10 --explicit-package-bases --disallow-untyped-calls --disallow-untyped-defs --disallow-incomplete-defs --ignore-missing-imports --disable-error-code attr-defined tests/unit tests/integration tests/e2e/

check-types:	check-types-src check-types-tests ## Checks type hints in sources and tests

security-check: ## Check the project for security issues
	uv run bandit -c pyproject.toml -r src tests

format: ## Format the code into unified format
	uv run black --line-length 88 src tests
	uv run ruff check src tests --fix

schema:	## Generate OpenAPI schema file stored in docs subdirectory
	uv run scripts/generate_openapi_schema.py docs/openapi.json

openapi-doc:	docs/openapi.json scripts/fix_openapi_doc.py	## Generate OpenAPI documentation
	openapi-to-markdown --input_file docs/openapi.json --output_file output.md
	# LCORE-1494: don't overwrite the original docs/output.md for now
	python3 scripts/fix_openapi_doc.py < output.md > openapi2.md
	rm output.md

generate-documentation:	devel-doc	## Generate or regenerated content of the whole /docs subdirectory

doc:	devel-doc	## Generate or regenerated content of the whole /docs subdirectory

devel-doc:	## Generate documentation for developers
	scripts/gen_doc.py

docs/models:	docs/models/requests.puml docs/models/responses.puml docs/models/database.puml docs/models/common.puml	## Generate documentation about models

docs/models/requests.puml: ## Generate PlantUML class diagram for requests data models
	uv run pyreverse src/models/api/requests/ --output puml --output-directory=docs/models/
	mv docs/models/classes.puml docs/models/requests.puml

docs/models/responses.puml: ## Generate PlantUML class diagram for responses data models
	uv run pyreverse src/models/api/responses/ --output puml --output-directory=docs/models/
	mv docs/models/classes.puml docs/models/responses.puml

docs/models/common.puml: ## Generate PlantUML class diagram for common data models
	uv run pyreverse src/models/common/ --output puml --output-directory=docs/models/
	mv docs/models/classes.puml docs/models/common.puml

docs/models/database.puml: ## Generate PlantUML class diagram for database data models
	uv run pyreverse src/models/database/ --output puml --output-directory=docs/models/
	mv docs/models/classes.puml docs/models/database.puml

docs/models/requests.svg:	docs/models/requests.puml	## Generate an SVG with requests data models
	pushd docs/models && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar requests.puml -tsvg && \
	xmllint --format classes.svg > requests.svg && \
	rm -f classes.svg && \
	popd

docs/models/responses.svg:	docs/models/responses.puml	## Generate an SVG with responses data models
	pushd docs/models && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar responses.puml -tsvg && \
	xmllint --format classes.svg > responses.svg && \
	rm -f classes.svg && \
	popd

docs/models/common.svg:	docs/models/common.puml	## Generate an SVG with common data models
	pushd docs/models && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar common.puml -tsvg && \
	xmllint --format classes.svg > common.svg && \
	rm -f classes.svg && \
	popd

docs/models/database.svg:	docs/models/database.puml	## Generate a SVG with database data models
	pushd docs/models && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar database.puml -tsvg && \
	xmllint --format classes.svg > database.svg && \
	rm -f classes.svg && \
	popd

docs/config.puml:	src/models/config.py ## Generate PlantUML class diagram for configuration
	uv run pyreverse src/models/config.py --output puml --output-directory=docs/
	mv docs/classes.puml docs/config.puml

# Omit --theme rose on the CLI: it fails with some plantuml.jar builds on pyreverse output.
# To use rose, add a line after @startuml: !theme rose  (requires a recent JAR).
# PNG is capped at 4096px per side by default; pyreverse class diagrams are often wider—raise the limit.
docs/config.png:	docs/config.puml ## Generate an image with configuration graph
	pushd docs && \
	java -DPLANTUML_LIMIT_SIZE=16384 -jar ${PATH_TO_PLANTUML}/plantuml.jar config.puml && \
	mv classes.png config.png && \
	popd

docs/config.svg:	docs/config.puml ## Generate an SVG with configuration graph
	pushd docs && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar config.puml -tsvg && \
	xmllint --format classes.svg > config.svg && \
	rm -f classes.svg && \
	popd

shellcheck: ## Run shellcheck
	wget -qO- "https://github.com/koalaman/shellcheck/releases/download/stable/shellcheck-stable.linux.x86_64.tar.xz" | tar -xJv \
	shellcheck --version
	shellcheck -- */*.sh

black:	## Check source code using Black code formatter
	uv run black --check --line-length 88 src tests

pylint:	## Check source code using Pylint static code analyser
	uv run pylint src tests

pyright:	## Check source code using Pyright static type checker
	uv run pyright src

docstyle:	## Check the docstring style using Docstyle checker
	uv run pydocstyle -v src

ruff:	## Check source code using Ruff linter
	uv run ruff check src tests --per-file-ignores=tests/*:S101 --per-file-ignores=scripts/*:S101

lint-openapi: ## Lint docs/openapi.json (Spectral OAS ruleset; fail on error)
	@if command -v npx >/dev/null 2>&1; then \
		npx --yes @stoplight/spectral-cli@6 lint docs/openapi.json --fail-severity error --display-only-failures; \
	else \
		echo "lint-openapi: skipping Spectral (npx not found). Install Node.js for OpenAPI lint locally; CI still runs it."; \
	fi

verify:	## Run all linters
	$(MAKE) black
	$(MAKE) pylint
	$(MAKE) pyright
	$(MAKE) ruff
	$(MAKE) docstyle
	$(MAKE) check-types
	$(MAKE) lint-openapi

distribution-archives:	## Generate distribution archives to be uploaded into Python registry
	rm -rf dist
	uv run python -m build

upload-distribution-archives:	## Upload distribution archives into Python registry
	uv run python -m twine upload --repository ${PYTHON_REGISTRY} dist/*

konflux-requirements:	## Generate hermetic requirements.*.txt file for konflux build
	./scripts/konflux_requirements.sh

konflux-rpm-lock:	## Generate rpm.lock.yaml file for konflux build
	./scripts/generate-rpm-lock.sh

konflux-artifacts-lock: ## Regenerate artifacts.lock.yaml file for konflux build
	./scripts/generate-artifacts-lock.sh

help: ## Show this help screen
	@echo 'Usage: make <OPTIONS> ... <TARGETS>'
	@echo ''
	@echo 'Available targets are:'
	@echo ''
	@grep -E '^[ a-zA-Z0-9_./-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-33s\033[0m %s\n", $$1, $$2}'
	@echo ''
