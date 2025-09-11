# Lightspeed Core Stack Development Guide

## Project Overview
Lightspeed Core Stack (LCS) is an AI-powered assistant built on FastAPI that provides answers using LLM services, agents, and RAG databases. It integrates with Llama Stack for AI operations.

## Development Environment
- **Python**: 3.12-3.13 (3.14 not supported)
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
- Use relative imports within modules: `from auth import get_auth_dependency`
- FastAPI dependencies: `from fastapi import APIRouter, HTTPException, Request, status, Depends`
- Llama Stack imports: `from llama_stack_client import AsyncLlamaStackClient`
- Check existing dependencies in pyproject.toml before adding new ones

#### Configuration
- All config uses Pydantic models extending `ConfigurationBase`
- Base class sets `extra="forbid"` to reject unknown fields
- Use `@model_validator` for custom validation
- Type hints: `Optional[FilePath]`, `PositiveInt`, `SecretStr`

#### Function Design Principles
**CRITICAL**: Avoid in-place parameter modification anti-patterns:
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

#### Error Handling
- Use FastAPI `HTTPException` with appropriate status codes
- Handle `APIConnectionError` from Llama Stack
- Logging: `import logging` and use module logger

#### Type Hints
- Required for all function signatures
- Use `typing_extensions.Self` for model validators
- Union types: `str | int` (modern syntax)
- Optional: `Optional[Type]` or `Type | None`

## Testing Framework

### Test Structure
```
tests/
├── unit/                 # Unit tests (pytest)
├── integration/          # Integration tests
└── e2e/                 # End-to-end tests (behave)
    └── features/        # Gherkin feature files
```

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
- **FastAPI**: Web framework (`>=0.115.12`)
- **Llama Stack**: AI integration (`==0.2.19`)
- **Pydantic**: Data validation/serialization
- **SQLAlchemy**: Database ORM (`>=2.0.42`)
- **Kubernetes**: K8s auth integration (`>=30.1.0`)

## Development Workflow
1. Use `uv sync --group dev --group llslibdev` for dependencies
2. Always use `uv run` prefix for commands
3. Check pyproject.toml for existing dependencies before adding new ones
4. Follow existing code patterns in the module you're modifying
5. Write unit tests covering new functionality
6. Run format and verify before completion