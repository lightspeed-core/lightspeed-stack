"""Unit tests for functions defined in utils/checks module."""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from utils import checks


@pytest.fixture(name="input_file")
def input_file_fixture(tmp_path):
    """Create file manually using the tmp_path fixture."""
    filename = os.path.join(tmp_path, "mydoc.csv")
    with open(filename, "wt", encoding="utf-8") as fout:
        fout.write("some content!")
    return filename


@pytest.fixture(name="input_directory")
def input_directory_fixture(tmp_path):
    """Create directory manually using the tmp_path fixture."""
    dirname = os.path.join(tmp_path, "mydir")
    os.mkdir(dirname)
    return dirname


def test_get_attribute_from_file_no_record():
    """Test the get_attribute_from_file function when record is not in dictionary."""
    # no data
    d = {}

    # non-existing key
    key = ""
    value = checks.get_attribute_from_file(d, key)
    assert value is None

    # non-existing key
    key = "this-does-not-exists"
    value = checks.get_attribute_from_file(d, "this-does-not-exists")
    assert value is None


def test_get_attribute_from_file_proper_record(input_file):
    """Test the get_attribute_from_file function when record is present in dictionary."""
    # existing key
    key = "my_file"

    # attribute with proper and existing filename
    d = {key: input_file}

    # file content should be read properly
    value = checks.get_attribute_from_file(d, key)
    assert value is not None
    assert value == "some content!"


def test_get_attribute_from_file_improper_filename():
    """Test the get_attribute_from_file when the file does not exist."""
    # existing key
    key = "my_file"

    # filename for file that does not exist
    input_file = "this-does-not-exists"
    d = {key: input_file}

    with pytest.raises(FileNotFoundError, match="this-does-not-exists"):
        checks.get_attribute_from_file(d, "my_file")


def test_file_check_existing_file(input_file):
    """Test the function file_check for existing file."""
    # just call the function, it should not raise an exception
    checks.file_check(input_file, "description")


def test_file_check_non_existing_file():
    """Test the function file_check for non existing file."""
    with pytest.raises(checks.InvalidConfigurationError):
        checks.file_check(Path("does-not-exists"), "description")


def test_file_check_not_readable_file(input_file):
    """Test the function file_check for not readable file."""
    with patch("os.access", return_value=False):
        with pytest.raises(checks.InvalidConfigurationError):
            checks.file_check(input_file, "description")


def test_directory_check_non_existing_directory():
    """Test the function directory_check skips non-existing directory."""
    # just call the function, it should not raise an exception
    checks.directory_check(
        "/foo/bar/baz", must_exists=False, must_be_writable=False, desc="foobar"
    )
    with pytest.raises(checks.InvalidConfigurationError):
        checks.directory_check(
            "/foo/bar/baz", must_exists=True, must_be_writable=False, desc="foobar"
        )


def test_directory_check_existing_writable_directory(input_directory):
    """Test the function directory_check checks directory."""
    # just call the function, it should not raise an exception
    checks.directory_check(
        input_directory, must_exists=True, must_be_writable=True, desc="foobar"
    )


def test_directory_check_non_a_directory(input_file):
    """Test the function directory_check checks directory."""
    # pass a filename not a directory name
    with pytest.raises(checks.InvalidConfigurationError):
        checks.directory_check(
            input_file, must_exists=True, must_be_writable=True, desc="foobar"
        )


def test_directory_check_existing_non_writable_directory(input_directory):
    """Test the function directory_check checks directory."""
    with patch("os.access", return_value=False):
        with pytest.raises(checks.InvalidConfigurationError):
            checks.directory_check(
                input_directory, must_exists=True, must_be_writable=True, desc="foobar"
            )


def test_import_python_module_success():
    """Test importing a Python module."""
    module_path = "tests/profiles/test/profile.py"
    module_name = "profile"
    result = checks.import_python_module(module_name, module_path)

    assert isinstance(result, ModuleType)


def test_import_python_module_error():
    """Test importing a Python module that is a .txt file."""
    module_path = "tests/profiles/test_two/test.txt"
    module_name = "profile"
    result = checks.import_python_module(module_name, module_path)

    assert result is None


def test_is_valid_profile():
    """Test if an imported profile is valid."""
    module_path = "tests/profiles/test/profile.py"
    module_name = "profile"
    fetched_module = checks.import_python_module(module_name, module_path)
    result = False
    if fetched_module:
        result = checks.is_valid_profile(fetched_module)

    assert result is True


def test_invalid_profile():
    """Test if an imported profile is valid (expect invalid)"""
    module_path = "tests/profiles/test_three/profile.py"
    module_name = "profile"
    fetched_module = checks.import_python_module(module_name, module_path)
    result = False
    if fetched_module:
        result = checks.is_valid_profile(fetched_module)

    assert result is False
