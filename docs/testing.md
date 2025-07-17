# Testing

Three groups of software tests are used in this repository, each group from the test suite having different granularity. These groups are designed to represent three layers:

1. Unit Tests
1. Integration Tests
1. End to end Tests



## Running tests

Unit tests followed by integration and end to end tests can be started by using the following command:

```
make test
```

It is also possible to run just one selected group of tests:

```
make test-unit                 Run the unit tests
make test-integration          Run integration tests tests
make test-e2e                  Run end to end tests
```



## Unit tests

Unit tests are based on the [Pytest framework](https://docs.pytest.org/en/) and code coverage is measured by the plugin [pytest-cov](https://github.com/pytest-dev/pytest-cov). For mocking and patching, the [unittest framework](https://docs.python.org/3/library/unittest.html) is used.

Currently code coverage threshold for integration tests is set to 60%. This value is specified directly in Makefile, because the coverage threshold is different from threshold required for unit tests.

As specified in Definition of Done, new changes need to be covered by tests.

### Unit tests structure

* Defined in [tests/unit](https://github.com/lightspeed-core/lightspeed-stack/tree/main/tests/unit)


```
├── app
│   ├── endpoints
│   │   ├── __init__.py
│   │   ├── test_authorized.py
│   │   ├── test_config.py
│   │   ├── test_feedback.py
│   │   ├── test_health.py
│   │   ├── test_info.py
│   │   ├── test_models.py
│   │   ├── test_query.py
│   │   ├── test_root.py
│   │   └── test_streaming_query.py
│   ├── __init__.py
│   └── test_routers.py
├── auth
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_k8s.py
│   ├── test_noop.py
│   ├── test_noop_with_token.py
│   └── test_utils.py
├── __init__.py
├── models
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_requests.py
│   └── test_responses.py
├── runners
│   ├── __init__.py
│   ├── test_data_collector_runner.py
│   └── test_uvicorn_runner.py
├── services
│   └── test_data_collector.py
├── test_client.py
├── test_configuration.py
├── test_lightspeed_stack.py
├── test_log.py
└── utils
    ├── __init__.py
    ├── test_checks.py
    ├── test_common.py
    ├── test_endpoints.py
    ├── test_suid.py
    └── test_types.py
```

* Please note that the directory structure of unit tests is similar to source directory structure. It helps choosing just one test to be run.



## Integration tests

Integration tests are based on the [Pytest framework](https://docs.pytest.org/en/) and code coverage is measured by the plugin [pytest-cov](https://github.com/pytest-dev/pytest-cov). For mocking and patching, the [unittest framework](https://docs.python.org/3/library/unittest.html) is used.

* Defined in [tests/integration](https://github.com/lightspeed-core/lightspeed-stack/tree/main/tests/integration)



## End to end tests

End to end tests are based on [Behave](https://behave.readthedocs.io/en/stable/) framework. Tests are specified in a form of [test scenarios](e2e_scenarios.md).

* Defined in [tests/e2e](https://github.com/lightspeed-core/lightspeed-stack/tree/main/tests/e2e)



## Tips and hints

### Developing unit tests

#### Patching

**WARNING**:
Since tests are executed using Pytest, which relies heavily on fixtures,
we discourage use of `patch` decorators in all test code, as they may interact with one another.

It is possible to use patching inside the test implementation as a context manager:

```python
def test_xyz():
    with patch("ols.config", new=Mock()):
        ...
        ...
        ...
```

- `new=` allow us to use different function or class
- `return_value=` allow us to define return value (no mock will be called)


#### Verifying that some exception is thrown

Sometimes it is needed to test whether some exception is thrown from a tested function or method. In this case `pytest.raises` can be used:


```python
def test_conversation_cache_wrong_cache(invalid_cache_type_config):
    """Check if wrong cache env.variable is detected properly."""
    with pytest.raises(ValueError):
        CacheFactory.conversation_cache(invalid_cache_type_config)
```

It is also possible to check if the exception is thrown with the expected message. The message (or its part) is written as regexp:

```python
def test_constructor_no_provider():
    """Test that constructor checks for provider."""
    # we use bare Exception in the code, so need to check
    # message, at least
    with pytest.raises(Exception, match="ERROR: Missing provider"):
        load_llm(provider=None)
```

#### Checking what was printed and logged to stdout or stderr by the tested code

It is possible to capture stdout and stderr by using standard fixture `capsys`:

```python
def test_foobar(capsys):
    """Test the foobar function that prints to stdout."""
    foobar("argument1", "argument2")

    # check captured log output
    captured_out = capsys.readouterr().out
    assert captured_out == "Output printed by foobar function"
    captured_err = capsys.readouterr().err
    assert captured_err == ""
```

Capturing logs:

```python
@patch.dict(os.environ, {"LOG_LEVEL": "INFO"})
def test_logger_show_message_flag(mock_load_dotenv, capsys):
    """Test logger set with show_message flag."""
    logger = Logger(logger_name="foo", log_level=logging.INFO, show_message=True)
    logger.logger.info("This is my debug message")

    # check captured log output
    # the log message should be captured
    captured_out = capsys.readouterr().out
    assert "This is my debug message" in captured_out

    # error output should be empty
    captured_err = capsys.readouterr().err
    assert captured_err == ""
```
