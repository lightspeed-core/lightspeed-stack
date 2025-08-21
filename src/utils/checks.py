"""Checks that are performed to configuration options."""

import os
from types import ModuleType
import constants
import importlib
from logging import Logger
from typing import Optional

from pydantic import FilePath


class InvalidConfigurationError(Exception):
    """Lightspeed configuration is invalid."""


def get_attribute_from_file(data: dict, file_name_key: str) -> Optional[str]:
    """Retrieve value of an attribute from a file."""
    file_path = data.get(file_name_key)
    if file_path is not None:
        with open(file_path, encoding="utf-8") as f:
            return f.read().rstrip()
    return None


def file_check(path: FilePath, desc: str) -> None:
    """Check that path is a readable regular file."""
    if not os.path.isfile(path):
        raise InvalidConfigurationError(f"{desc} '{path}' is not a file")
    if not os.access(path, os.R_OK):
        raise InvalidConfigurationError(f"{desc} '{path}' is not readable")


def profile_check(profile: str | None) -> None:
    if profile is None:
        raise KeyError("Missing profile_name.")
    if profile not in constants.CUSTOM_PROFILES:
        raise InvalidConfigurationError(
            f"Profile {profile} not present. Must be one of: {constants.CUSTOM_PROFILES}"
        )


def read_profile_file(
    profile_path: str,
    profile_name: str,
    logger: Logger,
) -> ModuleType | None:
    try:
        data = importlib.import_module(f"{profile_path}.{profile_name}.profile")
    except (FileNotFoundError, ModuleNotFoundError):
        logger.error("Profile .py file not found.")
        data = None
    return data
