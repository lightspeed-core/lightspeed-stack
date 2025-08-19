"""Unit tests for functions defined in src/lightspeed_stack.py."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lightspeed_stack import create_argument_parser, store_config


def test_create_argument_parser():
    """Test for create_argument_parser function."""
    arg_parser = create_argument_parser()
    # nothing more to test w/o actual parsing is done
    assert arg_parser is not None


@pytest.fixture
def config_storage_path(tmpdir):
    """Fixture provides a temporary config storage location."""
    return (tmpdir / "config").strpath


@pytest.fixture
def mock_configuration(config_storage_path):  # pylint: disable=redefined-outer-name
    """Fixture provides a mock configuration object for testing."""
    mock_config = MagicMock()
    mock_config.user_data_collection_configuration.config_storage = config_storage_path
    return mock_config


@pytest.fixture
def sample_config_file():
    """Create a temporary config file with sample content."""
    config_content = """# Sample configuration
name: Lightspeed Core Service (LCS)
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: true
  library_client_config_path: run.yaml
user_data_collection:
  feedback_enabled: true
  feedback_storage: "/tmp/data/feedback"
  transcripts_enabled: true
  transcripts_storage: "/tmp/data/transcripts"
  config_enabled: true
  config_storage: "/tmp/data/config"
authentication:
  module: "noop"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_content)
        f.flush()
        yield f.name
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@patch("lightspeed_stack.configuration")
def test_store_config_enabled(
    mock_configuration_module,
    config_storage_path,
    sample_config_file,
    mock_configuration,
):  # pylint: disable=redefined-outer-name
    """Test that config is stored when enabled."""
    mock_configuration_module.user_data_collection_configuration = (
        mock_configuration.user_data_collection_configuration
    )

    store_config(sample_config_file)

    # Verify that a config file was created
    config_files = list(Path(config_storage_path).glob("*.json"))
    assert len(config_files) == 1, f"Expected 1 config file, found {len(config_files)}"

    # Verify the content
    with open(config_files[0], "r", encoding="utf-8") as f:
        stored_data = json.load(f)

    assert "metadata" in stored_data
    assert "configuration" in stored_data
    assert "timestamp" in stored_data["metadata"]
    assert "service_version" in stored_data["metadata"]
    assert "config_file_path" in stored_data["metadata"]

    assert stored_data["metadata"]["config_file_path"] == sample_config_file
    assert "name: Lightspeed Core Service (LCS)" in stored_data["configuration"]
    assert "user_data_collection:" in stored_data["configuration"]


@patch("lightspeed_stack.configuration")
def test_store_config_creates_directory(
    mock_configuration_module, tmpdir, sample_config_file
):  # pylint: disable=redefined-outer-name
    """Test that config storage creates directory if it doesn't exist."""
    # Use a non-existent nested directory path
    nested_path = tmpdir / "nested" / "config" / "storage"
    full_path = nested_path.strpath

    # Create a mock config with the nested path
    mock_config = MagicMock()
    mock_config.user_data_collection_configuration.config_storage = full_path
    mock_configuration_module.user_data_collection_configuration = (
        mock_config.user_data_collection_configuration
    )

    # Directory shouldn't exist initially
    assert not Path(full_path).exists()

    # Call store_config
    store_config(sample_config_file)

    # Directory should be created
    assert Path(full_path).exists()
    assert Path(full_path).is_dir()

    # Config file should be stored
    config_files = list(Path(full_path).glob("*.json"))
    assert len(config_files) == 1


@patch("lightspeed_stack.configuration")
def test_store_config_unique_filenames(
    mock_configuration_module,
    config_storage_path,
    sample_config_file,
    mock_configuration,
):  # pylint: disable=redefined-outer-name
    """Test that multiple calls create files with unique names."""
    mock_configuration_module.user_data_collection_configuration = (
        mock_configuration.user_data_collection_configuration
    )

    # Call store_config multiple times
    store_config(sample_config_file)
    store_config(sample_config_file)
    store_config(sample_config_file)

    # Should have 3 unique files
    config_files = list(Path(config_storage_path).glob("*.json"))
    assert len(config_files) == 3

    # All filenames should be unique
    filenames = [f.name for f in config_files]
    assert len(set(filenames)) == 3


@patch("lightspeed_stack.version.__version__", "1.2.3-test")
@patch("lightspeed_stack.configuration")
def test_store_config_includes_version(
    mock_configuration_module,
    config_storage_path,
    sample_config_file,
    mock_configuration,
):  # pylint: disable=redefined-outer-name
    """Test that stored config includes the service version."""
    mock_configuration_module.user_data_collection_configuration = (
        mock_configuration.user_data_collection_configuration
    )

    store_config(sample_config_file)

    config_files = list(Path(config_storage_path).glob("*.json"))
    with open(config_files[0], "r", encoding="utf-8") as f:
        stored_data = json.load(f)

    assert stored_data["metadata"]["service_version"] == "1.2.3-test"


@patch("lightspeed_stack.configuration")
def test_store_config_preserves_yaml_content(
    mock_configuration_module,
    config_storage_path,
    sample_config_file,
    mock_configuration,
):  # pylint: disable=redefined-outer-name
    """Test that original YAML content is preserved exactly."""
    mock_configuration_module.user_data_collection_configuration = (
        mock_configuration.user_data_collection_configuration
    )

    # Read the original content
    with open(sample_config_file, "r", encoding="utf-8") as f:
        original_content = f.read()

    store_config(sample_config_file)

    config_files = list(Path(config_storage_path).glob("*.json"))
    with open(config_files[0], "r", encoding="utf-8") as f:
        stored_data = json.load(f)

    # The stored configuration should match the original exactly
    assert stored_data["configuration"] == original_content


@patch("lightspeed_stack.configuration")
def test_store_config_json_format(
    mock_configuration_module,
    config_storage_path,
    sample_config_file,
    mock_configuration,
):  # pylint: disable=redefined-outer-name
    """Test that stored file is valid JSON with proper structure."""
    mock_configuration_module.user_data_collection_configuration = (
        mock_configuration.user_data_collection_configuration
    )

    store_config(sample_config_file)

    config_files = list(Path(config_storage_path).glob("*.json"))

    # Should be valid JSON
    with open(config_files[0], "r", encoding="utf-8") as f:
        stored_data = json.load(f)  # This will raise if invalid JSON

    # Should have expected structure
    expected_keys = {"metadata", "configuration"}
    assert set(stored_data.keys()) == expected_keys

    expected_metadata_keys = {
        "timestamp",
        "service_version",
        "config_file_path",
    }
    assert set(stored_data["metadata"].keys()) == expected_metadata_keys

    # Configuration should be a string (YAML content)
    assert isinstance(stored_data["configuration"], str)
