"""Checks that are performed to configuration options."""

import os
import importlib
import importlib.util
from types import ModuleType
from typing import Optional
from pydantic import FilePath


class InvalidConfigurationError(Exception):
    """Lightspeed configuration is invalid."""


def get_attribute_from_file(data: dict, file_name_key: str) -> Optional[str]:
    """
    Return the contents of a file whose path is stored in the given mapping.

    Looks up file_name_key in data; if a non-None value is found it is treated
    as a filesystem path, the content of the file is read. In case the key is
    missing or maps to None, returns None.

    Parameters:
        data (dict): Mapping containing the file path under file_name_key.
        file_name_key (str): Key in `data` whose value is the path to the file.

    Returns:
        Optional[str]: File contents with trailing whitespace stripped, or None
        if the key is not present or is None.
    """
    file_path = data.get(file_name_key)
    if file_path is not None:
        with open(file_path, encoding="utf-8") as f:
            return f.read().rstrip()
    return None


def file_check(path: FilePath, desc: str) -> None:
    """
    Ensure the given path is an existing regular file and is readable.

    If the path is not a regular file or is not readable, raises
    InvalidConfigurationError.

    Parameters:
        path (FilePath): Filesystem path to validate.
        desc (str): Short description of the value being checked; used in error
        messages.

    Raises:
        InvalidConfigurationError: If `path` does not point to a file or is not
        readable.
    """
    if not os.path.isfile(path):
        raise InvalidConfigurationError(f"{desc} '{path}' is not a file")
    if not os.access(path, os.R_OK):
        raise InvalidConfigurationError(f"{desc} '{path}' is not readable")


def directory_check(
    path: FilePath, must_exists: bool, must_be_writable: bool, desc: str
) -> None:
    """
    Ensure the given path is an existing directory.

    If the path is not a directory, raises InvalidConfigurationError.

    Parameters:
        path (FilePath): Filesystem path to validate.
        must_exists (bool): Should the directory exists?
        must_be_writable (bool): Should the check test if directory is writable?
        desc (str): Short description of the value being checked; used in error
        messages.

    Raises:
        InvalidConfigurationError: If `path` does not point to a directory or
        is not writable when required.
    """
    if not os.path.exists(path):
        if must_exists:
            raise InvalidConfigurationError(f"{desc} '{path}' does not exist")
        return
    if not os.path.isdir(path):
        raise InvalidConfigurationError(f"{desc} '{path}' is not a directory")
    if must_be_writable:
        if not os.access(path, os.W_OK):
            raise InvalidConfigurationError(f"{desc} '{path}' is not writable")


def import_python_module(profile_name: str, profile_path: str) -> ModuleType | None:
    """Import a Python module from a file path."""
    if not profile_path.endswith(".py"):
        return None
    spec = importlib.util.spec_from_file_location(profile_name, profile_path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (
        SyntaxError,
        ImportError,
        ModuleNotFoundError,
        NameError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        return None
    return module


def is_valid_profile(profile_module: ModuleType) -> bool:
    """Validate that a profile module has the required PROFILE_CONFIG structure."""
    if not hasattr(profile_module, "PROFILE_CONFIG"):
        return False

    profile_config = getattr(profile_module, "PROFILE_CONFIG", {})
    if not isinstance(profile_config, dict):
        return False

    if not profile_config.get("system_prompts"):
        return False

    return isinstance(profile_config.get("system_prompts"), dict)
