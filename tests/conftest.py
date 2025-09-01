"""Global configuration for all tests."""

import os

# Set environment variable for all tests globally
# This ensures the anonymization module can be imported in CI environments
os.environ.setdefault("USER_ANON_PEPPER", "test-pepper-for-all-tests")
