# Lightspeed Core Stack Development Guide

## Project Overview
Lightspeed Core Stack (LCS) is an AI-powered assistant built on FastAPI that provides answers using LLM services, agents, and RAG databases. It integrates with Llama Stack for AI operations.

## Development Environment
- **Python**: Check `pyproject.toml` for supported Python versions
- **Package Manager**: uv (use `uv run` for all commands)
- **Required Commands**:
  - `uv run make format` - Format code (black + ruff)
  - `uv run make verify` - Run all linters (black, pylint, pyright, ruff, docstyle, check-types)

## Code Architecture & Patterns

### Project Structure
```
src/
├── app/                    # FastAPI application
│   ├── endpoints/         # REST API endpoints
│   └── main.py           # Application entry point
├── auth/                  # Authentication modules (k8s, jwk, noop)
├── authorization/         # Authorization middleware & resolvers
├── models/               # Pydantic models
│   ├── config.py         # Configuration classes
│   ├── requests.py       # Request models
│   └── responses.py      # Response models
├── utils/                # Utility functions
├── client.py             # Llama Stack client wrapper
└── configuration.py      # Config management
```

### Coding Standards

#### Imports & Dependencies
- Use absolute imports for internal modules: `from auth import get_auth_dependency`
- FastAPI dependencies: `from fastapi import APIRouter, HTTPException, Request, status, Depends`
- Llama Stack imports: `from llama_stack_client import AsyncLlamaStackClient`
- **ALWAYS** check `pyproject.toml` for existing dependencies before adding new ones
- **ALWAYS** verify current library versions in `pyproject.toml` rather than assuming versions

#### Module Standards
- All modules start with descriptive docstrings explaining purpose
- Use `logger = logging.getLogger(__name__)` pattern for module logging
- Package `__init__.py` files contain brief package descriptions
- Central `constants.py` for shared constants with descriptive comments
- Type aliases defined at module level for clarity

#### Configuration
- All config uses Pydantic models extending `ConfigurationBase`
- Base class sets `extra="forbid"` to reject unknown fields
- Use `@field_validator` and `@model_validator` for custom validation
- Type hints: `Optional[FilePath]`, `PositiveInt`, `SecretStr`

#### Function Standards
- **Documentation**: All functions require docstrings with brief descriptions
- **Type Annotations**: Complete type annotations for parameters and return types
  - Use `typing_extensions.Self` for model validators
  - Union types: `str | int` (modern syntax)
  - Optional: `Optional[Type]` or `Type | None`
- **Naming**: Use snake_case with descriptive, action-oriented names (get_, validate_, check_)
- **Return Values**: **CRITICAL** - Avoid in-place parameter modification anti-patterns:
  ```python
  # ❌ BAD: Modifying parameter in-place
  def process_data(input_data: Any, result_dict: dict) -> None:
      result_dict[key] = value  # Anti-pattern

  # ✅ GOOD: Return new data structure
  def process_data(input_data: Any) -> dict:
      result_dict = {}
      result_dict[key] = value
      return result_dict
  ```
- **Async Functions**: Use `async def` for I/O operations and external API calls
- **Error Handling**: 
  - Use FastAPI `HTTPException` with appropriate status codes for API endpoints
  - Handle `APIConnectionError` from Llama Stack

#### Logging Standards
- Use `import logging` and module logger pattern: `logger = logging.getLogger(__name__)`
- Standard log levels with clear purposes:
  - `logger.debug()` - Detailed diagnostic information
  - `logger.info()` - General information about program execution
  - `logger.warning()` - Something unexpected happened or potential problems
  - `logger.error()` - Serious problems that prevented function execution

#### Class Standards
- **Documentation**: All classes require descriptive docstrings explaining purpose
- **Naming**: Use PascalCase with descriptive names and standard suffixes:
  - `Configuration` for config classes
  - `Error`/`Exception` for custom exceptions  
  - `Resolver` for strategy pattern implementations
  - `Interface` for abstract base classes
- **Pydantic Models**: Extend `ConfigurationBase` for config, `BaseModel` for data models
- **Abstract Classes**: Use ABC for interfaces with `@abstractmethod` decorators
- **Validation**: Use `@model_validator` and `@field_validator` for Pydantic models
- **Type Hints**: Complete type annotations for all class attributes

#### Docstring Standards
- Follow Google Python docstring conventions: https://google.github.io/styleguide/pyguide.html
- Required for all modules, classes, and functions
- Include brief description and detailed sections as needed:
  - `Args:` for function parameters
  - `Returns:` for return values
  - `Raises:` for exceptions that may be raised
  - `Attributes:` for class attributes (Pydantic models)


## Testing Framework

### Test Structure
```
tests/
├── unit/                 # Unit tests (pytest)
├── integration/          # Integration tests
└── e2e/                 # End-to-end tests (behave)
    └── features/        # Gherkin feature files
```

### Testing Framework Requirements
- **Required**: Use pytest for all unit and integration tests
- **Forbidden**: Do not use unittest - pytest is the standard for this project
- **E2E Tests**: Use behave (BDD) framework for end-to-end testing

### Unit Tests (pytest)
- **Fixtures**: Use `conftest.py` for shared fixtures
- **Mocking**: `pytest-mock` for AsyncMock objects
- **Common Pattern**: 
  ```python
  @pytest.fixture(name="prepare_agent_mocks")
  def prepare_agent_mocks_fixture(mocker):
      mock_client = mocker.AsyncMock()
      mock_agent = mocker.AsyncMock()
      mock_agent._agent_id = "test_agent_id"
      return mock_client, mock_agent
  ```
- **Auth Mock**: `MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")`
- **Coverage**: Unit tests require 60% coverage, integration 10%

### E2E Tests (behave)
- **Framework**: Behave (BDD) with Gherkin feature files
- **Step Definitions**: In `tests/e2e/features/steps/`
- **Common Steps**: Service status, authentication, HTTP requests
- **Test List**: Maintained in `tests/e2e/test_list.txt`

### Test Commands
```bash
uv run make test-unit        # Unit tests with coverage
uv run make test-integration # Integration tests  
uv run make test-e2e        # End-to-end tests
```

## Quality Assurance

### Required Before Completion
1. `uv run make format` - Auto-format code
2. `uv run make verify` - Run all linters
3. Create unit tests for new code
4. Ensure tests pass

### Linting Tools
- **black**: Code formatting
- **pylint**: Static analysis (`source-roots = "src"`)
- **pyright**: Type checking (excludes `src/auth/k8s.py`)
- **ruff**: Fast linter
- **pydocstyle**: Docstring style
- **mypy**: Additional type checking

### Security
- **bandit**: Security issue detection
- Never commit secrets/keys
- Use environment variables for sensitive data

## Key Dependencies
**IMPORTANT**: Always check `pyproject.toml` for current versions rather than relying on this list:
- **FastAPI**: Web framework
- **Llama Stack**: AI integration
- **Pydantic**: Data validation/serialization
- **SQLAlchemy**: Database ORM
- **Kubernetes**: K8s auth integration

## Development Workflow
1. Use `uv sync --group dev --group llslibdev` for dependencies
2. Always use `uv run` prefix for commands
3. **ALWAYS** check `pyproject.toml` for existing dependencies and versions before adding new ones
4. Follow existing code patterns in the module you're modifying
5. Write unit tests covering new functionality
6. Run format and verify before completion