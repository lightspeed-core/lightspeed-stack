# Integration Tests

This directory contains integration tests for Lightspeed Core Stack. Integration tests verify that multiple components work together correctly, using real implementations where possible and mocking only external dependencies.

## Table of Contents

- [Getting Started](#getting-started)
- [Common Fixtures](#common-fixtures)
- [Helper Functions](#helper-functions)
- [Test Constants](#test-constants)
- [Writing Integration Tests](#writing-integration-tests)
- [Running Tests](#running-tests)
- [Best Practices](#best-practices)

## Getting Started

Integration tests are located in subdirectories:
- `endpoints/` - Tests for REST API endpoints
- Other modules test specific components in isolation

All integration tests share common fixtures and helpers defined in `conftest.py`.

## Common Fixtures

These fixtures are automatically available to all integration tests via `conftest.py`:

### Core Fixtures

#### `test_config` (function-scoped)
Loads the real test configuration from `tests/configuration/lightspeed-stack.yaml`.

```python
def test_example(test_config: AppConfig) -> None:
    assert test_config.inference.default_provider == "test-provider"
```

#### `test_db_engine` (function-scoped)
Provides a fresh in-memory SQLite database engine for each test.

#### `test_db_session` (function-scoped)
Provides a database session connected to the test database.

#### `patch_db_session` (autouse, function-scoped)
Automatically patches `app.database.engine` and `app.database.session_local` to use the test database. This applies to ALL integration tests automatically.

#### `test_request` (function-scoped)
Creates a basic FastAPI Request object with proper HTTP scope.

#### `test_auth` (function-scoped)
Returns an AuthTuple from the real noop authentication module.

```python
async def test_example(test_auth: AuthTuple) -> None:
    user_id, username, is_system, token = test_auth
    assert user_id == "00000000-0000-0000-0000-000"
```

#### `mock_request_with_auth` (function-scoped)
Creates a Request object with all Action permissions granted. Useful for tests that need to bypass authorization.

```python
def test_example(mock_request_with_auth: Request) -> None:
    assert Action.DELETE_CONVERSATION in mock_request_with_auth.state.authorized_actions
```

### Mocking Fixtures

#### `mock_llama_stack_client` (function-scoped)
Mocks the external Llama Stack client with sensible defaults:
- Returns a mock response with "This is a test response about Ansible."
- Mocks `models.list`, `shields.list`, `vector_stores.list`
- Mocks `conversations.create` with proper conv_ format
- Can be customized in individual tests

```python
def test_example(mock_llama_stack_client: Any) -> None:
    # Customize the mock for this specific test
    mock_llama_stack_client.responses.create.return_value = custom_response
```

## Helper Functions

Helper functions in `conftest.py` make it easier to create common test objects:

### `create_mock_llm_response()`

Create a customizable mock LLM response:

```python
from tests.integration.conftest import create_mock_llm_response

def test_custom_response(mocker: MockerFixture) -> None:
    response = create_mock_llm_response(
        mocker,
        content="Custom response text",
        tool_calls=[...],
        refusal=None,  # Set to string for shield violations
        input_tokens=20,
        output_tokens=10,
    )
```

**Parameters:**
- `content` - Response text (default: "This is a test response about Ansible.")
- `tool_calls` - Optional list of tool calls
- `refusal` - Optional refusal message for shield violations
- `input_tokens` - Input token count (default: 10)
- `output_tokens` - Output token count (default: 5)

### `create_mock_vector_store_response()`

Create a mock vector store response for RAG testing:

```python
from tests.integration.conftest import create_mock_vector_store_response

def test_rag(mocker: MockerFixture) -> None:
    chunks = [
        {"text": "Chunk 1", "score": 0.95, "metadata": {"source": "doc1"}},
        {"text": "Chunk 2", "score": 0.85, "metadata": {"source": "doc2"}},
    ]
    response = create_mock_vector_store_response(mocker, chunks=chunks)
```

### `create_mock_tool_call()`

Create a mock tool call:

```python
from tests.integration.conftest import create_mock_tool_call

def test_tools(mocker: MockerFixture) -> None:
    tool_call = create_mock_tool_call(
        mocker,
        tool_name="search",
        arguments={"query": "test"},
        call_id="call-123",
    )
```

## Test Constants

Use these constants for consistent test data across integration tests:

```python
from tests.integration.conftest import (
    TEST_USER_ID,              # "00000000-0000-0000-0000-000"
    TEST_USERNAME,             # "lightspeed-user"
    TEST_CONVERSATION_ID,      # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    TEST_REQUEST_ID,           # "123e4567-e89b-12d3-a456-426614174000"
    TEST_OTHER_USER_ID,        # "11111111-1111-1111-1111-111111111111"
    TEST_NON_EXISTENT_ID,      # "00000000-0000-0000-0000-000000000001"
    TEST_MODEL,                # "test-provider/test-model"
    TEST_PROVIDER,             # "test-provider"
    TEST_MODEL_NAME,           # "test-model"
)
```

## Writing Integration Tests

### File Naming

Integration test files should be named `test_<component>_integration.py`:
- `test_query_integration.py` - Tests for query endpoints
- `test_streaming_query_integration.py` - Tests for streaming query
- `test_conversations_v1_integration.py` - Tests for v1 conversation endpoints

### Test Structure

```python
"""Integration tests for <component description>."""

# pylint: disable=too-many-arguments  # Integration tests need many fixtures
# pylint: disable=too-many-positional-arguments  # Integration tests need many fixtures

import pytest
from pytest_mock import MockerFixture

from app.endpoints.example import example_handler
from authentication.interface import AuthTuple
from configuration import AppConfig


@pytest.mark.asyncio
async def test_example_endpoint_success(
    test_config: AppConfig,
    mock_llama_stack_client: Any,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that example endpoint returns successful response.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - External dependencies are properly mocked
    - Response structure is correct

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
    """
    response = await example_handler(
        request=test_request,
        auth=test_auth,
    )

    assert response is not None
    # ... more assertions
```

### What to Test

Integration tests should verify:
1. **Component interaction** - Multiple components working together
2. **Real implementations** - Use actual database, config, authentication
3. **External mocks only** - Mock only external services (Llama Stack, external APIs)
4. **Error handling** - HTTP status codes, error messages
5. **Data flow** - Database persistence, cache updates, etc.

### What NOT to Test

- Low-level implementation details (use unit tests)
- Individual function logic (use unit tests)
- Every code branch (use unit tests)

## Running Tests

### Run all integration tests
```bash
uv run pytest tests/integration/ -v
```

### Run specific test file
```bash
uv run pytest tests/integration/endpoints/test_query_integration.py -v
```

### Run specific test
```bash
uv run pytest tests/integration/endpoints/test_query_integration.py::test_query_v2_endpoint_successful_response -v
```

### Run with coverage
```bash
uv run make test-integration
```

### Run with detailed output
```bash
uv run pytest tests/integration/ -v --tb=short
```

## Best Practices

### 1. Use Common Fixtures

Always use fixtures from `conftest.py` instead of creating your own:

```python
# ❌ BAD - Creating custom fixture
@pytest.fixture
def my_custom_client(mocker):
    # ... duplicate code

# ✅ GOOD - Using common fixture
def test_example(mock_llama_stack_client: Any):
    # Customize if needed
    mock_llama_stack_client.responses.create.return_value = custom_response
```

### 2. Use Test Constants

Use constants from `conftest.py` for consistency:

```python
# ❌ BAD - Magic strings
conversation_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# ✅ GOOD - Using constant
from tests.integration.conftest import TEST_CONVERSATION_ID
conversation_id = TEST_CONVERSATION_ID
```

### 3. Use Helper Functions

Use helper functions to reduce boilerplate:

```python
# ❌ BAD - Manually creating mocks
mock_response = mocker.MagicMock()
mock_response.output = [...]
# ... many lines of setup

# ✅ GOOD - Using helper
from tests.integration.conftest import create_mock_llm_response
mock_response = create_mock_llm_response(mocker, content="Custom text")
```

### 4. Clear Test Names

Test names should describe what they verify:

```python
# ❌ BAD
def test_query_1():

# ✅ GOOD
def test_query_v2_endpoint_returns_successful_response():
def test_query_v2_endpoint_handles_connection_error():
def test_query_v2_endpoint_validates_conversation_ownership():
```

### 5. Comprehensive Docstrings

Include what the test verifies and parameters:

```python
@pytest.mark.asyncio
async def test_example(
    test_config: AppConfig,
    mock_llama_stack_client: Any,
) -> None:
    """Test that example endpoint handles errors correctly.

    This integration test verifies:
    - Error handling when external service fails
    - Proper HTTP status code is returned
    - Error message is user-friendly

    Parameters:
        test_config: Test configuration
        mock_llama_stack_client: Mocked Llama Stack client
    """
```

### 6. Test One Thing

Each test should verify one specific behavior:

```python
# ❌ BAD - Testing multiple things
def test_endpoint():
    # Test success case
    # Test error case
    # Test edge case

# ✅ GOOD - Separate tests
def test_endpoint_success():
def test_endpoint_handles_error():
def test_endpoint_handles_edge_case():
```

### 7. Use Meaningful Assertions

```python
# ❌ BAD - Vague assertion
assert response

# ✅ GOOD - Specific assertions
assert response is not None
assert response.conversation_id == TEST_CONVERSATION_ID
assert "Ansible" in response.response
assert response.input_tokens == 10
```

### 8. Clean Up After Tests

The framework handles most cleanup automatically via fixtures. Only add explicit cleanup if needed:

```python
@pytest.fixture
def custom_resource():
    resource = setup_resource()
    yield resource
    # Cleanup happens here
    teardown_resource(resource)
```

## Troubleshooting

### Database Session Errors

If you see `RuntimeError: Database session not initialized`:
- The `patch_db_session` fixture is autouse, so this shouldn't happen
- Check that you're in the `tests/integration/` directory
- Verify conftest.py is being loaded

### Import Errors

If you see `ModuleNotFoundError`:
- Ensure you're running tests with `uv run pytest`
- Check that imports use absolute paths: `from app.endpoints.query import ...`

### Mock Not Working

If mocks aren't being applied:
- Verify you're patching the right location (where it's used, not where it's defined)
- Check that the fixture is included in test parameters
- Use `mocker.patch` instead of `unittest.mock.patch`

### Test Isolation Issues

If tests interfere with each other:
- Check that fixtures have correct scope (usually `function`)
- Verify cleanup is happening in fixtures
- Use `pytest --tb=short -x` to stop on first failure

## Contributing

When adding new common functionality:

1. **Add to conftest.py** - If it's useful across multiple test files
2. **Document here** - Add to this README
3. **Add examples** - Show how to use it
4. **Keep it simple** - Don't over-engineer

When modifying existing fixtures:
1. **Check usage** - Search for uses across all test files
2. **Maintain backwards compatibility** - Don't break existing tests
3. **Update docs** - Keep this README current
