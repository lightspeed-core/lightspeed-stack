ARTIFACT_DIR := $(if $(ARTIFACT_DIR),$(ARTIFACT_DIR),tests/test_results)
PATH_TO_PLANTUML := ~/bin

# Variable to filter tests whose names or parent class names match a
# given (case-insensitive) expression. Logical operators like or, and,
# and not are allowed.
# For example, to run tests that matches the word "endpoint", do:
# $ make test-unit TEST_FILTER=endpoint
# To run tests that matches the work "endpoint" and "utils" do:
# $ make test-unit TEST_FILTER="endpoint or utils"
TEST_FILTER :=

run: ## Run the service locally
	uv run src/lightspeed_stack.py

test-unit: ## Run the unit tests
	@echo "Running unit tests..."
ifneq ($(strip $(TEST_FILTER)),)
	@echo "Filtering unit tests with names matching: \"$(TEST_FILTER)\""
	uv run pytest -k "$(TEST_FILTER)" tests/unit
else
	@echo "Reports will be written to ${ARTIFACT_DIR}"
	COVERAGE_FILE="${ARTIFACT_DIR}/.coverage.unit" uv run pytest tests/unit --cov=src --cov-report term-missing --cov-report "json:${ARTIFACT_DIR}/coverage_unit.json" --junit-xml="${ARTIFACT_DIR}/junit_unit.xml" --cov-fail-under=60
endif

test-integration: ## Run integration tests tests
	@echo "Running integration tests..."
ifneq ($(strip $(TEST_FILTER)),)
	@echo "Filtering integration tests with names matching: \"$(TEST_FILTER)\""
	uv run pytest -k "$(TEST_FILTER)" tests/integration
else
	@echo "Reports will be written to ${ARTIFACT_DIR}"
	COVERAGE_FILE="${ARTIFACT_DIR}/.coverage.integration" uv run pytest tests/integration --cov=src --cov-report term-missing --cov-report "json:${ARTIFACT_DIR}/coverage_integration.json" --junit-xml="${ARTIFACT_DIR}/junit_integration.xml" --cov-fail-under=10
endif

test-e2e: ## Run BDD tests for the service
	PYTHONDONTWRITEBYTECODE=1 uv run behave --tags=-skip -D dump_errors=true @tests/e2e/test_list.txt \

check-types: ## Checks type hints in sources
	uv run mypy --explicit-package-bases --disallow-untyped-calls --disallow-untyped-defs --disallow-incomplete-defs --ignore-missing-imports --disable-error-code attr-defined src/

security-check: ## Check the project for security issues
	bandit -c pyproject.toml -r src tests

format: ## Format the code into unified format
	uv run black .
	uv run ruff check . --fix

schema:	## Generate OpenAPI schema file
	uv run scripts/generate_openapi_schema.py docs/openapi.json

# TODO uv migration
requirements.txt:	pyproject.toml pdm.lock ## Generate requirements.txt file containing hashes for all non-devel packages
	pdm export --prod --format requirements --output requirements.txt --no-extras --without evaluation

docs/config.puml:	src/models/config.py ## Generate PlantUML class diagram for configuration
	pyreverse src/models/config.py --output puml --output-directory=docs/
	mv docs/classes.puml docs/config.puml

docs/config.png:	docs/config.puml ## Generate an image with configuration graph
	pushd docs && \
	java -jar ${PATH_TO_PLANTUML}/plantuml.jar --theme rose config.puml && \
	mv classes.png config.png && \
	popd

shellcheck: ## Run shellcheck
	wget -qO- "https://github.com/koalaman/shellcheck/releases/download/stable/shellcheck-stable.linux.x86_64.tar.xz" | tar -xJv \
	shellcheck --version
	shellcheck -- */*.sh

black:
	uv run black --check .

pylint:
	uv run pylint src

pyright:
	uv run pyright src

docstyle:
	uv run pydocstyle -v src

ruff:
	uv run ruff check . --per-file-ignores=tests/*:S101 --per-file-ignores=scripts/*:S101

verify:
	$(MAKE) black
	$(MAKE) pylint
	$(MAKE) pyright
	$(MAKE) ruff
	$(MAKE) docstyle
	$(MAKE) check-types

help: ## Show this help screen
	@echo 'Usage: make <OPTIONS> ... <TARGETS>'
	@echo ''
	@echo 'Available targets are:'
	@echo ''
	@grep -E '^[ a-zA-Z0-9_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-33s\033[0m %s\n", $$1, $$2}'
	@echo ''
