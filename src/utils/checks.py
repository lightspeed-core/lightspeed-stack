"""Checks that are performed to configuration options."""

import importlib
import importlib.util
import os
import sqlite3
from contextlib import closing
from types import ModuleType
from typing import Optional

from pydantic import FilePath

# fixed point in time the quota limiter periods are tried on
SQLITE_PERIOD_REFERENCE = "2000-01-01 00:00:00"


class InvalidConfigurationError(Exception):
    """Lightspeed configuration is invalid."""


def get_attribute_from_file(data: dict[str, str], file_name_key: str) -> Optional[str]:
    """
    Return the contents of a file whose path is stored in the given mapping.

    Looks up file_name_key in data; if a non-None value is found it is treated
    as a filesystem path, the content of the file is read. In case the key is
    missing or maps to None, returns None.

    Parameters:
    ----------
        data (dict): Mapping containing the file path under file_name_key.
        file_name_key (str): Key in `data` whose value is the path to the file.

    Returns:
    -------
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
    ----------
        path (FilePath): Filesystem path to validate.
        desc (str): Short description of the value being checked; used in error
        messages.

    Raises:
    ------
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
    ----------
        path (FilePath): Filesystem path to validate.
        must_exists (bool): Should the directory exists?
        must_be_writable (bool): Should the check test if directory is writable?
        desc (str): Short description of the value being checked; used in error
        messages.

    Raises:
    ------
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


def import_python_module(profile_name: str, profile_path: str) -> Optional[ModuleType]:
    """
    Import a Python module from a filesystem path and return the loaded module.

    Parameters:
    ----------
        profile_name (str): Name to assign to the imported module.
        profile_path (str): Filesystem path to the Python source file; must end with `.py`.

    Returns:
    -------
        Optional[ModuleType]: The loaded module on success; `None` if
        `profile_path` does not end with `.py`, if a module spec or loader
        cannot be created, or if importing/executing the module fails.
    """
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
    """
    Check whether a module exposes a valid PROFILE_CONFIG with required structure.

    The module must define a `PROFILE_CONFIG` attribute that is a dict and contains a non-empty
    `system_prompts` entry. This function returns `True` only when `system_prompts` exists
    and is itself a dict.

    Returns:
        True if the module provides a dict `PROFILE_CONFIG` containing a
        `system_prompts` dict, False otherwise.
    """
    if not hasattr(profile_module, "PROFILE_CONFIG"):
        return False

    profile_config = getattr(profile_module, "PROFILE_CONFIG", {})
    if not isinstance(profile_config, dict):
        return False

    if not profile_config.get("system_prompts"):
        return False

    return isinstance(profile_config.get("system_prompts"), dict)


def is_valid_sqlite_period(period: str) -> bool:
    """
    Check whether SQLite can use the period to move a timestamp forward.

    The quota scheduler passes the period of a quota limiter to the SQLite
    function datetime() as a modifier. SQLite itself is asked what it makes of
    the period, so the check can not drift from what SQLite accepts: datetime()
    returns NULL for a modifier it can not parse, and a zero or negative period
    does not give a later time.

    Parameters:
    ----------
        period (str): Period as specified in the quota limiter configuration.

    Returns:
    -------
        bool: True if datetime() applied to a fixed timestamp with the period
        as the modifier returns a later time, False otherwise.
    """
    # julianday() makes it a comparison of times: as text, the result of the
    # modifier 'subsec' would be greater than the timestamp it does not move
    with closing(sqlite3.connect(":memory:")) as connection:
        (is_later,) = connection.execute(
            "SELECT julianday(datetime(?, ?)) > julianday(?)",
            (SQLITE_PERIOD_REFERENCE, period, SQLITE_PERIOD_REFERENCE),
        ).fetchone()
    return bool(is_later)
