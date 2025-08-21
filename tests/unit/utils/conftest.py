"""Configuration for utils unit tests."""

import os

# Set environment variable for all tests in this directory
os.environ.setdefault("USER_ANON_PEPPER", "test-pepper-for-utils-tests")
