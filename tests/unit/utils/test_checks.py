"""Unit tests for functions defined in utils/checks module."""

from logging import Logger
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

def test_profile_check_empty():
    with pytest.raises(KeyError):
        checks.profile_check(None)

def test_profile_check_missing():
    with pytest.raises(checks.InvalidConfigurationError):
        checks.profile_check("fake")

def test_read_profile_error():
    logger = Logger("test")
    data = checks.read_profile_file("/fake/path", "fake-profile", logger)
    assert data is None

def test_read_profile():
    logger = Logger("test")
    fpath = "utils.profiles"
    profile = "rhdh"
    data = checks.read_profile_file(fpath, profile, logger)
    assert type(data) is ModuleType